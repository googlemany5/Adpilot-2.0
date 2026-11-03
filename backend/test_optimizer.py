import math
from types import SimpleNamespace

import pytest

from optimizer import (
    safe_divide,
    calculate_experiment_metrics,
    rank_experiments,
    calculate_final_allocation,
    validate_allocation,
    continuous_optimization,
)


def make_experiment(**overrides):
    data = {
        "id": 1,
        "name": "Test experiment",
        "experiment_type": "country",
        "target": "United States",
        "platform": "meta",
        "budget": 100,
        "spent": 50,
        "clicks": 100,
        "conversions": 5,
        "revenue": 200,
        "status": "completed",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


# SAFE DIVISION

def test_safe_divide_normal_values():
    assert safe_divide(200, 50) == 4


def test_safe_divide_zero_denominator():
    assert safe_divide(200, 0) == 0


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_safe_divide_rejects_non_finite_values(value):
    with pytest.raises(ValueError):
        safe_divide(value, 10)


def test_safe_divide_rejects_invalid_denominator():
    with pytest.raises(ValueError):
        safe_divide(10, float("nan"))


# EXPERIMENT METRICS

def test_experiment_metrics_calculate_correctly():
    result = calculate_experiment_metrics(make_experiment())

    assert result["roas"] == 4
    assert result["conversion_rate"] == 0.05
    assert result["cost_per_conversion"] == 10


# EXPERIMENT RANKING

def test_rank_experiments_ranks_higher_roas_first():
    low = make_experiment(id=1, revenue=100, spent=50)
    high = make_experiment(id=2, revenue=300, spent=50)

    result = rank_experiments([low, high])

    assert result[0]["experiment_id"] == 2
    assert result[0]["score"] > result[1]["score"]


def test_rank_experiments_does_not_expand_tiny_sample():
    experiment = make_experiment(
        spent=1,
        revenue=100,
        clicks=1,
        conversions=1,
    )

    result = rank_experiments([experiment])

    assert result[0]["recommendation"] != "expand"


def test_rank_experiments_rejects_non_finite_metrics():
    experiment = make_experiment(revenue=float("nan"))

    with pytest.raises(ValueError):
        rank_experiments([experiment])


# FINAL ALLOCATION

def test_final_allocation_distributes_budget_proportionally():
    result = calculate_final_allocation(
        [
            {"name": "A", "expected_roas": 4},
            {"name": "B", "expected_roas": 2},
        ],
        900,
    )

    assert result[0]["recommended_budget"] == 600
    assert result[1]["recommended_budget"] == 300
    assert sum(x["recommended_budget"] for x in result) == 900


def test_final_allocation_returns_empty_for_zero_budget():
    assert calculate_final_allocation(
        [{"expected_roas": 4}],
        0,
    ) == []


@pytest.mark.parametrize("budget", [float("nan"), float("inf"), -1, True])
def test_final_allocation_rejects_invalid_budget(budget):
    with pytest.raises(ValueError):
        calculate_final_allocation(
            [{"expected_roas": 4}],
            budget,
        )


def test_final_allocation_rejects_non_finite_roas():
    with pytest.raises(ValueError):
        calculate_final_allocation(
            [{"expected_roas": float("nan")}],
            100,
        )


# ALLOCATION VALIDATION

def test_validate_allocation_approves_within_budget():
    result = validate_allocation(
        {"recommended_budget": 40},
        100,
    )

    assert result["approved_budget"] == 40
    assert result["within_budget"] is True
    assert result["blocked"] is False


def test_validate_allocation_caps_at_remaining_budget():
    result = validate_allocation(
        {"recommended_budget": 150},
        100,
    )

    assert result["approved_budget"] == 100
    assert result["within_budget"] is False


@pytest.mark.parametrize(
    "requested,remaining",
    [
        (float("nan"), 100),
        (float("inf"), 100),
        (True, 100),
        (10, float("nan")),
        (10, float("inf")),
    ],
)
def test_validate_allocation_rejects_invalid_values(requested, remaining):
    with pytest.raises(ValueError):
        validate_allocation(
            {"recommended_budget": requested},
            remaining,
        )


# CONTINUOUS OPTIMIZATION

def test_continuous_optimization_increases_high_roas_recommendation():
    result = continuous_optimization([
        {"expected_roas": 4, "current_budget": 100}
    ])

    assert result[0]["action"] == "increase"
    assert result[0]["recommended_budget"] == 120


def test_continuous_optimization_does_not_change_original_input():
    original = {
        "expected_roas": 4,
        "current_budget": 100,
    }

    continuous_optimization([original])

    assert original["current_budget"] == 100


def test_continuous_optimization_rejects_non_finite_values():
    with pytest.raises(ValueError):
        continuous_optimization([
            {
                "expected_roas": float("nan"),
                "current_budget": 100,
            }
        ])
