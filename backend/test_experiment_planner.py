import pytest

from experiment_planner import money, create_experiment_plan


def markets(*items):
    return {"shortlist": list(items)}


def market(country, score=1, eligible=True):
    return {
        "country": country,
        "score": score,
        "eligible_for_experiment": eligible,
    }


def test_money_converts_and_rounds_down_to_cents():
    assert money("12.349") == money("12.34")
    assert money(10) == money("10.00")


@pytest.mark.parametrize(
    "value",
    [-1, float("nan"), float("inf"), float("-inf"), None, True, "invalid"],
)
def test_money_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        money(value)


def test_plan_allocates_budget_proportionally():
    result = create_experiment_plan(
        100,
        markets(
            market("USA", 3),
            market("Canada", 1),
        ),
    )

    experiments = result["experiments"]

    assert len(experiments) == 2
    assert experiments[0]["planned_budget"] == 75
    assert experiments[1]["planned_budget"] == 25
    assert result["planned_total"] == 100


def test_allocations_add_up_exactly_with_uneven_shares():
    result = create_experiment_plan(
        10,
        markets(
            market("USA", 1),
            market("Canada", 1),
            market("Mexico", 1),
        ),
    )

    allocations = [
        item["planned_budget"] for item in result["experiments"]
    ]

    assert sum(allocations) == 10
    assert all(value >= 1 for value in allocations)


def test_ineligible_markets_are_excluded():
    result = create_experiment_plan(
        20,
        markets(
            market("USA", 10, False),
            market("Canada", 5, True),
        ),
    )

    assert len(result["experiments"]) == 1
    assert result["experiments"][0]["country"] == "Canada"


def test_max_experiments_limits_shortlist():
    result = create_experiment_plan(
        100,
        markets(
            market("USA", 3),
            market("Canada", 2),
            market("Mexico", 1),
        ),
        max_experiments=2,
    )

    assert len(result["experiments"]) == 2


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "3"])
def test_invalid_max_experiments_rejected(value):
    with pytest.raises(ValueError):
        create_experiment_plan(
            100,
            markets(market("USA")),
            max_experiments=value,
        )


def test_budget_under_one_dollar_creates_no_experiments():
    result = create_experiment_plan(
        0.99,
        markets(market("USA")),
    )

    assert result["experiments"] == []
    assert result["planned_total"] == 0
    assert result["spending_executed"] is False


def test_round_budget_cannot_exceed_discovery_budget():
    with pytest.raises(ValueError):
        create_experiment_plan(
            100,
            markets(market("USA")),
            round_budget=101,
        )


@pytest.mark.parametrize(
    "bad_budget",
    [-1, float("nan"), float("inf"), None, True],
)
def test_invalid_discovery_budget_rejected(bad_budget):
    with pytest.raises(ValueError):
        create_experiment_plan(
            bad_budget,
            markets(market("USA")),
        )


def test_invalid_round_budget_rejected():
    with pytest.raises(ValueError):
        create_experiment_plan(
            100,
            markets(market("USA")),
            round_budget=float("nan"),
        )


def test_zero_scores_are_allocated_equally():
    result = create_experiment_plan(
        12,
        markets(
            market("USA", 0),
            market("Canada", 0),
        ),
    )

    allocations = [
        item["planned_budget"] for item in result["experiments"]
    ]

    assert allocations == [6, 6]


def test_invalid_scores_fall_back_safely():
    result = create_experiment_plan(
        10,
        markets(
            market("USA", float("nan")),
            market("Canada", float("inf")),
        ),
    )

    allocations = [
        item["planned_budget"] for item in result["experiments"]
    ]

    assert allocations == [5, 5]


def test_round_budget_leaves_unused_discovery_funds():
    result = create_experiment_plan(
        100,
        markets(market("USA")),
        round_budget=20,
    )

    assert result["round_budget"] == 20
    assert result["planned_total"] == 20
    assert result["unallocated_budget"] == 80


def test_planner_never_executes_ad_spending():
    result = create_experiment_plan(
        50,
        markets(market("USA")),
    )

    assert result["spending_executed"] is False
    assert all(
        experiment["status"] == "planned"
        for experiment in result["experiments"]
    )


def test_original_market_data_is_not_modified():
    original = markets(market("USA", 5))
    before = repr(original)

    create_experiment_plan(50, original)

    assert repr(original) == before
