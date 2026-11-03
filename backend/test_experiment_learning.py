import pytest

from experiment_learning import analyze_experiment, learn_from_experiments


def experiment(**overrides):
    data = {
        "experiment_id": "test-1",
        "name": "US Market Test",
        "spend": 100,
        "revenue": 300,
        "conversions": 5,
        "clicks": 100,
        "impressions": 1000,
    }
    data.update(overrides)
    return data


def test_calculates_metrics_correctly():
    result = analyze_experiment(experiment())

    assert result["roas"] == 3
    assert result["cost_per_conversion"] == 20
    assert result["conversion_rate"] == 0.05
    assert result["click_through_rate"] == 0.1
    assert result["minimum_data_reached"] is True
    assert result["recommendation"] == "expand_candidate"


def test_high_roas_with_too_little_data_does_not_expand():
    result = analyze_experiment(
        experiment(spend=5, revenue=100, conversions=1, clicks=5, impressions=50)
    )

    assert result["roas"] == 20
    assert result["recommendation"] == "test_more"
    assert result["minimum_data_reached"] is False


def test_zero_spend_requests_data_collection():
    result = analyze_experiment(
        experiment(spend=0, revenue=0, conversions=0, clicks=0, impressions=0)
    )

    assert result["roas"] is None
    assert result["recommendation"] == "collect_data"


def test_missing_revenue_requests_tracking_review():
    data = experiment()
    del data["revenue"]

    result = analyze_experiment(data)

    assert result["revenue_recorded"] is False
    assert result["roas"] is None
    assert result["recommendation"] == "review_tracking"


def test_zero_revenue_with_sufficient_data_requests_tracking_review():
    result = analyze_experiment(experiment(revenue=0))

    assert result["minimum_data_reached"] is True
    assert result["recommendation"] == "review_tracking"


def test_medium_roas_recommends_more_testing():
    result = analyze_experiment(experiment(revenue=200))

    assert result["roas"] == 2
    assert result["recommendation"] == "test_more"


def test_low_roas_recommends_review_before_reduction():
    result = analyze_experiment(experiment(revenue=50))

    assert result["roas"] == 0.5
    assert result["recommendation"] == "reduce_candidate"


def test_evidence_score_stays_between_zero_and_100():
    result = analyze_experiment(
        experiment(spend=10000, clicks=10000, impressions=20000, conversions=1000)
    )

    assert 0 <= result["evidence_score"] <= 100
    assert result["evidence_score"] == 100


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("spend", -1),
        ("spend", float("nan")),
        ("spend", float("inf")),
        ("spend", True),
        ("revenue", -1),
        ("revenue", float("nan")),
        ("revenue", float("inf")),
        ("revenue", True),
        ("clicks", -1),
        ("clicks", 1.5),
        ("clicks", True),
        ("conversions", -1),
        ("conversions", 1.5),
        ("impressions", float("inf")),
    ],
)
def test_invalid_measurements_are_rejected(field, bad_value):
    with pytest.raises(ValueError):
        analyze_experiment(experiment(**{field: bad_value}))


def test_conversions_cannot_exceed_clicks():
    with pytest.raises(ValueError):
        analyze_experiment(experiment(conversions=10, clicks=5))


def test_clicks_cannot_exceed_impressions():
    with pytest.raises(ValueError):
        analyze_experiment(experiment(clicks=100, impressions=50))


def test_zero_clicks_produces_no_conversion_rate():
    result = analyze_experiment(
        experiment(clicks=0, conversions=0, impressions=100)
    )

    assert result["conversion_rate"] is None


def test_non_dictionary_experiment_is_rejected():
    with pytest.raises(ValueError):
        analyze_experiment(["not", "a", "dictionary"])


def test_learning_ranks_expansion_candidate_first():
    results = learn_from_experiments([
        experiment(experiment_id="low", revenue=50),
        experiment(experiment_id="high", revenue=400),
        experiment(experiment_id="medium", revenue=200),
    ])

    assert results["ranked_results"][0]["experiment_id"] == "high"
    assert results["ranked_results"][0]["recommendation"] == "expand_candidate"
    assert results["experiments_analyzed"] == 3


def test_learning_counts_recommendations():
    results = learn_from_experiments([
        experiment(revenue=400),
        experiment(revenue=200),
        experiment(revenue=50),
    ])

    assert results["recommendation_counts"] == {
        "expand_candidate": 1,
        "test_more": 1,
        "reduce_candidate": 1,
    }


def test_empty_experiment_list_is_supported():
    result = learn_from_experiments([])

    assert result["experiments_analyzed"] == 0
    assert result["ranked_results"] == []
    assert result["spending_executed"] is False


def test_non_list_input_is_rejected():
    with pytest.raises(ValueError):
        learn_from_experiments({"experiment": experiment()})


def test_learning_never_executes_spending():
    result = learn_from_experiments([experiment()])

    assert result["spending_executed"] is False
    assert all(
        item["spending_executed"] is False
        for item in result["ranked_results"]
    )


def test_original_experiment_is_not_modified():
    original = experiment()
    before = original.copy()

    analyze_experiment(original)

    assert original == before
