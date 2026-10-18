from datetime import datetime
from typing import List, Dict, Any


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

def safe_divide(
    numerator: float,
    denominator: float,
) -> float:

    if denominator <= 0:
        return 0.0

    return numerator / denominator


# ============================================================
# EXPERIMENT METRICS
# ============================================================

def calculate_experiment_metrics(
    experiment,
) -> Dict[str, Any]:

    roas = safe_divide(
        experiment.revenue,
        experiment.spent,
    )

    conversion_rate = safe_divide(
        experiment.conversions,
        experiment.clicks,
    )

    cost_per_conversion = safe_divide(
        experiment.spent,
        experiment.conversions,
    )

    return {
        "experiment_id": experiment.id,
        "name": experiment.name,
        "type": experiment.experiment_type,
        "target": experiment.target,
        "platform": experiment.platform,
        "budget": experiment.budget,
        "spent": experiment.spent,
        "clicks": experiment.clicks,
        "conversions": experiment.conversions,
        "revenue": experiment.revenue,
        "roas": roas,
        "conversion_rate": conversion_rate,
        "cost_per_conversion": cost_per_conversion,
        "status": experiment.status,
    }


# ============================================================
# RANK EXPERIMENTS
# ============================================================

def rank_experiments(
    experiments,
) -> List[Dict[str, Any]]:

    ranked = []

    for experiment in experiments:

        metrics = calculate_experiment_metrics(
            experiment
        )

        if experiment.spent < 0:
            continue

        # Basic prototype score.
        #
        # ROAS is the main signal, but we also reward
        # conversions and penalize extremely small samples.

        sample_factor = min(
            max(experiment.clicks / 25, 0.25),
            1.0,
        )

        score = (
            metrics["roas"]
            * sample_factor
        )

        metrics["score"] = score

        if score >= HIGH_ROAS:
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

    if available_budget <= 0:
        return []

    positive = [
        opportunity
        for opportunity in opportunities
        if opportunity.get(
            "expected_roas",
            0,
        ) > 0
    ]

    if not positive:
        return []

    total_score = sum(
        max(
            opportunity.get(
                "expected_roas",
                0,
            ),
            0,
        )
        for opportunity in positive
    )

    if total_score <= 0:
        return []

    allocations = []

    for opportunity in positive:

        expected_roas = max(
            opportunity.get(
                "expected_roas",
                0,
            ),
            0,
        )

        allocation = (
            available_budget
            * expected_roas
            / total_score
        )

        allocations.append(
            {
                **opportunity,
                "recommended_budget":
                    round(allocation, 2),
            }
        )

    # Correct rounding difference.
    allocated = sum(
        item["recommended_budget"]
        for item in allocations
    )

    difference = round(
        available_budget - allocated,
        2,
    )

    if allocations:
        allocations[0][
            "recommended_budget"
        ] = round(
            allocations[0]["recommended_budget"]
            + difference,
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

    requested = allocation.get(
        "recommended_budget",
        0,
    )

    if requested < 0:
        requested = 0

    approved = min(
        requested,
        max(remaining_budget, 0),
    )

    return {
        "approved_budget":
            round(approved, 2),

        "requested_budget":
            round(requested, 2),

        "within_budget":
            requested <= remaining_budget,

        "blocked":
            approved <= 0,
    }


# ============================================================
# CONTINUOUS OPTIMIZATION
# ============================================================

def continuous_optimization(
    opportunities: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:

    recommendations = []

    for opportunity in opportunities:

        roas = opportunity.get(
            "expected_roas",
            0,
        )

        current_budget = opportunity.get(
            "current_budget",
            0,
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

        recommended_budget = (
            current_budget
            * multiplier
        )

        recommendations.append(
            {
                **opportunity,
                "action": action,
                "recommended_budget":
                    round(
                        recommended_budget,
                        2,
                    ),
            }
        )

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
            datetime.utcnow(),

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
