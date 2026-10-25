"""Combines market discovery, experiment planning, and performance learning."""

from market_discovery import discover_markets
from experiment_planner import create_experiment_plan
from experiment_learning import learn_from_experiments
from regional_discovery import discover_regions
from performance_analyzer import analyze_performance
from profit_optimizer import optimize_profit


def build_growth_plan(
    campaign,
    markets,
    discovery_budget,
    round_budget=None,
    regions_by_country=None,
    experiment_results=None,
    max_markets=3,
    max_regions=5,
):
    """Build a read-only growth plan from market and experiment evidence."""
    market_report = discover_markets(
        campaign, markets, max_markets=max_markets
    )

    budget_plan = create_experiment_plan(
        discovery_budget=discovery_budget,
        round_budget=round_budget,
        market_discovery=market_report,
        max_experiments=max_markets,
    )

    regional_reports = []
    regions_by_country = regions_by_country or {}

    for selected in market_report.get("shortlist", []):
        country = selected.get("country")
        if not country:
            continue
        region_candidates = regions_by_country.get(country, [])
        if region_candidates:
            regional_reports.append(
                discover_regions(
                    country,
                    region_candidates,
                    max_regions=max_regions,
                )
            )

    if experiment_results is None:
        results = []
    elif isinstance(experiment_results, list):
        results = experiment_results
    else:
        raise ValueError("experiment_results must be a list when supplied.")
    learning_report = learn_from_experiments(results)
    profit_report = optimize_profit(results)
    performance_report = analyze_performance(results)

    actions = [
        "Review market and regional recommendations.",
        "Choose an advertising platform for each proposed test.",
        "Collect actual results before changing budget recommendations.",
    ]

    for result in performance_report["experiments"]:
        if result["assessment"] == "promising":
            actions.append(
                f"Review {result['name']} for a possible controlled follow-up; "
                "do not increase spending without safety approval."
            )
        elif result["assessment"] == "underperforming":
            actions.append(
                f"Review {result['name']} for targeting, creative, or "
                "measurement problems before allocating more budget."
            )

    return {
        "engine": "adpilot_growth_planner_v2",
        "market_discovery": market_report,
        "experiment_budget_plan": budget_plan,
        "regional_discovery": regional_reports,
        "experiment_learning": learning_report,
        "performance_analysis": performance_report,
        "profit_optimization": profit_report,
        "next_actions": actions,
        "spending_executed": False,
        "mode": "shadow",
    }
