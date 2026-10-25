"""AdPilot AI Market Discovery Engine.

Ranks candidate advertising markets using explicit campaign and market data.
This module recommends where to experiment; it never spends advertising money.
"""

from typing import Any


WEIGHTS = {
    "language": 30,
    "product_fit": 25,
    "season": 20,
    "timing": 15,
    "audience": 10,
}


def _clamp_score(value: Any, default: float = 50.0) -> float:
    """Convert a score to a safe number between 0 and 100."""
    try:
        score = float(value)
    except (TypeError, ValueError, OverflowError):
        return default

    if score != score or score in (float("inf"), float("-inf")):
        return default

    return max(0.0, min(100.0, score))



def _clamp_month(value: Any) -> int:
    """Return a valid month, or 0 when the input is unusable."""
    try:
        month = int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return month if 1 <= month <= 12 else 0


def _language_score(campaign_language: str, market: dict) -> float:
    languages = market.get("languages", [])

    if isinstance(languages, str):
        languages = [languages]

    if not languages or not campaign_language:
        return 50.0

    normalized = campaign_language.strip().casefold()
    supported = [str(language).strip().casefold() for language in languages]

    return 100.0 if normalized in supported else 0.0


def _product_score(product_category: str, market: dict) -> float:
    suitable = market.get("suitable_categories", [])

    if isinstance(suitable, str):
        suitable = [suitable]

    if not suitable or not product_category:
        return 50.0

    normalized = product_category.strip().casefold()

    if "all" in [str(item).casefold() for item in suitable]:
        return 100.0

    return (
        100.0
        if normalized in [str(item).strip().casefold() for item in suitable]
        else 20.0
    )


def _season_score(month: int, market: dict) -> float:
    good_months = market.get("good_months", [])
    poor_months = market.get("poor_months", [])

    if not good_months and not poor_months:
        return 50.0

    if month in good_months:
        return 100.0

    if month in poor_months:
        return 15.0

    return 60.0


def _timing_score(market: dict) -> float:
    """Score the supplied local hour against a market's active hours."""
    hour = market.get("local_hour")
    active_hours = market.get("active_hours", [8, 22])

    if hour is None:
        return 50.0

    try:
        hour = int(hour)
        start, end = int(active_hours[0]), int(active_hours[1])
    except (TypeError, ValueError, IndexError):
        return 50.0

    if not 0 <= hour <= 23:
        return 50.0

    if start <= end:
        return 100.0 if start <= hour < end else 15.0

    # Supports active periods crossing midnight, such as 20:00–02:00.
    return 100.0 if hour >= start or hour < end else 15.0


def score_market(
    campaign: dict,
    market: dict,
) -> dict:
    """Score one candidate market and explain the result."""
    signals = {
        "language": _language_score(
            str(campaign.get("language", "")), market
        ),
        "product_fit": _product_score(
            str(campaign.get("product_category", "")), market
        ),
        "season": _season_score(
            _clamp_month(campaign.get("month", 0)), market
        ),
        "timing": _timing_score(market),
        "audience": _clamp_score(
            market.get("audience_score", 50)
        ),
    }

    weighted_total = sum(
        signals[name] * weight
        for name, weight in WEIGHTS.items()
    ) / sum(WEIGHTS.values())

    reasons = []
    warnings = []

    if signals["language"] == 100:
        reasons.append("Campaign language matches a listed market language.")
    elif signals["language"] == 0:
        warnings.append("Campaign language is not listed for this market.")
    else:
        reasons.append("Language fit needs more data.")

    if signals["product_fit"] == 100:
        reasons.append("Product category is listed as suitable.")
    elif signals["product_fit"] == 20:
        warnings.append("Product category is not listed as suitable.")
    else:
        reasons.append("Product-market fit needs more data.")

    if signals["season"] == 15:
        warnings.append("This month is listed as a poor seasonal fit.")
    elif signals["season"] == 100:
        reasons.append("This month is listed as a favorable season.")

    if signals["timing"] == 15:
        warnings.append("The supplied local hour is outside active hours.")
    elif signals["timing"] == 100:
        reasons.append("The supplied local hour is within active hours.")

    if signals["audience"] < 30:
        warnings.append("The audience potential score is low.")

    # Hard filters stop clearly unsuitable markets from ranking highly.
    hard_rejections = []
    if signals["language"] == 0:
        hard_rejections.append("language_mismatch")
    if signals["season"] == 15:
        hard_rejections.append("poor_season")
    if signals["timing"] == 15:
        hard_rejections.append("outside_active_hours")

    eligible = not hard_rejections and weighted_total >= 40

    return {
        "country": market.get("country", "Unknown"),
        "region": market.get("region"),
        "score": round(weighted_total, 2),
        "eligible_for_experiment": eligible,
        "signals": signals,
        "rejection_reasons": hard_rejections,
        "reasons": reasons,
        "warnings": warnings,
    }


def discover_markets(
    campaign: dict,
    markets: list[dict],
    max_markets: int = 3,
) -> dict:
    """Rank markets and return a shortlist for the experiment engine."""
    if not isinstance(max_markets, int) or max_markets < 1:
        raise ValueError("max_markets must be a positive integer.")

    month = campaign.get("month", 1)
    if not isinstance(month, int) or not 1 <= month <= 12:
        raise ValueError("campaign month must be an integer from 1 to 12.")

    if not isinstance(campaign, dict):
        raise ValueError("campaign must be a dictionary.")
    if not isinstance(markets, list):
        raise ValueError("markets must be a list of dictionaries.")

    results = [
        score_market(campaign, market)
        for market in markets
        if isinstance(market, dict)
    ]
    results.sort(key=lambda item: item["score"], reverse=True)

    eligible = [
        item for item in results
        if item["eligible_for_experiment"]
    ]
    rejected = [
        item for item in results
        if not item["eligible_for_experiment"]
    ]

    return {
        "engine": "market_discovery_v1",
        "campaign_language": campaign.get("language"),
        "product_category": campaign.get("product_category"),
        "month": month,
        "markets_evaluated": len(results),
        "markets_selected": min(len(eligible), max_markets),
        "shortlist": eligible[:max_markets],
        "rejected_markets": rejected,
        "next_stage": (
            "state_or_region_discovery" if eligible
            else "collect_more_market_data"
        ),
        "spending_executed": False,
    }
