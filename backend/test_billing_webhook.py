import json

import pytest
import stripe
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import billing
from auth import get_db
from database import Base, UserDB, SubscriptionDB
from main import app


@pytest.fixture
def billing_setup(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )
    db = TestingSession()

    user = UserDB(
        email="billing-webhook-test@example.com",
        password_hash="not-used-in-this-test",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    subscription = SubscriptionDB(
        user_id=user.id,
        plan="starter",
        status="pending",
        stripe_customer_id="cus_test_123",
        stripe_subscription_id="sub_test_123",
    )
    db.add(subscription)
    db.commit()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_secret")

    client = TestClient(app, raise_server_exceptions=True)

    yield client, db, user, subscription

    app.dependency_overrides.clear()
    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def send_event(
    monkeypatch, client, event_type, obj, created=1800000000, event_id=None
):
    event = {
        "id": event_id or f"evt_test_{created}_{event_type}",
        "created": created,
        "type": event_type,
        "data": {"object": obj},
    }

    monkeypatch.setattr(
        stripe.Webhook,
        "construct_event",
        lambda **kwargs: event,
    )

    return client.post(
        "/billing/webhook",
        content=json.dumps(event),
        headers={"stripe-signature": "test-signature"},
    )


def test_active_stripe_subscription_activates_paid_access(
    billing_setup, monkeypatch
):
    client, db, user, subscription = billing_setup

    response = send_event(
        monkeypatch,
        client,
        "customer.subscription.updated",
        {
            "id": "sub_test_123",
            "customer": "cus_test_123",
            "status": "active",
            "metadata": {
                "user_id": str(user.id),
                "plan": "starter",
            },
        },
    )

    assert response.status_code == 200
    db.refresh(subscription)
    assert subscription.status == "active"
    assert subscription.plan == "starter"


def test_invalid_stripe_signature_is_rejected(
    billing_setup, monkeypatch
):
    client, db, user, subscription = billing_setup

    def reject_signature(**kwargs):
        raise stripe.SignatureVerificationError(
            "Invalid signature",
            sig_header=kwargs.get("sig_header", ""),
        )

    monkeypatch.setattr(
        stripe.Webhook,
        "construct_event",
        reject_signature,
    )

    response = client.post(
        "/billing/webhook",
        content='{"type":"customer.subscription.updated"}',
        headers={"stripe-signature": "invalid"},
    )

    assert response.status_code == 400
    db.refresh(subscription)
    assert subscription.status == "pending"


def test_deleted_subscription_removes_paid_access(
    billing_setup, monkeypatch
):
    client, db, user, subscription = billing_setup
    subscription.status = "active"
    db.commit()

    response = send_event(
        monkeypatch,
        client,
        "customer.subscription.deleted",
        {
            "id": "sub_test_123",
            "customer": "cus_test_123",
            "status": "canceled",
            "metadata": {
                "user_id": str(user.id),
                "plan": "starter",
            },
        },
    )

    assert response.status_code == 200
    db.refresh(subscription)
    assert subscription.status == "pending"


def test_failed_payment_removes_paid_access(
    billing_setup, monkeypatch
):
    client, db, user, subscription = billing_setup
    subscription.status = "active"
    db.commit()

    response = send_event(
        monkeypatch,
        client,
        "invoice.payment_failed",
        {"subscription": "sub_test_123"},
    )

    assert response.status_code == 200
    db.refresh(subscription)
    assert subscription.status == "pending"


def test_checkout_completion_does_not_activate_new_subscription(
    billing_setup, monkeypatch
):
    client, db, user, subscription = billing_setup

    response = send_event(
        monkeypatch,
        client,
        "checkout.session.completed",
        {
            "id": "cs_test_123",
            "customer": "cus_test_123",
            "subscription": "sub_new_456",
            "client_reference_id": str(user.id),
            "metadata": {
                "user_id": str(user.id),
                "plan": "starter",
            },
        },
    )

    assert response.status_code == 200
    db.refresh(subscription)
    assert subscription.status == "pending"
    assert subscription.stripe_subscription_id == "sub_new_456"


def test_repeated_checkout_event_does_not_duplicate_subscription(
    billing_setup, monkeypatch
):
    client, db, user, subscription = billing_setup

    event_object = {
        "id": "cs_test_123",
        "customer": "cus_test_123",
        "subscription": "sub_new_456",
        "client_reference_id": str(user.id),
        "metadata": {
            "user_id": str(user.id),
            "plan": "starter",
        },
    }

    first = send_event(
        monkeypatch, client, "checkout.session.completed", event_object
    )
    second = send_event(
        monkeypatch, client, "checkout.session.completed", event_object
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert db.query(SubscriptionDB).filter_by(user_id=user.id).count() == 1
    db.refresh(subscription)
    assert subscription.status == "pending"
    assert subscription.stripe_subscription_id == "sub_new_456"


def test_stale_active_event_does_not_restore_access_after_failed_payment(
    billing_setup, monkeypatch
):
    client, db, user, subscription = billing_setup
    subscription.status = "active"
    db.commit()

    # First, Stripe reports that payment failed.
    failed_payment = send_event(
        monkeypatch,
        client,
        "invoice.payment_failed",
        {"subscription": "sub_test_123"},
        created=200,
    )
    assert failed_payment.status_code == 200

    db.refresh(subscription)
    assert subscription.status == "pending"

    # Then an older "active" update arrives late.
    stale_active_update = send_event(
        monkeypatch,
        client,
        "customer.subscription.updated",
        {
            "id": "sub_test_123",
            "customer": "cus_test_123",
            "status": "active",
            "metadata": {
                "user_id": str(user.id),
                "plan": "starter",
            },
        },
        created=100,
    )
    assert stale_active_update.status_code == 200

    db.refresh(subscription)

    # A stale event must not restore paid access.
    assert subscription.status == "pending"



def test_newer_active_event_can_restore_access_after_failed_payment(
    billing_setup, monkeypatch
):
    client, db, user, subscription = billing_setup
    subscription.status = "active"
    db.commit()

    failed_payment = send_event(
        monkeypatch,
        client,
        "invoice.payment_failed",
        {"subscription": "sub_test_123"},
        created=200,
    )
    assert failed_payment.status_code == 200
    db.refresh(subscription)
    assert subscription.status == "pending"

    newer_active_update = send_event(
        monkeypatch,
        client,
        "customer.subscription.updated",
        {
            "id": "sub_test_123",
            "customer": "cus_test_123",
            "status": "active",
            "metadata": {
                "user_id": str(user.id),
                "plan": "starter",
            },
        },
        created=300,
    )
    assert newer_active_update.status_code == 200
    db.refresh(subscription)
    assert subscription.status == "active"
    assert subscription.last_stripe_event_created == 300


def test_unknown_subscription_id_does_not_fall_back_to_customer_or_user(
    billing_setup, monkeypatch
):
    client, db, user, subscription = billing_setup

    response = send_event(
        monkeypatch,
        client,
        "customer.subscription.updated",
        {
            "id": "sub_unknown_999",
            "customer": "cus_test_123",
            "status": "active",
            "metadata": {
                "user_id": str(user.id),
                "plan": "starter",
            },
        },
    )

    assert response.status_code == 200
    db.refresh(subscription)
    assert subscription.status == "pending"
    assert subscription.stripe_subscription_id == "sub_test_123"


def test_conflicting_customer_id_cannot_change_subscription(
    billing_setup, monkeypatch
):
    client, db, user, subscription = billing_setup

    response = send_event(
        monkeypatch,
        client,
        "customer.subscription.updated",
        {
            "id": "sub_test_123",
            "customer": "cus_someone_else",
            "status": "active",
            "metadata": {
                "user_id": str(user.id),
                "plan": "starter",
            },
        },
    )

    assert response.status_code == 200
    db.refresh(subscription)
    assert subscription.status == "pending"
    assert subscription.stripe_customer_id == "cus_test_123"
    assert subscription.stripe_subscription_id == "sub_test_123"



def test_checkout_cannot_claim_another_users_stripe_identifiers(
    billing_setup, monkeypatch
):
    client, db, user, subscription = billing_setup

    other_user = UserDB(
        email="other-billing-owner@example.com",
        password_hash="not-used-in-this-test",
        is_active=True,
    )
    db.add(other_user)
    db.commit()
    db.refresh(other_user)

    other_subscription = SubscriptionDB(
        user_id=other_user.id,
        plan="pro",
        status="active",
        stripe_customer_id="cus_other_owner",
        stripe_subscription_id="sub_other_owner",
    )
    db.add(other_subscription)
    db.commit()

    response = send_event(
        monkeypatch,
        client,
        "checkout.session.completed",
        {
            "id": "cs_attempted_claim",
            "customer": "cus_other_owner",
            "subscription": "sub_other_owner",
            "client_reference_id": str(user.id),
            "metadata": {
                "user_id": str(user.id),
                "plan": "starter",
            },
        },
    )

    assert response.status_code == 200
    db.refresh(subscription)
    db.refresh(other_subscription)

    assert subscription.stripe_customer_id == "cus_test_123"
    assert subscription.stripe_subscription_id == "sub_test_123"
    assert subscription.status == "pending"

    assert other_subscription.user_id == other_user.id
    assert other_subscription.stripe_customer_id == "cus_other_owner"
    assert other_subscription.stripe_subscription_id == "sub_other_owner"
    assert other_subscription.status == "active"


def test_subscription_event_with_wrong_metadata_user_does_not_change_owner(
    billing_setup, monkeypatch
):
    client, db, user, subscription = billing_setup

    other_user = UserDB(
        email="metadata-mismatch@example.com",
        password_hash="not-used-in-this-test",
        is_active=True,
    )
    db.add(other_user)
    db.commit()
    db.refresh(other_user)

    response = send_event(
        monkeypatch,
        client,
        "customer.subscription.updated",
        {
            "id": "sub_test_123",
            "customer": "cus_test_123",
            "status": "active",
            "metadata": {
                "user_id": str(other_user.id),
                "plan": "starter",
            },
        },
    )

    assert response.status_code == 200
    db.refresh(subscription)

    assert subscription.user_id == user.id
    assert subscription.status == "pending"
    assert subscription.stripe_customer_id == "cus_test_123"
    assert subscription.stripe_subscription_id == "sub_test_123"


def test_duplicate_event_id_cannot_apply_a_different_payload(
    billing_setup, monkeypatch
):
    client, db, user, subscription = billing_setup
    event_id = "evt_same_id_different_payload"

    active_event = {
        "id": "sub_test_123",
        "customer": "cus_test_123",
        "status": "active",
        "metadata": {"user_id": str(user.id), "plan": "starter"},
    }
    first = send_event(
        monkeypatch,
        client,
        "customer.subscription.updated",
        active_event,
        created=1800000000,
        event_id=event_id,
    )
    assert first.status_code == 200
    db.refresh(subscription)
    assert subscription.status == "active"

    # Same Stripe event ID must be ignored, even if a different payload
    # is supplied in this test to simulate an unexpected replay.
    changed_event = {
        **active_event,
        "status": "past_due",
    }
    second = send_event(
        monkeypatch,
        client,
        "customer.subscription.updated",
        changed_event,
        created=1800000000,
        event_id=event_id,
    )
    assert second.status_code == 200
    db.refresh(subscription)
    assert subscription.status == "active"

    processed_count = (
        db.query(billing.ProcessedStripeEventDB)
        .filter_by(event_id=event_id)
        .count()
    )
    assert processed_count == 1


def test_failed_webhook_event_can_be_retried(billing_setup, monkeypatch):
    client, db, user, subscription = billing_setup
    event_id = "evt_retry_after_processing_failure"

    original_find = billing._find_subscription
    calls = {"count": 0}

    def fail_once(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("Simulated temporary database failure")
        return original_find(*args, **kwargs)

    monkeypatch.setattr(billing, "_find_subscription", fail_once)

    event_obj = {
        "id": "sub_test_123",
        "customer": "cus_test_123",
        "status": "active",
        "metadata": {
            "user_id": str(user.id),
            "plan": "starter",
        },
    }

    # The first attempt fails unexpectedly.
    with pytest.raises(RuntimeError, match="Simulated temporary database failure"):
        send_event(
            monkeypatch,
            client,
            "customer.subscription.updated",
            event_obj,
            event_id=event_id,
        )

    # Roll back the test's shared session to simulate request cleanup after
    # an unhandled exception and inspect persisted database state.
    db.rollback()
    assert (
        db.query(billing.ProcessedStripeEventDB)
        .filter_by(event_id=event_id)
        .count()
        == 0
    )

    # The same event can then be retried successfully.
    retry = send_event(
        monkeypatch,
        client,
        "customer.subscription.updated",
        event_obj,
        event_id=event_id,
    )

    assert retry.status_code == 200
    db.refresh(subscription)
    assert subscription.status == "active"
    assert (
        db.query(billing.ProcessedStripeEventDB)
        .filter_by(event_id=event_id)
        .count()
        == 1
    )
