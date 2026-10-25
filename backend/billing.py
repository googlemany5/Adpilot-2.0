import os

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from auth import get_current_user, get_db
from database import ProcessedStripeEventDB, SubscriptionDB, UserDB
from plan_config import PAID_PLAN_CAMPAIGN_LIMITS

router = APIRouter(tags=["billing"])


def _is_stale_stripe_event(subscription, event_created):
    last_created = subscription.last_stripe_event_created
    return last_created is not None and event_created < last_created


def _record_stripe_event(subscription, event_created):
    last_created = subscription.last_stripe_event_created
    if last_created is None or event_created > last_created:
        subscription.last_stripe_event_created = event_created


class CheckoutRequest(BaseModel):
    plan: str


def _price_ids():
    return {
        "starter": os.getenv("STRIPE_STARTER_PRICE_ID"),
        "pro": os.getenv("STRIPE_PRO_PRICE_ID"),
        "business": os.getenv("STRIPE_BUSINESS_PRICE_ID"),
    }


def _find_subscription(db, customer_id=None, subscription_id=None, user_id=None):
    query = db.query(SubscriptionDB)

    # A supplied Stripe subscription ID is authoritative. Never fall back
    # to another customer or user if that exact ID is not found.
    if subscription_id:
        return query.filter(
            SubscriptionDB.stripe_subscription_id == str(subscription_id)
        ).first()

    if customer_id:
        result = query.filter(
            SubscriptionDB.stripe_customer_id == str(customer_id)
        ).first()
        if result:
            return result

    if user_id is not None:
        return query.filter(SubscriptionDB.user_id == int(user_id)).first()

    return None


def _stripe_identifiers_conflict(
    db, subscription, customer_id=None, subscription_id=None
):
    # Stripe customer and subscription identifiers must not be shared
    # between different AdPilot subscription records.
    query = db.query(SubscriptionDB).filter(
        SubscriptionDB.id != subscription.id
    )

    if customer_id and query.filter(
        SubscriptionDB.stripe_customer_id == str(customer_id)
    ).first():
        return True

    if subscription_id and query.filter(
        SubscriptionDB.stripe_subscription_id == str(subscription_id)
    ).first():
        return True

    return False


def _ensure_subscription(db, user_id):
    subscription = _find_subscription(db, user_id=user_id)
    if subscription is None:
        subscription = SubscriptionDB(
            user_id=user_id,
            plan="none",
            status="pending",
        )
        db.add(subscription)
        db.flush()
    return subscription


@router.post("/billing/checkout")
def create_checkout(
    data: CheckoutRequest,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plan = data.plan.strip().lower()

    if plan not in PAID_PLAN_CAMPAIGN_LIMITS:
        raise HTTPException(status_code=400, detail="Unknown paid plan.")

    secret = os.getenv("STRIPE_SECRET_KEY")
    frontend_url = os.getenv("ADPILOT_FRONTEND_URL")
    price_id = _price_ids().get(plan)

    if not secret or not frontend_url or not price_id:
        raise HTTPException(
            status_code=503,
            detail="Billing is not configured. Please try again later.",
        )

    frontend_url = frontend_url.rstrip("/")
    if not (
        frontend_url.startswith("https://")
        or frontend_url.startswith("http://localhost")
    ):
        raise HTTPException(
            status_code=503,
            detail="The configured frontend URL is not permitted.",
        )

    subscription = _ensure_subscription(db, current_user.id)

    if (
        subscription.status == "active"
        and subscription.plan in PAID_PLAN_CAMPAIGN_LIMITS
        and subscription.stripe_subscription_id
    ):
        db.commit()
        raise HTTPException(
            status_code=409,
            detail="You already have an active paid subscription.",
        )

    db.commit()

    try:
        session = stripe.checkout.Session.create(
            api_key=secret,
            mode="subscription",
            customer=subscription.stripe_customer_id or None,
            customer_email=(
                None if subscription.stripe_customer_id else current_user.email
            ),
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{frontend_url}/?billing=success",
            cancel_url=f"{frontend_url}/?billing=cancelled",
            client_reference_id=str(current_user.id),
            metadata={
                "user_id": str(current_user.id),
                "plan": plan,
            },
            subscription_data={
                "metadata": {
                    "user_id": str(current_user.id),
                    "plan": plan,
                }
            },
        )
    except stripe.StripeError:
        raise HTTPException(
            status_code=502,
            detail="Stripe could not create checkout. Please try again.",
        )

    return {"checkout_url": session.url}


@router.post("/billing/webhook")
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    signature = request.headers.get("stripe-signature")

    if not secret or not signature:
        raise HTTPException(status_code=400, detail="Webhook configuration missing.")

    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=signature,
            secret=secret,
        )
    except (ValueError, stripe.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid webhook signature.")

    event_type = event["type"]
    obj = event["data"]["object"]

    try:
        event_created = int(event["created"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="Invalid webhook event timestamp.",
        )

    if event_created < 0:
        raise HTTPException(
            status_code=400,
            detail="Invalid webhook event timestamp.",
        )

    event_id = event.get("id")
    if not isinstance(event_id, str) or not event_id.strip():
        raise HTTPException(status_code=400, detail="Invalid Stripe event ID")

    # Fast path for retries. The primary key and flush also protect against
    # concurrent requests attempting to register the same event.
    if db.query(ProcessedStripeEventDB).filter_by(event_id=event_id).first():
        return {"received": True}

    db.add(
        ProcessedStripeEventDB(
            event_id=event_id,
            event_type=event_type,
            event_created=event_created,
        )
    )
    try:
        db.flush()
    except IntegrityError:
        # Another request may have registered this event after our lookup.
        # Roll back the failed transaction; do not commit after rollback.
        db.rollback()
        return {"received": True}

    if event_type == "checkout.session.completed":
        metadata = obj.get("metadata") or {}
        user_id = metadata.get("user_id") or obj.get("client_reference_id")
        plan = (metadata.get("plan") or "").strip().lower()

        try:
            user_id = int(user_id) if user_id is not None else None
        except (TypeError, ValueError):
            user_id = None

        if user_id is not None and plan in PAID_PLAN_CAMPAIGN_LIMITS:
            # Never create or modify a subscription for a nonexistent user.
            user = db.query(UserDB).filter(UserDB.id == user_id).first()
            if user is None:
                db.commit()
                return {"received": True}

            subscription = _ensure_subscription(db, user_id)
            if _is_stale_stripe_event(subscription, event_created):
                db.commit()
                return {"received": True}

            new_subscription_id = obj.get("subscription")
            if isinstance(new_subscription_id, dict):
                new_subscription_id = new_subscription_id.get("id")

            customer_id = obj.get("customer")
            if isinstance(customer_id, dict):
                customer_id = customer_id.get("id")

            # Do not let checkout attach identifiers already owned by
            # another AdPilot account.
            if _stripe_identifiers_conflict(
                db,
                subscription,
                customer_id=customer_id,
                subscription_id=new_subscription_id,
            ):
                db.commit()
                return {"received": True}

            same_subscription = (
                bool(new_subscription_id)
                and subscription.stripe_subscription_id == str(new_subscription_id)
            )

            subscription.plan = plan
            if customer_id:
                subscription.stripe_customer_id = str(customer_id)
            if new_subscription_id:
                subscription.stripe_subscription_id = str(new_subscription_id)

            # Checkout completion alone never grants paid access.
            if not same_subscription:
                subscription.status = "pending"

            _record_stripe_event(subscription, event_created)
            db.commit()

    elif event_type in {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }:
        metadata = obj.get("metadata") or {}
        plan = (metadata.get("plan") or "").strip().lower()
        user_id = metadata.get("user_id")
        customer_id = obj.get("customer")
        subscription_id = obj.get("id")

        subscription = _find_subscription(
            db,
            customer_id=customer_id,
            subscription_id=subscription_id,
            user_id=user_id,
        )

        # Reject conflicting identifiers. A valid subscription ID must not
        # be allowed to change a different stored Stripe customer's access.
        metadata_user_id = metadata.get("user_id")
        if subscription is not None and metadata_user_id is not None:
            try:
                if int(metadata_user_id) != subscription.user_id:
                    subscription = None
            except (TypeError, ValueError):
                subscription = None

        if (
            subscription is not None
            and customer_id
            and subscription.stripe_customer_id
            and subscription.stripe_customer_id != str(customer_id)
        ):
            subscription = None

        if subscription is not None and _stripe_identifiers_conflict(
            db,
            subscription,
            customer_id=customer_id,
            subscription_id=subscription_id,
        ):
            subscription = None

        if subscription is not None:
            if _is_stale_stripe_event(subscription, event_created):
                db.commit()
                return {"received": True}

            if plan in PAID_PLAN_CAMPAIGN_LIMITS:
                subscription.plan = plan

            if customer_id:
                subscription.stripe_customer_id = str(customer_id)
            if subscription_id:
                subscription.stripe_subscription_id = str(subscription_id)

            provider_status = obj.get("status", "")
            if (
                event_type != "customer.subscription.deleted"
                and provider_status in {"active", "trialing"}
                and subscription.plan in PAID_PLAN_CAMPAIGN_LIMITS
            ):
                subscription.status = "active"
            else:
                subscription.status = "pending"

            _record_stripe_event(subscription, event_created)
            db.commit()

    elif event_type == "invoice.payment_failed":
        subscription_id = obj.get("subscription")
        if isinstance(subscription_id, dict):
            subscription_id = subscription_id.get("id")

        subscription = _find_subscription(
            db, subscription_id=subscription_id
        )
        if subscription is not None:
            if _is_stale_stripe_event(subscription, event_created):
                db.commit()
                return {"received": True}

            subscription.status = "pending"
            _record_stripe_event(subscription, event_created)
            db.commit()

    # Unhandled signed events are acknowledged without changing access.
    db.commit()
    return {"received": True}
