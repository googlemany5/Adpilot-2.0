import pytest

from forecast_engine import forecast_campaign


def campaign(**overrides):
    data = {
        "id": 1,
        "monthly_budget": 3000,
        "spent_this_month": 1000,
        "revenue_this_month": 2000,
    }
    data.update(overrides)
    return data


def test_forecast_calculates_remaining_revenue():
    result = forecast_campaign(
        campaign(),
        [
            {"spend": 100, "revenue": 300},
            {"spend": 100, "revenue": 300},
            {"spend": 100, "revenue": 300},
        ],
    )

    assert result["historical_roas"] == 3
    assert result["remaining_budget_estimate"] == 2000
    assert result["projected_remaining_revenue"] == 6000
    assert result["projected_monthly_revenue"] == 8000


def test_forecast_handles_exhausted_budget():
    result = forecast_campaign(
        campaign(spent_this_month=3000),
        [{"spend": 100, "revenue": 300}],
    )

    assert result["remaining_budget_estimate"] == 0
    assert result["projected_remaining_revenue"] == 0


def test_forecast_handles_exceeded_budget():
    result = forecast_campaign(
        campaign(spent_this_month=3500),
        [{"spend": 100, "revenue": 300}],
    )

    assert result["remaining_budget_estimate"] == 0
    assert any("exceeds" in warning for warning in result["warnings"])


def test_forecast_handles_zero_historical_spend():
    result = forecast_campaign(
        campaign(),
        [{"spend": 0, "revenue": 100}],
    )

    assert result["confidence"] == "insufficient_data"
    assert result["projected_monthly_revenue"] is None


def test_forecast_marks_small_samples_low_confidence():
    result = forecast_campaign(
        campaign(),
        [{"spend": 100, "revenue": 300}],
    )

    assert result["confidence"] == "low"


@pytest.mark.parametrize(
    "bad_value",
    [True, -1, float("nan"), float("inf"), None],
)
def test_forecast_rejects_invalid_campaign_values(bad_value):
    with pytest.raises(ValueError):
        forecast_campaign(
            campaign(monthly_budget=bad_value),
            [],
        )


@pytest.mark.parametrize(
    "bad_value",
    [True, -1, float("nan"), float("inf"), None],
)
def test_forecast_rejects_invalid_historical_values(bad_value):
    with pytest.raises(ValueError):
        forecast_campaign(
            campaign(),
            [{"spend": bad_value, "revenue": 100}],
        )


def test_forecast_does_not_modify_campaign():
    original = campaign()
    before = original.copy()

    forecast_campaign(
        original,
        [{"spend": 100, "revenue": 300}],
    )

    assert original == before


def test_forecast_never_executes_spending():
    result = forecast_campaign(
        campaign(),
        [{"spend": 100, "revenue": 300}],
    )

    assert result["mode"] == "shadow"
    assert result["spending_executed"] is False
    assert result["campaign_modified"] is False
