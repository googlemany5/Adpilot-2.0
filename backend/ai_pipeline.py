from typing import Any

from sqlalchemy.orm import Session

from database import CampaignDB, AIDecisionDB
from optimizer import run_optimization_pipeline
from budget_controller import validate_allocation_batch


# ============================================================
# AI DECISION PIPELINE
# ============================================================

def prepare_decision_fields(allocation: dict, safety: dict) -> dict:
    import math
    def amount(value):
        try:
            n = float(value)
            return round(n, 2) if math.isfinite(n) and n >= 0 else 0.0
        except (TypeError, ValueError, OverflowError):
            return 0.0
    requested = amount(safety.get("requested_budget", allocation.get("budget", allocation.get("recommended_budget", 0))))
    approved = amount(safety.get("approved_budget", 0))
    can_review = bool(safety.get("approved")) and approved > 0
    budget = approved if can_review else 0.0
    reason = (str(allocation.get("reason", "Optimizer recommendation")) + " Requested budget: $" + format(requested, ".2f") + "; safety-approved budget: $" + format(budget, ".2f") + ". Safety result: " + str(safety.get("reason", "No reason provided.")))
    return {"status": "shadow" if can_review else "blocked", "recommended_budget": budget, "reason": reason}


def run_ai_pipeline(
    db: Session,
    campaign: CampaignDB,
    experiments: list[Any],
):
    """
    Complete decision flow:

        Experiment data
              ↓
        Optimizer
              ↓
        Allocation validation
              ↓
        AI decision log
              ↓
        Shadow Mode / execution layer
    """

    optimization = run_optimization_pipeline(
        experiments=experiments,
        available_budget=max(
            0.0,
            float(campaign.monthly_budget)
            - float(campaign.spent_this_month or 0),
        ),
    )

    allocations = optimization.get(
        "final_allocations",
        [],
    )

    # The optimizer uses recommended_budget; the safety controller
    # accepts budget. Normalize the shape before validation.
    allocations = [
        {
            **allocation,
            "budget": allocation.get(
                "budget",
                allocation.get("recommended_budget", 0),
            ),
        }
        for allocation in allocations
    ]

    safety_result = validate_allocation_batch(
        db=db,
        campaign=campaign,
        allocations=allocations,
    )

    logged_decisions = []
    safety_allocations = safety_result.get("allocations", [])

    for index, allocation in enumerate(allocations):
        safety = (
            safety_allocations[index]
            if index < len(safety_allocations)
            else {}
        )
        fields = prepare_decision_fields(allocation, safety)

        decision = AIDecisionDB(
            campaign_id=campaign.id,
            decision_type="allocation",
            platform=allocation.get("platform", "unknown"),
            country=allocation.get("country"),
            region=allocation.get("region"),
            audience=allocation.get("audience"),
            day_of_week=allocation.get("day_of_week"),
            hour=allocation.get("hour"),
            recommended_budget=fields["recommended_budget"],
            expected_roas=float(allocation.get("expected_roas", 0)),
            confidence=float(allocation.get("confidence", 0)),
            reason=fields["reason"],
            status=fields["status"],
        )
        db.add(decision)
        logged_decisions.append(decision)

    db.commit()

    return {
        "campaign_id": campaign.id,
        "mode": "shadow",
        "optimization": optimization,
        "safety": safety_result,
        "decisions_logged": len(
            logged_decisions
        ),
        "message": (
            "AI decisions generated in Shadow Mode. "
            "No advertising platform spending was executed."
        ),
    }
