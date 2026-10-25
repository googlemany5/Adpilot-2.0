"""AdPilot Forecast Engine v1: conservative, read-only campaign forecasts."""

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


def forecast_campaign(campaign, historical_results):
    """
    Estimate end-of-month revenue using historical ROAS.

    historical_results must contain dictionaries with spend and revenue.
    These results should represent the current month's performance.
    This function does not change campaign data or execute spending.
    """

    if not isinstance(campaign, dict):
        raise ValueError("campaign must be a dictionary.")

    if not isinstance(historical_results, list):
        raise ValueError("historical_results must be a list.")

    monthly_budget = _number(
        campaign.get("monthly_budget", 0), "monthly_budget"
    )
    spent = _number(
        campaign.get("spent_this_month", 0), "spent_this_month"
    )
    revenue_to_date = _number(
        campaign.get("revenue_this_month", 0), "revenue_this_month"
    )

    if spent > monthly_budget:
        remaining_budget = 0.0
        budget_warning = "Recorded spend already exceeds the monthly budget."
    else:
        remaining_budget = monthly_budget - spent
        budget_warning = None

    total_spend = 0.0
    total_revenue = 0.0

    for index, result in enumerate(historical_results):
        if not isinstance(result, dict):
            raise ValueError(
                f"Historical result {index} must be a dictionary."
            )

        row_spend = _number(result.get("spend"), f"results[{index}].spend")
        row_revenue = _number(
            result.get("revenue"), f"results[{index}].revenue"
        )

        total_spend += row_spend
        total_revenue += row_revenue

        if not math.isfinite(total_spend) or not math.isfinite(total_revenue):
            raise ValueError("Historical totals exceed supported numeric limits.")

    if not math.isfinite(total_spend) or not math.isfinite(total_revenue):
        raise ValueError("Historical totals exceed supported numeric limits.")

    if total_spend > 0:
        historical_roas = total_revenue / total_spend
        if not math.isfinite(historical_roas):
            raise ValueError("Calculated historical ROAS is not finite.")
        historical_roas = round(historical_roas, 4)
    else:
        historical_roas = None

    warnings = []
    if budget_warning:
        warnings.append(budget_warning)

    sample_count = sum(
        1 for row in historical_results
        if float(row.get("spend", 0)) > 0
    )

    if sample_count == 0:
        confidence = "insufficient_data"
        warnings.append(
            "No historical result with positive spend; revenue cannot be forecast."
        )
        projected_remaining_revenue = None
        projected_monthly_revenue = None
        projected_monthly_roas = None
    else:
        if sample_count < 3:
            confidence = "low"
            warnings.append(
                "Very little historical data; results may differ substantially."
            )
        elif sample_count < 10:
            confidence = "medium"
            warnings.append(
                "Forecast is based on a limited sample and assumes past ROAS continues."
            )
        else:
            confidence = "higher_sample_size"
            warnings.append(
                "More observations do not guarantee accuracy; performance can change."
            )

        projected_remaining_revenue = round(
            remaining_budget * historical_roas, 2
        )
        projected_monthly_revenue = round(
            revenue_to_date + projected_remaining_revenue, 2
        )

        projected_total_spend = spent + remaining_budget
        projected_monthly_roas = (
            round(projected_monthly_revenue / projected_total_spend, 4)
            if projected_total_spend > 0
            else None
        )

    return {
        "engine": "forecast_engine_v1",
        "campaign_id": campaign.get("id"),
        "historical_sample_count": sample_count,
        "historical_spend_in_results": round(total_spend, 2),
        "historical_revenue_in_results": round(total_revenue, 2),
        "historical_roas": historical_roas,
        "remaining_budget_estimate": round(remaining_budget, 2),
        "projected_remaining_revenue": projected_remaining_revenue,
        "projected_monthly_revenue": projected_monthly_revenue,
        "projected_monthly_roas": projected_monthly_roas,
        "confidence": confidence,
        "warnings": warnings,
        "mode": "shadow",
        "campaign_modified": False,
        "spending_executed": False,
    }
