"""AdPilot experiment planner.

Creates a budget allocation plan for market tests.
Does not launch campaigns or execute advertising spend.
"""

from decimal import Decimal, ROUND_DOWN
from typing import Any
import math


CENT = Decimal("0.01")
MIN_TEST_BUDGET = Decimal("1.00")


def money(value: Any) -> Decimal:
    """Convert a value to a non-negative dollar amount."""
    try:
        amount = Decimal(str(value))
    except Exception as exc:
        raise ValueError("Budget must be a valid number.") from exc

    if not amount.is_finite() or amount < 0:
        raise ValueError("Budget must be finite and non-negative.")

    return amount.quantize(CENT, rounding=ROUND_DOWN)


def create_experiment_plan(
    discovery_budget: Any,
    market_discovery: dict,
    round_budget: Any = None,
    max_experiments: int = 3,
) -> dict:
    """Allocate a testing round across the highest-ranked eligible markets."""
    total_budget = money(discovery_budget)
    available_round_budget = (
        total_budget if round_budget is None else money(round_budget)
    )

    if available_round_budget > total_budget:
        raise ValueError("Round budget cannot exceed discovery budget.")

    if not isinstance(max_experiments, int) or isinstance(max_experiments, bool) or max_experiments < 1:
        raise ValueError("max_experiments must be a positive integer.")

    shortlist = market_discovery.get("shortlist", [])
    candidates = [
        item for item in shortlist
        if item.get("eligible_for_experiment") is True
    ][:max_experiments]

    # Don't create tests that cannot receive at least $1 each.
    affordable_count = int(available_round_budget // MIN_TEST_BUDGET)
    candidates = candidates[:affordable_count]

    if not candidates:
        return {
            "planner": "experiment_budget_planner_v1",
            "discovery_budget": float(total_budget),
            "round_budget": float(available_round_budget),
            "planned_total": 0.0,
            "unallocated_budget": float(available_round_budget),
            "experiments": [],
            "message": "No eligible markets can be funded at $1 or more each.",
            "spending_executed": False,
        }

    scores = []
    for item in candidates:
        try:
            score = float(item.get("score", 0))
        except (TypeError, ValueError, OverflowError):
            score = 0.0
        if not math.isfinite(score):
            score = 0.0
        scores.append(max(0.0, score))
    score_total = sum(scores)

    if score_total <= 0:
        scores = [1.0] * len(candidates)
        score_total = float(len(candidates))

    # First calculate proportional shares rounded down to cents.
    allocations = [
        (available_round_budget * Decimal(str(score / score_total)))
        .quantize(CENT, rounding=ROUND_DOWN)
        for score in scores
    ]

    # Distribute remaining cents by largest fractional remainder.
    remaining = available_round_budget - sum(allocations)
    fractions = [
        (available_round_budget * Decimal(str(score / score_total))) - allocation
        for score, allocation in zip(scores, allocations)
    ]

    order = sorted(
        range(len(candidates)),
        key=lambda index: fractions[index],
        reverse=True,
    )

    cents_left = int(remaining / CENT)
    for index in order[:cents_left]:
        allocations[index] += CENT

    experiments = []
    for market, score, allocation in zip(candidates, scores, allocations):
        experiments.append({
            "experiment_name": f"Market test - {market.get('country', 'Unknown')}",
            "experiment_type": "country",
            "country": market.get("country", "Unknown"),
            "region": market.get("region"),
            "platform": None,
            "planned_budget": float(allocation),
            "market_score": round(score, 2),
            "status": "planned",
            "success_metrics": [
                "revenue",
                "conversions",
                "cost_per_conversion",
                "return_on_ad_spend",
            ],
        })

    planned_total = sum(allocations)
    unallocated = total_budget - planned_total

    return {
        "planner": "experiment_budget_planner_v1",
        "discovery_budget": float(total_budget),
        "round_budget": float(available_round_budget),
        "planned_total": float(planned_total),
        "unallocated_budget": float(unallocated),
        "experiments": experiments,
        "message": (
            "Testing plan created. Choose an advertising platform and review "
            "the plan before any campaign is launched."
        ),
        "spending_executed": False,
    }
