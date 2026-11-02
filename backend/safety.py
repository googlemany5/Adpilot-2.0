from datetime import date, datetime
import math

from sqlalchemy import update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from database import CampaignDB, SpendingTransactionDB


# ============================================================
# ADPILOT SAFETY SETTINGS
# ============================================================

MINIMUM_DAILY_RESERVE = 0.00

# Prevent a single allocation from consuming an unreasonable
# percentage of the campaign's remaining daily budget.
MAX_SINGLE_ALLOCATION_PERCENT = 0.50


# ============================================================
# DATE / MONTH HELPERS
# ============================================================

def reset_daily_if_needed(campaign: CampaignDB):
    today = date.today()

    if campaign.spending_date != today:
        campaign.spending_date = today
        campaign.spent_today = 0.0


def reset_monthly_if_needed(campaign: CampaignDB):
    today = date.today()
    current_month = today.month
    current_year = today.year

    if (
        campaign.spending_month != current_month
        or getattr(campaign, "spending_year", current_year)
        != current_year
    ):
        campaign.spending_month = current_month
        campaign.spending_year = current_year
        campaign.spent_this_month = 0.0


# ============================================================
# BUDGET LIMITS
# ============================================================

def calculate_daily_budget(campaign: CampaignDB) -> float:
    """
    Prototype pacing system.

    Monthly budget is divided across 30 days.
    Later this will account for the actual number of days
    remaining in the billing period.
    """

    if campaign.monthly_budget <= 0:
        return 0.0

    return campaign.monthly_budget / 30.0


def get_remaining_daily_budget(
    campaign: CampaignDB,
) -> float:

    reset_daily_if_needed(campaign)

    daily_budget = calculate_daily_budget(campaign)

    remaining = daily_budget - campaign.spent_today

    return max(0.0, remaining)


def get_remaining_monthly_budget(
    campaign: CampaignDB,
) -> float:

    reset_monthly_if_needed(campaign)

    remaining = (
        campaign.monthly_budget
        - campaign.spent_this_month
    )

    return max(0.0, remaining)


def get_remaining_discovery_budget(
    campaign: CampaignDB,
) -> float:

    remaining = (
        campaign.discovery_budget
        - campaign.discovery_spent
    )

    return max(0.0, remaining)


# ============================================================
# SAFETY VALIDATION
# ============================================================

def validate_spend(
    campaign: CampaignDB,
    amount: float,
    spending_type: str = "normal",
):
    """
    Returns:

        (True, "approved")

    or

        (False, "reason")
    """

    if (
        isinstance(amount, bool)
        or not isinstance(amount, (int, float))
        or not math.isfinite(amount)
    ):
        return False, "Spend amount must be a finite number."

    if spending_type not in {"normal", "discovery"}:
        return False, "Invalid spending type."

    if amount <= 0:
        return False, "Spend amount must be greater than zero."

    if campaign.status != "active":
        return False, "Campaign is not active."

    reset_daily_if_needed(campaign)
    reset_monthly_if_needed(campaign)

    daily_remaining = get_remaining_daily_budget(campaign)
    monthly_remaining = get_remaining_monthly_budget(campaign)

    # --------------------------------------------------------
    # Discovery budget
    # --------------------------------------------------------

    if spending_type == "discovery":

        discovery_remaining = (
            get_remaining_discovery_budget(campaign)
        )

        if amount > discovery_remaining:
            return (
                False,
                "Discovery budget exceeded."
            )

        # Discovery spending still counts toward the
        # campaign's actual advertising budget.
        if amount > daily_remaining:
            return (
                False,
                "Daily advertising limit exceeded."
            )

        if amount > monthly_remaining:
            return (
                False,
                "Monthly advertising limit exceeded."
            )

        maximum_single_allocation = (
            daily_remaining * MAX_SINGLE_ALLOCATION_PERCENT
        )

        if amount > maximum_single_allocation:
            return (
                False,
                "Allocation is too large for a single decision."
            )

        return True, "approved"

    # --------------------------------------------------------
    # Normal advertising budget
    # --------------------------------------------------------

    if amount > daily_remaining:
        return (
            False,
            "Daily advertising limit exceeded."
        )

    if amount > monthly_remaining:
        return (
            False,
            "Monthly advertising limit exceeded."
        )

    # Prevent one optimizer decision from consuming
    # an excessive amount of the remaining daily budget.
    if daily_remaining > 0:

        maximum_single_allocation = (
            daily_remaining
            * MAX_SINGLE_ALLOCATION_PERCENT
        )

        if amount > maximum_single_allocation:
            return (
                False,
                "Allocation is too large for a single decision."
            )

    return True, "approved"


# ============================================================
# RECORD APPROVED SPENDING
# ============================================================

def record_spend(
    db: Session,
    campaign: CampaignDB,
    amount: float,
    platform: str = "unknown",
    country: str | None = None,
    spending_type: str = "normal",
):
    """
    Atomically validates and records an approved spending decision.

    This records a decision only. It does not spend money on an
    external advertising platform.
    """

    try:
        campaign_id = campaign.id
        dialect = db.get_bind().dialect.name

        if dialect == "sqlite":
            # Acquire SQLite's write lock before reading budget counters.
            result = db.execute(
                update(CampaignDB)
                .where(CampaignDB.id == campaign_id)
                .values(id=CampaignDB.id)
                .execution_options(synchronize_session=False)
            )

            if result.rowcount != 1:
                raise ValueError("Campaign was not found.")

            db.refresh(campaign)

        else:
            # Acquire a row-level lock on databases that support it.
            locked_campaign = (
                db.query(CampaignDB)
                .filter(CampaignDB.id == campaign_id)
                .with_for_update()
                .populate_existing()
                .first()
            )

            if locked_campaign is None:
                raise ValueError("Campaign was not found.")

            campaign = locked_campaign

        # Refresh budget periods before validating the allocation.
        reset_daily_if_needed(campaign)
        reset_monthly_if_needed(campaign)

        approved, reason = validate_spend(
            campaign=campaign,
            amount=amount,
            spending_type=spending_type,
        )

        if not approved:
            raise ValueError(reason)

        campaign.spent_today += amount
        campaign.spent_this_month += amount

        if spending_type == "discovery":
            campaign.discovery_spent += amount

        transaction = SpendingTransactionDB(
            campaign_id=campaign.id,
            amount=amount,
            platform=platform,
            country=country,
            spending_type=spending_type,
        )

        db.add(transaction)
        db.commit()
        db.refresh(campaign)
        db.refresh(transaction)

        return transaction

    except OperationalError as exc:
        db.rollback()
        raise ValueError(
            "Spending could not safely acquire the database lock. "
            "Please retry the request."
        ) from exc

    except Exception:
        db.rollback()
        raise


# ============================================================
# EMERGENCY CONTROLS
# ============================================================

def pause_campaign(campaign: CampaignDB):
    campaign.status = "paused"


def emergency_pause_campaign(campaign: CampaignDB):
    campaign.status = "emergency_paused"


def resume_campaign(campaign: CampaignDB):

    if campaign.status in {
        "paused",
        "emergency_paused",
    }:
        campaign.status = "active"


# ============================================================
# SAFETY SUMMARY
# ============================================================

def get_safety_summary(
    campaign: CampaignDB,
):

    reset_daily_if_needed(campaign)
    reset_monthly_if_needed(campaign)

    daily_budget = calculate_daily_budget(campaign)

    return {
        "campaign_id": campaign.id,
        "status": campaign.status,

        "daily_budget": round(
            daily_budget,
            2,
        ),

        "spent_today": round(
            campaign.spent_today,
            2,
        ),

        "remaining_today": round(
            get_remaining_daily_budget(campaign),
            2,
        ),

        "monthly_budget": round(
            campaign.monthly_budget,
            2,
        ),

        "spent_this_month": round(
            campaign.spent_this_month,
            2,
        ),

        "remaining_this_month": round(
            get_remaining_monthly_budget(campaign),
            2,
        ),

        "discovery_budget": round(
            campaign.discovery_budget,
            2,
        ),

        "discovery_spent": round(
            campaign.discovery_spent,
            2,
        ),

        "discovery_remaining": round(
            get_remaining_discovery_budget(campaign),
            2,
        ),

        "safe_to_spend": (
            campaign.status == "active"
            and get_remaining_daily_budget(campaign) > 0
            and get_remaining_monthly_budget(campaign) > 0
        ),
    }
