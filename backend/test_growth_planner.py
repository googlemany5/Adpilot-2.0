import pytest

from growth_planner import build_growth_plan
from market_discovery import discover_markets


def campaign(**overrides):
    data = {
        "language": "English",
        "product_category": "fitness",
        "month": 11,
    }
    data.update(overrides)
    return data


def market(country="USA", **overrides):
    data = {
        "country": country,
        "region": "North America",
        "languages": ["English"],
        "suitable_categories": ["fitness"],
        "good_months": [11],
        "local_hour": 12,
        "active_hours": [8, 22],
        "audience_score": 90,
    }
    data.update(overrides)
    return data


def region(name="Montana", **overrides):
    data = {
        "region": name,
        "audience_score": 90,
        "market_size_score": 80,
        "competition_score": 20,
        "demand_score": 85,
    }
    data.update(overrides)
    return data


def result(**overrides):
    data = {
        "experiment_id": "exp-1",
        "name": "US Fitness Test",
        "country": "USA",
        "region": "Montana",
        "platform": "meta",
        "spend": 100,
        "revenue": 400,
        "conversions": 5,
        "clicks": 100,
        "impressions": 1000,
        "product_cost": 100,
        "fulfillment_cost": 20,
        "transaction_fees": 10,
        "other_costs": 5,
    }
    data.update(overrides)
    return data


def test_growth_plan_combines_all_engines():
    plan = build_growth_plan(
        campaign(),
        [market()],
        discovery_budget=100,
        regions_by_country={"USA": [region()]},
        experiment_results=[result()],
    )

    assert plan["engine"] == "adpilot_growth_planner_v2"
    assert plan["market_discovery"]["markets_selected"] == 1
    assert len(plan["experiment_budget_plan"]["experiments"]) == 1
    assert len(plan["regional_discovery"]) == 1
    assert plan["experiment_learning"]["experiments_analyzed"] == 1
    assert plan["profit_optimization"]["experiments_analyzed"] == 1
    assert plan["performance_analysis"]["experiment_count"] == 1


def test_growth_plan_is_shadow_only():
    plan = build_growth_plan(
        campaign(), [market()], 100, experiment_results=[result()]
    )

    assert plan["mode"] == "shadow"
    assert plan["spending_executed"] is False
    assert plan["experiment_budget_plan"]["spending_executed"] is False
    assert plan["experiment_learning"]["spending_executed"] is False
    assert plan["profit_optimization"]["spending_executed"] is False
    assert plan["performance_analysis"]["spending_executed"] is False


def test_growth_plan_without_experiment_results_is_supported():
    plan = build_growth_plan(campaign(), [market()], 100)

    assert plan["experiment_learning"]["experiments_analyzed"] == 0
    assert plan["profit_optimization"]["experiments_analyzed"] == 0
    assert plan["performance_analysis"]["experiment_count"] == 0


def test_growth_plan_recommends_regional_discovery():
    plan = build_growth_plan(
        campaign(),
        [market()],
        100,
        regions_by_country={
            "USA": [region("Montana"), region("Texas", audience_score=75)]
        },
    )

    reports = plan["regional_discovery"]
    assert len(reports) == 1
    assert reports[0]["regions_evaluated"] == 2
    assert reports[0]["shortlist"][0]["region"] == "Montana"


def test_growth_plan_respects_market_limit():
    plan = build_growth_plan(
        campaign(),
        [market("USA"), market("Canada"), market("Australia")],
        100,
        max_markets=2,
    )

    assert plan["market_discovery"]["markets_selected"] == 2
    assert len(plan["experiment_budget_plan"]["experiments"]) <= 2


def test_growth_plan_respects_region_limit():
    plan = build_growth_plan(
        campaign(),
        [market()],
        100,
        regions_by_country={
            "USA": [
                region("Montana"),
                region("Texas"),
                region("Florida"),
            ]
        },
        max_regions=2,
    )

    assert len(plan["regional_discovery"][0]["shortlist"]) == 2


def test_growth_plan_adds_follow_up_action_for_promising_result():
    plan = build_growth_plan(
        campaign(), [market()], 100,
        experiment_results=[result()],
    )

    assert any(
        "controlled follow-up" in action
        for action in plan["next_actions"]
    )


def test_growth_plan_adds_review_action_for_underperforming_result():
    plan = build_growth_plan(
        campaign(), [market()], 100,
        experiment_results=[result(revenue=20)],
    )

    assert any(
        "targeting, creative, or" in action
        for action in plan["next_actions"]
    )


def test_growth_plan_rejects_non_list_experiment_results():
    with pytest.raises(ValueError, match="experiment_results must be a list"):
        build_growth_plan(
            campaign(), [market()], 100,
            experiment_results={"spend": 100},
        )


def test_growth_plan_rejects_invalid_experiment_measurements():
    with pytest.raises(ValueError):
        build_growth_plan(
            campaign(), [market()], 100,
            experiment_results=[result(spend=float("nan"))],
        )


def test_growth_plan_does_not_modify_inputs():
    original_campaign = campaign()
    original_markets = [market()]
    original_results = [result()]

    before_campaign = original_campaign.copy()
    before_markets = [item.copy() for item in original_markets]
    before_results = [item.copy() for item in original_results]

    build_growth_plan(
        original_campaign,
        original_markets,
        100,
        experiment_results=original_results,
    )

    assert original_campaign == before_campaign
    assert original_markets == before_markets
    assert original_results == before_results


@pytest.mark.parametrize("bad_campaign", [None, [], "invalid"])
def test_market_discovery_rejects_invalid_campaign_type(bad_campaign):
    with pytest.raises(ValueError, match="campaign must be a dictionary"):
        discover_markets(bad_campaign, [market()])


@pytest.mark.parametrize("bad_limit", [0, -1, True, 1.5])
def test_market_discovery_rejects_invalid_market_limit(bad_limit):
    with pytest.raises(ValueError, match="max_markets"):
        discover_markets(campaign(), [market()], max_markets=bad_limit)


@pytest.mark.parametrize("bad_month", [True, 0, 13, 1.5, "11"])
def test_market_discovery_rejects_invalid_month(bad_month):
    with pytest.raises(ValueError, match="campaign month"):
        discover_markets(campaign(month=bad_month), [market()])


def test_market_discovery_rejects_non_list_markets():
    with pytest.raises(ValueError, match="markets must be a list"):
        discover_markets(campaign(), {"country": "USA"})
