"""AdPilot Alerts v1: read-only alerts for campaign health."""

import math


def _number(value, field):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be a finite, non-negative number.")

    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(
            f"{field} must be a finite, non-negative number."
        ) from exc

    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{field} must be a finite, non-negative number.")

    return number


def analyze_campaign_alerts(campaign, experiments=None, recommendations=None):
    """Return actionable alerts without changing campaign data."""

    if not isinstance(campaign, dict):
        raise ValueError("campaign must be a dictionary.")

    if experiments is None:
        experiments = []
    if recommendations is None:
        recommendations = []

    if not isinstance(experiments, list):
        raise ValueError("experiments must be a list.")
    if not isinstance(recommendations, list):
        raise ValueError("recommendations must be a list.")

    alerts = []

    def add_alert(code, severity, title, message, action):
        alerts.append({
            "code": code,
            "severity": severity,
            "title": title,
            "message": message,
            "recommended_action": action,
        })

    status = str(campaign.get("status") or "").strip().lower()

    if status == "emergency_paused":
        add_alert(
            "CAMPAIGN_EMERGENCY_PAUSED",
            "critical",
            "Campaign emergency-paused",
            "The campaign is marked emergency_paused.",
            "Review the reason for the pause and resolve safety issues before considering reactivation.",
        )
    elif status == "paused":
        add_alert(
            "CAMPAIGN_PAUSED",
            "info",
            "Campaign is paused",
            "The campaign is currently marked paused.",
            "Review whether the pause is intentional.",
        )

    monthly_budget = _number(
        campaign.get("monthly_budget", 0), "monthly_budget"
    )
    month_spend = _number(
        campaign.get("spent_this_month", 0), "spent_this_month"
    )
    discovery_budget = _number(
        campaign.get("discovery_budget", 0), "discovery_budget"
    )
    discovery_spend = _number(
        campaign.get("discovery_spent", 0), "discovery_spent"
    )

    if month_spend > monthly_budget:
        add_alert(
            "MONTHLY_BUDGET_EXCEEDED",
            "critical",
            "Monthly budget exceeded",
            "Recorded monthly spend is greater than the configured monthly budget.",
            "Pause further spending through the existing safety controls and audit spend records.",
        )
    elif monthly_budget > 0 and month_spend >= monthly_budget * 0.9:
        add_alert(
            "MONTHLY_BUDGET_NEAR_LIMIT",
            "warning",
            "Monthly budget nearly used",
            "Recorded monthly spend has reached at least 90% of the monthly budget.",
            "Review remaining budget and pacing before authorizing any additional spend.",
        )

    if discovery_spend > discovery_budget:
        add_alert(
            "DISCOVERY_BUDGET_EXCEEDED",
            "critical",
            "Discovery budget exceeded",
            "Recorded discovery spend is greater than its configured budget.",
            "Stop additional discovery allocations through the existing safety controls and audit the records.",
        )
    elif discovery_budget > 0 and discovery_spend >= discovery_budget * 0.9:
        add_alert(
            "DISCOVERY_BUDGET_NEAR_LIMIT",
            "warning",
            "Discovery budget nearly used",
            "Recorded discovery spend has reached at least 90% of the discovery budget.",
            "Review experiment results before allocating more discovery budget.",
        )

    tracking_issues = 0
    for experiment in experiments:
        if not isinstance(experiment, dict):
            raise ValueError("Each experiment must be a dictionary.")

        if experiment.get("revenue") is None or experiment.get("conversions") is None:
            tracking_issues += 1

    if tracking_issues:
        add_alert(
            "EXPERIMENT_TRACKING_INCOMPLETE",
            "warning",
            "Experiment tracking incomplete",
            f"{tracking_issues} experiment(s) are missing revenue or conversion data.",
            "Check conversion events, analytics integration, and attribution before trusting performance estimates.",
        )

    incomplete_profit = sum(
        1 for recommendation in recommendations
        if isinstance(recommendation, dict)
        and recommendation.get("recommendation") == "collect_cost_data"
    )

    if incomplete_profit:
        add_alert(
            "PROFIT_DATA_INCOMPLETE",
            "warning",
            "Profit data needs attention",
            f"{incomplete_profit} profit report(s) indicate missing cost or performance data.",
            "Supply verified revenue, ad spend, and relevant cost data before judging profitability.",
        )

    rejected = sum(
        1 for recommendation in recommendations
        if isinstance(recommendation, dict)
        and recommendation.get("status") == "rejected"
    )

    if rejected:
        add_alert(
            "RECOMMENDATIONS_REJECTED",
            "info",
            "Recommendations were rejected",
            f"{rejected} recommendation(s) were rejected.",
            "Review rejection reasons to improve future recommendations.",
        )

    severity_order = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda alert: severity_order[alert["severity"]])

    return {
        "engine": "alert_engine_v1",
        "campaign_id": campaign.get("id"),
        "alert_count": len(alerts),
        "alerts": alerts,
        "mode": "read_only",
        "campaign_modified": False,
        "spending_executed": False,
    }
