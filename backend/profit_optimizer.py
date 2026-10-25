"""AdPilot Profit Optimization v1.

Estimates experiment profitability from supplied data.
Recommendation-only: never changes budgets or launches advertising.
"""

import math

COST_FIELDS = (
    "product_cost",
    "fulfillment_cost",
    "transaction_fees",
    "other_costs",
)


def _amount(value, field):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be a finite non-negative number.")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field} must be a finite non-negative number.") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{field} must be a finite non-negative number.")
    return number


def optimize_profit(experiments):
    """Report known-cost profit estimates and conservative next steps."""
    if not isinstance(experiments, list):
        raise ValueError("experiments must be a list.")

    reports = []
    totals = {
        "revenue": 0.0,
        "ad_spend": 0.0,
        "known_non_ad_costs": 0.0,
        "known_profit_estimate": 0.0,
    }
    complete_count = 0

    for item in experiments:
        if not isinstance(item, dict):
            raise ValueError("Each experiment must be a dictionary.")

        revenue_known = item.get("revenue") is not None
        spend_known = item.get("spend") is not None

        revenue = _amount(item["revenue"], "revenue") if revenue_known else None
        spend = _amount(item["spend"], "spend") if spend_known else None

        costs = {}
        missing_costs = []
        for field in COST_FIELDS:
            if field in item and item[field] is not None:
                costs[field] = _amount(item[field], field)
            else:
                costs[field] = 0.0
                missing_costs.append(field)

        # Optionally estimate product cost from a supplied unit cost and
        # whole-number conversion count, but never invent missing values.
        if "product_cost" in missing_costs and item.get("product_cost_per_conversion") is not None:
            conversions_value = item.get("conversions")
            if isinstance(conversions_value, bool) or conversions_value is None:
                raise ValueError("conversions must be supplied with product_cost_per_conversion.")
            try:
                conversions_float = float(conversions_value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("conversions must be a non-negative whole number.") from exc
            if not math.isfinite(conversions_float) or conversions_float < 0 or not conversions_float.is_integer():
                raise ValueError("conversions must be a non-negative whole number.")
            unit_cost = _amount(item["product_cost_per_conversion"], "product_cost_per_conversion")
            costs["product_cost"] = unit_cost * int(conversions_float)
            missing_costs.remove("product_cost")

        known_non_ad_costs = sum(costs.values())
        can_estimate = revenue_known and spend_known
        known_profit = revenue - spend - known_non_ad_costs if can_estimate else None
        complete = can_estimate and not missing_costs

        if complete:
            complete_count += 1
            if known_profit > 0:
                recommendation = "profitable_candidate"
                reason = "Supplied costs indicate positive profit; verify the figures before any budget decision."
            elif known_profit < 0:
                recommendation = "loss_making_candidate"
                reason = "Supplied costs indicate a loss; review margins, attribution, and campaign setup."
            else:
                recommendation = "break_even_candidate"
                reason = "Supplied costs indicate break-even performance before any unlisted expenses."
        else:
            recommendation = "collect_cost_data"
            reason = "Profit is incomplete because revenue, ad spend, or one or more cost categories are missing."

        report = {
            "experiment_id": item.get("experiment_id", item.get("id")),
            "name": item.get("name", item.get("experiment_name", "Unnamed experiment")),
            "revenue": round(revenue, 2) if revenue_known else None,
            "ad_spend": round(spend, 2) if spend_known else None,
            "known_non_ad_costs": round(known_non_ad_costs, 2),
            "known_profit_estimate": round(known_profit, 2) if known_profit is not None else None,
            "profit_complete": complete,
            "missing_cost_fields": missing_costs,
            "recommendation": recommendation,
            "reason": reason,
            "spending_executed": False,
        }
        reports.append(report)

        if can_estimate:
            totals["revenue"] += revenue
            totals["ad_spend"] += spend
            totals["known_non_ad_costs"] += known_non_ad_costs
            totals["known_profit_estimate"] += known_profit

    return {
        "engine": "profit_optimizer_v1",
        "experiments_analyzed": len(reports),
        "experiments_with_complete_costs": complete_count,
        "totals": {key: round(value, 2) for key, value in totals.items()},
        "experiments": reports,
        "important_note": (
            "Profit estimates are only as reliable as the supplied data. "
            "Complete here means all listed cost categories were provided; "
            "unlisted taxes, overhead, refunds, or other expenses may still apply."
        ),
        "mode": "shadow",
        "spending_executed": False,
    }
