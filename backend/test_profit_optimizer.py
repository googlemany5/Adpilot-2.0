import pytest

from profit_optimizer import optimize_profit


def experiment(**overrides):
    data = {
        "experiment_id": "test-1",
        "name": "US Market Test",
        "revenue": 1000,
        "spend": 200,
        "product_cost": 300,
        "fulfillment_cost": 100,
        "transaction_fees": 30,
        "other_costs": 20,
    }
    data.update(overrides)
    return data


def test_calculates_complete_positive_profit():
    result = optimize_profit([experiment()])
    report = result["experiments"][0]

    assert report["known_profit_estimate"] == 350
    assert report["profit_complete"] is True
    assert report["recommendation"] == "profitable_candidate"
    assert result["experiments_with_complete_costs"] == 1


def test_calculates_loss():
    result = optimize_profit([
        experiment(revenue=500, spend=300, product_cost=400)
    ])

    report = result["experiments"][0]

    assert report["known_profit_estimate"] == -350
    assert report["recommendation"] == "loss_making_candidate"


def test_calculates_break_even():
    result = optimize_profit([
        experiment(
            revenue=650,
            spend=200,
            product_cost=300,
            fulfillment_cost=100,
            transaction_fees=30,
            other_costs=20,
        )
    ])

    report = result["experiments"][0]

    assert report["known_profit_estimate"] == 0
    assert report["recommendation"] == "break_even_candidate"


def test_missing_costs_prevent_complete_profit_claim():
    data = experiment()
    del data["product_cost"]

    result = optimize_profit([data])
    report = result["experiments"][0]

    assert report["profit_complete"] is False
    assert report["recommendation"] == "collect_cost_data"
    assert "product_cost" in report["missing_cost_fields"]


def test_missing_revenue_or_spend_prevents_profit_calculation():
    result = optimize_profit([
        experiment(revenue=None),
        experiment(spend=None),
    ])

    for report in result["experiments"]:
        assert report["known_profit_estimate"] is None
        assert report["profit_complete"] is False
        assert report["recommendation"] == "collect_cost_data"


def test_product_cost_can_be_estimated_from_unit_cost():
    data = experiment()
    del data["product_cost"]
    data["product_cost_per_conversion"] = 10
    data["conversions"] = 20

    result = optimize_profit([data])
    report = result["experiments"][0]

    assert report["known_non_ad_costs"] == 350
    assert report["known_profit_estimate"] == 450
    assert report["profit_complete"] is True


def test_missing_product_cost_without_unit_cost_stays_incomplete():
    data = experiment()
    del data["product_cost"]

    result = optimize_profit([data])
    report = result["experiments"][0]

    assert report["profit_complete"] is False
    assert "product_cost" in report["missing_cost_fields"]


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("revenue", -1),
        ("revenue", float("nan")),
        ("revenue", float("inf")),
        ("revenue", True),
        ("spend", -1),
        ("spend", float("nan")),
        ("spend", float("inf")),
        ("spend", True),
        ("product_cost", -1),
        ("product_cost", float("nan")),
        ("fulfillment_cost", float("inf")),
        ("transaction_fees", True),
        ("other_costs", -1),
    ],
)
def test_invalid_money_values_are_rejected(field, bad_value):
    with pytest.raises(ValueError):
        optimize_profit([experiment(**{field: bad_value})])


@pytest.mark.parametrize(
    "bad_conversions",
    [-1, 1.5, True, float("nan"), float("inf"), None],
)
def test_invalid_conversion_counts_are_rejected(bad_conversions):
    data = experiment()
    del data["product_cost"]
    data["product_cost_per_conversion"] = 10
    data["conversions"] = bad_conversions

    with pytest.raises(ValueError):
        optimize_profit([data])


def test_totals_combine_multiple_experiments():
    result = optimize_profit([
        experiment(revenue=1000),
        experiment(revenue=500),
    ])

    assert result["totals"]["revenue"] == 1500
    assert result["totals"]["ad_spend"] == 400
    assert result["totals"]["known_non_ad_costs"] == 900
    assert result["totals"]["known_profit_estimate"] == 200


def test_empty_list_is_supported():
    result = optimize_profit([])

    assert result["experiments_analyzed"] == 0
    assert result["experiments"] == []
    assert result["experiments_with_complete_costs"] == 0


def test_non_list_input_is_rejected():
    with pytest.raises(ValueError):
        optimize_profit({"experiment": experiment()})


def test_non_dictionary_experiment_is_rejected():
    with pytest.raises(ValueError):
        optimize_profit(["invalid"])


def test_profit_optimizer_never_executes_spending():
    result = optimize_profit([experiment()])

    assert result["mode"] == "shadow"
    assert result["spending_executed"] is False
    assert result["experiments"][0]["spending_executed"] is False


def test_original_experiment_is_not_modified():
    original = experiment()
    before = original.copy()

    optimize_profit([original])

    assert original == before
