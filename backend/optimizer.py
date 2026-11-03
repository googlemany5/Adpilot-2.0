from datetime import datetime, timezone
from typing import List, Dict, Any
import math


# ============================================================
# ADPILOT OPTIMIZATION ENGINE
# ============================================================

# These are intentionally conservative prototype values.
# Later they will be replaced by ML/statistical models.

MIN_DATA_POINTS = 1

HIGH_ROAS = 3.0
MEDIUM_ROAS = 1.5


# ============================================================
# SAFE NUMBER HELPERS
# ============================================================

def _finite_nonnegative(value: Any, field: str) -> float:
    """Require a finite, non-negative numeric value; reject booleans."""
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be a finite non-negative number.")

    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(
            f"{field} must be a finite non-negative number."
        ) from exc

    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{field} must be a finite non-negative number.")

    return number


def safe_divide(numerator: float, denominator: float) -> float:
    numerator = _finite_nonnegative(numerator, "numerator")
    denominator = _finite_nonnegative(denominator, "denominator")

    if denominator == 0:
        return 0.0

    result = numerator / denominator
    if not math.isfinite(result):
        raise ValueError("Division result must be finite.")
    return result


# ============================================================
# EXPERIMENT METRICS
# ============================================================

def calculate_experiment_metrics(experiment) -> Dict[str, Any]:
    if experiment is None:
        raise ValueError("experiment is required.")

    revenue = _finite_nonnegative(experiment.revenue, "revenue")
    spent = _finite_nonnegative(experiment.spent, "spent")
    conversions = _finite_nonnegative(experiment.conversions, "conversions")
    clicks = _finite_nonnegative(experiment.clicks, "clicks")

    roas = safe_divide(revenue, spent)
    conversion_rate = safe_divide(conversions, clicks)
    cost_per_conversion = safe_divide(spent, conversions)

    return {
        "experiment_id": experiment.id,
        "name": experiment.name,
        "type": experiment.experiment_type,
        "target": experiment.target,
        "platform": experiment.platform,
        "budget": experiment.budget,
        "spent": spent,
        "clicks": clicks,
        "conversions": conversions,
        "revenue": revenue,
        "roas": roas,
        "conversion_rate": conversion_rate,
        "cost_per_conversion": cost_per_conversion,
        "status": experiment.status,
    }


# ============================================================
# RANK EXPERIMENTS
# ============================================================

def rank_experiments(experiments) -> List[Dict[str, Any]]:
    if not isinstance(experiments, (list, tuple)):
        raise ValueError("experiments must be a list or tuple.")

    ranked = []

    for experiment in experiments:
        metrics = calculate_experiment_metrics(experiment)

        sample_factor = min(
            max(metrics["clicks"] / 25, 0.25),
            1.0,
        )

        score = metrics["roas"] * sample_factor
        if not math.isfinite(score):
            raise ValueError("Experiment score must be finite.")

        metrics["score"] = score

        sufficient_evidence = (
            metrics["spent"] >= 25
            and metrics["clicks"] >= 20
            and metrics["conversions"] >= 3
        )

        if score >= HIGH_ROAS and sufficient_evidence:
            metrics["recommendation"] = "expand"
        elif score >= MEDIUM_ROAS:
            metrics["recommendation"] = "test_more"
        else:
            metrics["recommendation"] = "reduce"

        ranked.append(metrics)

    ranked.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    return ranked


# ============================================================
# MARKET EXPANSION
# ============================================================

def choose_market_expansion(
    ranked_experiments,
) -> List[Dict[str, Any]]:

    opportunities = []

    for experiment in ranked_experiments:

        if experiment["recommendation"] != "expand":
            continue

        opportunities.append(
            {
                "source_experiment_id":
                    experiment["experiment_id"],

                "target":
                    experiment["target"],

                "platform":
                    experiment["platform"],

                "roas":
                    experiment["roas"],

                "score":
                    experiment["score"],

                "next_stage":
                    "state_or_region",
            }
        )

    return opportunities


# ============================================================
# STATE / PROVINCE EXPANSION
# ============================================================

def choose_state_expansion(
    ranked_experiments,
) -> List[Dict[str, Any]]:

    opportunities = []

    for experiment in ranked_experiments:

        if experiment["recommendation"] != "expand":
            continue

        opportunities.append(
            {
                "target":
                    experiment["target"],

                "platform":
                    experiment["platform"],

                "roas":
                    experiment["roas"],

                "next_stage":
                    "region",
            }
        )

    return opportunities


# ============================================================
# REGION EXPANSION
# ============================================================

def choose_region_expansion(
    ranked_experiments,
) -> List[Dict[str, Any]]:

    opportunities = []

    for experiment in ranked_experiments:

        if experiment["recommendation"] != "expand":
            continue

        opportunities.append(
            {
                "target":
                    experiment["target"],

                "platform":
                    experiment["platform"],

                "roas":
                    experiment["roas"],

                "next_stage":
                    "audience",
            }
        )

    return opportunities


# ============================================================
# AUDIENCE EXPANSION
# ============================================================

def choose_audience_expansion(
    ranked_experiments,
) -> List[Dict[str, Any]]:

    opportunities = []

    for experiment in ranked_experiments:

        if experiment["recommendation"] != "expand":
            continue

        opportunities.append(
            {
                "target":
                    experiment["target"],

                "platform":
                    experiment["platform"],

                "roas":
                    experiment["roas"],

                "next_stage":
                    "time",
            }
        )

    return opportunities


# ============================================================
# TIME OPTIMIZATION
# ============================================================

def rank_time_opportunities(
    opportunities,
) -> List[Dict[str, Any]]:

    ranked = []

    for opportunity in opportunities:

        spend = opportunity.get(
            "spend",
            0,
        )

        revenue = opportunity.get(
            "revenue",
            0,
        )

        roas = safe_divide(
            revenue,
            spend,
        )

        ranked.append(
            {
                **opportunity,
                "roas": roas,
            }
        )

    ranked.sort(
        key=lambda item: item["roas"],
        reverse=True,
    )

    return ranked


# ============================================================
# FINAL ALLOCATION
# ============================================================

def calculate_final_allocation(
    opportunities: List[Dict[str, Any]],
    available_budget: float,
) -> List[Dict[str, Any]]:
    available_budget = _finite_nonnegative(
        available_budget, "available_budget"
    )

    if not isinstance(opportunities, list):
        raise ValueError("opportunities must be a list.")

    if available_budget == 0:
        return []

    positive = []

    for opportunity in opportunities:
        if not isinstance(opportunity, dict):
            raise ValueError("Each opportunity must be a dictionary.")

        expected_roas = _finite_nonnegative(
            opportunity.get("expected_roas", 0),
            "expected_roas",
        )

        if expected_roas > 0:
            positive.append((opportunity, expected_roas))

    if not positive:
        return []

    total_score = sum(score for _, score in positive)

    if not math.isfinite(total_score) or total_score <= 0:
        raise ValueError("Total allocation score must be finite and positive.")

    allocations = []

    for opportunity, expected_roas in positive:
        allocation = available_budget * expected_roas / total_score

        if not math.isfinite(allocation):
            raise ValueError("Calculated allocation must be finite.")

        allocations.append({
            **opportunity,
            "recommended_budget": round(allocation, 2),
        })

    allocated = sum(
        item["recommended_budget"] for item in allocations
    )

    difference = round(available_budget - allocated, 2)

    allocations[0]["recommended_budget"] = round(
        allocations[0]["recommended_budget"] + difference,
        2,
    )

    return allocations


# ============================================================
# SAFETY VALIDATION
# ============================================================

def validate_allocation(
    allocation: Dict[str, Any],
    remaining_budget: float,
) -> Dict[str, Any]:
    if not isinstance(allocation, dict):
        raise ValueError("allocation must be a dictionary.")

    requested = _finite_nonnegative(
        allocation.get("recommended_budget", 0),
        "recommended_budget",
    )
    remaining = _finite_nonnegative(
        remaining_budget,
        "remaining_budget",
    )

    approved = min(requested, remaining)

    return {
        "approved_budget": round(approved, 2),
        "requested_budget": round(requested, 2),
        "within_budget": requested <= remaining,
        "blocked": approved <= 0,
    }


# ============================================================
# CONTINUOUS OPTIMIZATION
# ============================================================

def continuous_optimization(
    opportunities: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not isinstance(opportunities, list):
        raise ValueError("opportunities must be a list.")

    recommendations = []

    for opportunity in opportunities:
        if not isinstance(opportunity, dict):
            raise ValueError("Each opportunity must be a dictionary.")

        roas = _finite_nonnegative(
            opportunity.get("expected_roas", 0),
            "expected_roas",
        )
        current_budget = _finite_nonnegative(
            opportunity.get("current_budget", 0),
            "current_budget",
        )

        if roas >= HIGH_ROAS:
            action = "increase"
            multiplier = 1.20
        elif roas >= MEDIUM_ROAS:
            action = "maintain"
            multiplier = 1.00
        else:
            action = "decrease"
            multiplier = 0.50

        recommended_budget = current_budget * multiplier

        if not math.isfinite(recommended_budget):
            raise ValueError("Recommended budget must be finite.")

        recommendations.append({
            **opportunity,
            "action": action,
            "recommended_budget": round(recommended_budget, 2),
        })

    return recommendations


# ============================================================
# COMPLETE OPTIMIZATION PIPELINE
# ============================================================

def run_optimization_pipeline(
    experiments,
    available_budget: float,
) -> Dict[str, Any]:

    ranked = rank_experiments(
        experiments
    )

    market_expansion = (
        choose_market_expansion(ranked)
    )

    state_expansion = (
        choose_state_expansion(ranked)
    )

    region_expansion = (
        choose_region_expansion(ranked)
    )

    audience_expansion = (
        choose_audience_expansion(ranked)
    )

    allocation_candidates = []

    for experiment in ranked:

        if experiment["recommendation"] == "reduce":
            continue

        allocation_candidates.append(
            {
                "experiment_id":
                    experiment["experiment_id"],

                "target":
                    experiment["target"],

                "platform":
                    experiment["platform"],

                "expected_roas":
                    experiment["roas"],

                "confidence":
                    min(
                        max(
                            experiment["clicks"]
                            / 100,
                            0.1,
                        ),
                        1.0,
                    ),
            }
        )

    final_allocations = calculate_final_allocation(
        allocation_candidates,
        available_budget,
    )

    return {
        "generated_at":
            datetime.now(timezone.utc).replace(tzinfo=None),

        "ranked_experiments":
            ranked,

        "market_expansion":
            market_expansion,

        "state_expansion":
            state_expansion,

        "region_expansion":
            region_expansion,

        "audience_expansion":
            audience_expansion,

        "final_allocations":
            final_allocations,
    }
