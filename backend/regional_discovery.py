"""Ranks state, province, and regional advertising opportunities."""

def discover_regions(country, regions, max_regions=5):
    if not isinstance(regions, list):
        raise ValueError('regions must be a list.')
    if not isinstance(max_regions, int) or isinstance(max_regions, bool) or max_regions < 1:
        raise ValueError("max_regions must be a positive integer.")

    results = []

    for region in regions:
        name = region.get("region")
        if not name:
            continue

        def score_value(key, default=50):
            try:
                value = float(region.get(key, default))
            except (TypeError, ValueError, OverflowError):
                raise ValueError(f'{key} must be a valid number.')
            if not 0 <= value <= 100 or value != value:
                raise ValueError(f"{key} must be between 0 and 100.")
            return value

        audience = score_value("audience_score")
        market_size = score_value("market_size_score")
        competition = score_value("competition_score")
        demand = score_value("demand_score")

        # Lower competition is favorable, all other signals are higher-is-better.
        score = (
            audience * 0.35
            + market_size * 0.25
            + (100 - competition) * 0.20
            + demand * 0.20
        )

        reasons = []
        if audience >= 70:
            reasons.append("Strong audience potential")
        if market_size >= 70:
            reasons.append("Large estimated market")
        if competition <= 40:
            reasons.append("Relatively low competition")
        if demand >= 70:
            reasons.append("Strong estimated demand")

        results.append({
            "country": country,
            "region": name,
            "score": round(score, 2),
            "signals": {
                "audience": audience,
                "market_size": market_size,
                "competition": competition,
                "demand": demand,
            },
            "reasons": reasons or ["More regional data is needed"],
            "eligible_for_experiment": score >= 40,
            "spending_executed": False,
        })

    results.sort(key=lambda item: item["score"], reverse=True)
    eligible = [item for item in results if item["eligible_for_experiment"]]

    return {
        "engine": "regional_discovery_v1",
        "country": country,
        "regions_evaluated": len(results),
        "shortlist": eligible[:max_regions],
        "spending_executed": False,
    }
