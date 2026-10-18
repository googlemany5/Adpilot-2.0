from typing import Any

from sqlalchemy.orm import Session

from database import CampaignDB, AIDecisionDB
from optimizer import run_optimization_pipeline
from budget_controller import validate_allocation_batch


# ============================================================
# AI DECISION PIPELINE
# ============================================================

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

    for allocation in allocations:

        decision = AIDecisionDB(
            campaign_id=campaign.id,
            decision_type="allocation",
            platform=allocation.get(
                "platform",
                "unknown",
            ),
            country=allocation.get(
                "country",
            ),
            region=allocation.get(
                "region",
            ),
            audience=allocation.get(
                "audience",
            ),
            day_of_week=allocation.get(
                "day_of_week",
            ),
            hour=allocation.get(
                "hour",
            ),
            recommended_budget=float(
                allocation.get(
                    "budget",
                    0,
                )
            ),
            expected_roas=float(
                allocation.get(
                    "expected_roas",
                    0,
                )
            ),
            confidence=float(
                allocation.get(
                    "confidence",
                    0,
                )
            ),
            reason=allocation.get(
                "reason",
                "Optimizer recommendation",
            ),
            status="shadow",
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
