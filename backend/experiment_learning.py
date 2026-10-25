"""AdPilot Experiment Learning Engine.

Analyzes observed results and recommends next steps.
Recommendations only: no budget changes or ad launches.
"""

import math
from typing import Any


def _number(value: Any, field: str) -> float:
    """Validate a non-negative finite measurement."""
    if value is None or isinstance(value, bool):
        raise ValueError(f"{field} must be a valid number.")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field} must be a valid number.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite.")
    if number < 0:
        raise ValueError(f"{field} cannot be negative.")
    return number


def _count(value: Any, field: str) -> int:
    """Validate a count as a non-negative whole number."""
    number = _number(value, field)
    if not number.is_integer():
        raise ValueError(f"{field} must be a whole number.")
    return int(number)


def analyze_experiment(experiment: dict) -> dict:
    """Calculate metrics and make an evidence-aware recommendation."""
    if not isinstance(experiment, dict):
        raise ValueError("Each experiment must be a dictionary.")

    spend = _number(experiment.get("spend", 0), "spend")
    revenue_recorded = (
        "revenue" in experiment and experiment.get("revenue") is not None
    )
    revenue = _number(experiment["revenue"], "revenue") if revenue_recorded else 0.0
    conversions = _count(experiment.get("conversions", 0), "conversions")
    clicks = _count(experiment.get("clicks", 0), "clicks")
    impressions = _count(experiment.get("impressions", 0), "impressions")

    if conversions > clicks and clicks > 0:
        raise ValueError("Conversions cannot exceed clicks.")
    if clicks > impressions and impressions > 0:
        raise ValueError("Clicks cannot exceed impressions.")

    roas = revenue / spend if spend > 0 and revenue_recorded else None
    cpcv = spend / conversions if conversions > 0 else None
    conversion_rate = conversions / clicks if clicks > 0 else None
    ctr = clicks / impressions if impressions > 0 else None

    # Evidence quality is separate from performance: a strong ratio based
    # on a small sample is not enough to justify expansion.
    has_minimum_data = spend >= 25 and clicks >= 20
    evidence_score = min(100, round(
        min(spend / 100, 1) * 40
        + min(clicks / 100, 1) * 35
        + min(conversions / 10, 1) * 25,
        1,
    ))

    if spend == 0:
        recommendation = "collect_data"
        reason = "No advertising spend is recorded yet."
    elif not revenue_recorded:
        recommendation = "review_tracking"
        reason = (
            "Revenue data is missing. Verify conversion and revenue tracking "
            "before evaluating performance."
        )
    elif not has_minimum_data:
        recommendation = "test_more"
        reason = (
            "The experiment has limited data. Gather more results before "
            "making a strong budget decision."
        )
    elif roas >= 3.0 and conversions >= 3:
        recommendation = "expand_candidate"
        reason = (
            "ROAS is at least 3.0 with at least three conversions. "
            "Consider a controlled follow-up test after reviewing profit."
        )
    elif roas >= 1.5:
        recommendation = "test_more"
        reason = (
            "Results may justify more testing, but evidence is not strong "
            "enough for automatic expansion."
        )
    else:
        recommendation = "reduce_candidate"
        reason = (
            "ROAS is below 1.5. Review margins, attribution, and campaign "
            "conditions before changing investment."
        )

    if spend > 0 and revenue_recorded and revenue == 0 and has_minimum_data:
        recommendation = "review_tracking"
        reason = (
            "No revenue is recorded despite sufficient spend and clicks. "
            "Verify tracking before deciding to reduce investment."
        )

    return {
        "experiment_id": experiment.get("experiment_id", experiment.get("id")),
        "name": experiment.get("name", experiment.get("experiment_name", "Unnamed experiment")),
        "country": experiment.get("country"),
        "region": experiment.get("region"),
        "platform": experiment.get("platform"),
        "spend": round(spend, 2),
        "revenue": round(revenue, 2) if revenue_recorded else None,
        "revenue_recorded": revenue_recorded,
        "conversions": conversions,
        "clicks": clicks,
        "impressions": impressions,
        "roas": round(roas, 3) if roas is not None else None,
        "cost_per_conversion": round(cpcv, 2) if cpcv is not None else None,
        "conversion_rate": round(conversion_rate, 4) if conversion_rate is not None else None,
        "click_through_rate": round(ctr, 4) if ctr is not None else None,
        "minimum_data_reached": has_minimum_data,
        "evidence_score": evidence_score,
        "recommendation": recommendation,
        "reason": reason,
        "spending_executed": False,
    }


def learn_from_experiments(experiments: list[dict]) -> dict:
    """Rank observed experiments using performance and evidence quality."""
    if not isinstance(experiments, list):
        raise ValueError("experiments must be a list.")

    results = [analyze_experiment(item) for item in experiments]
    results.sort(
        key=lambda item: (
            item["recommendation"] == "expand_candidate",
            item["minimum_data_reached"],
            item["evidence_score"],
            item["roas"] if item["roas"] is not None else -1,
            item["conversions"],
        ),
        reverse=True,
    )

    counts = {}
    for result in results:
        action = result["recommendation"]
        counts[action] = counts.get(action, 0) + 1

    return {
        "engine": "experiment_learning_v2",
        "experiments_analyzed": len(results),
        "recommendation_counts": counts,
        "ranked_results": results,
        "important_note": (
            "Recommendations are based on supplied data, not proof of future "
            "performance. ROAS is not profit. Review margins, attribution, "
            "and tracking before changing budgets."
        ),
        "spending_executed": False,
    }
