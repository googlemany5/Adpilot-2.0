from typing import Any

from sqlalchemy.orm import Session

from database import CampaignDB
from safety import (
    validate_spend,
    get_safety_summary,
)


# ============================================================
# BUDGET CONTROLLER
# ============================================================

class BudgetController:

    """
    Central safety gate between AdPilot's optimization logic
    and advertising-platform execution.

    The optimizer can REQUEST a budget.

    The controller decides whether that request is allowed.
    """

    def __init__(
        self,
        db: Session,
        campaign: CampaignDB,
    ):

        self.db = db
        self.campaign = campaign

    # ========================================================
    # APPROVE ALLOCATION
    # ========================================================

    def approve_allocation(
        self,
        requested_amount: float,
        spending_type: str = "normal",
    ):

        approved, reason = validate_spend(
            campaign=self.campaign,
            amount=requested_amount,
            spending_type=spending_type,
        )

        summary = get_safety_summary(
            self.campaign
        )

        return {
            "approved": approved,
            "reason": reason,
            "requested_amount": round(
                requested_amount,
                2,
            ),
            "safety": summary,
        }

    # ========================================================
    # CLAMP ALLOCATION
    # ========================================================

    def safe_allocation_amount(
        self,
        requested_amount: float,
        spending_type: str = "normal",
    ) -> float:

        if requested_amount <= 0:
            return 0.0

        summary = get_safety_summary(
            self.campaign
        )

        if spending_type == "discovery":

            maximum = min(
                summary["remaining_today"],
                summary["remaining_this_month"],
                summary["discovery_remaining"],
            )

        else:

            maximum = min(
                summary["remaining_today"],
                summary["remaining_this_month"],
            )

        return round(
            max(
                0.0,
                min(
                    requested_amount,
                    maximum,
                ),
            ),
            2,
        )

    # ========================================================
    # BUILD EXECUTION REQUEST
    # ========================================================

    def build_execution_request(
        self,
        allocation: dict[str, Any],
    ):

        requested_amount = float(
            allocation.get(
                "budget",
                0,
            )
        )

        spending_type = allocation.get(
            "spending_type",
            "normal",
        )

        safe_amount = self.safe_allocation_amount(
            requested_amount,
            spending_type,
        )

        approval = self.approve_allocation(
            safe_amount,
            spending_type,
        )

        return {
            "campaign_id": self.campaign.id,

            "platform": allocation.get(
                "platform",
                "unknown",
            ),

            "country": allocation.get(
                "country",
            ),

            "region": allocation.get(
                "region",
            ),

            "audience": allocation.get(
                "audience",
            ),

            "day_of_week": allocation.get(
                "day_of_week",
            ),

            "hour": allocation.get(
                "hour",
            ),

            "requested_budget": round(
                requested_amount,
                2,
            ),

            "approved_budget": (
                safe_amount
                if approval["approved"]
                else 0.0
            ),

            "approved": approval["approved"],

            "reason": approval["reason"],

            "spending_type": spending_type,

            # This remains False until an actual platform
            # executor has successfully submitted the spend.
            "platform_execution": False,
        }


# ============================================================
# BATCH ALLOCATION SAFETY
# ============================================================

def validate_allocation_batch(
    db: Session,
    campaign: CampaignDB,
    allocations: list[dict[str, Any]],
):

    controller = BudgetController(
        db=db,
        campaign=campaign,
    )

    results = []

    total_requested = 0.0
    total_approved = 0.0

    for allocation in allocations:

        requested = float(
            allocation.get(
                "budget",
                0,
            )
        )

        total_requested += requested

        result = controller.build_execution_request(
            allocation
        )

        total_approved += result[
            "approved_budget"
        ]

        results.append(result)

    return {
        "campaign_id": campaign.id,
        "total_requested": round(
            total_requested,
            2,
        ),
        "total_approved": round(
            total_approved,
            2,
        ),
        "allocations": results,
    }
