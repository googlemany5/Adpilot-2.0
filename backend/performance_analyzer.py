"""Read-only campaign performance analysis for AdPilot."""

import math


def _number(value, default=0.0):
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError, OverflowError):
        return default


def analyze_performance(experiments):
    """Summarize experiment results without executing spending."""
    rows = []
    total_spend = 0.0
    total_revenue = 0.0
    total_profit = 0.0
    has_profit_data = False

    for item in experiments or []:
        if not isinstance(item, dict):
            continue

        spend = max(0.0, _number(item.get("spend", item.get("completed_spend", 0))))
        revenue = max(0.0, _number(item.get("revenue", item.get("completed_revenue", 0))))
        profit_value = item.get("profit")
        has_profit = profit_value is not None
        profit = _number(profit_value) if has_profit else revenue - spend

        roas = revenue / spend if spend > 0 else None
        if spend <= 0:
            assessment = "insufficient_data"
        elif roas >= 3:
            assessment = "promising"
        elif roas >= 1:
            assessment = "needs_more_evidence"
        else:
            assessment = "underperforming"

        rows.append({
            "experiment_id": item.get("id"),
            "name": item.get("name", item.get("experiment_name", "Unnamed experiment")),
            "platform": item.get("platform"),
            "country": item.get("country"),
            "region": item.get("region"),
            "spend": round(spend, 2),
            "revenue": round(revenue, 2),
            "roas": round(roas, 3) if roas is not None else None,
            "profit": round(profit, 2),
            "assessment": assessment,
            "has_explicit_profit": has_profit,
        })

        total_spend += spend
        total_revenue += revenue
        total_profit += profit
        has_profit_data = has_profit_data or has_profit

    return {
        "experiment_count": len(rows),
        "total_spend": round(total_spend, 2),
        "total_revenue": round(total_revenue, 2),
        "overall_roas": round(total_revenue / total_spend, 3) if total_spend else None,
        "estimated_profit_before_other_costs": round(total_profit, 2),
        "profit_is_partial_estimate": not has_profit_data,
        "experiments": rows,
        "spending_executed": False,
    }
