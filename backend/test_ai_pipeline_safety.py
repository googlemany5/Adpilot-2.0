from ai_pipeline import prepare_decision_fields


def test_fully_approved_allocation():
    result = prepare_decision_fields(
        {"budget": 80, "reason": "Good experiment"},
        {
            "requested_budget": 80,
            "approved_budget": 80,
            "approved": True,
            "reason": "Within limits",
        },
    )
    assert result["status"] == "shadow"
    assert result["recommended_budget"] == 80


def test_partially_approved_allocation():
    result = prepare_decision_fields(
        {"budget": 100, "reason": "Good experiment"},
        {
            "requested_budget": 100,
            "approved_budget": 40,
            "approved": True,
            "reason": "Budget capped",
        },
    )
    assert result["status"] == "shadow"
    assert result["recommended_budget"] == 40
    assert "Requested budget: $100.00" in result["reason"]


def test_blocked_allocation():
    result = prepare_decision_fields(
        {"budget": 100},
        {
            "requested_budget": 100,
            "approved_budget": 0,
            "approved": False,
            "reason": "Campaign is paused",
        },
    )
    assert result["status"] == "blocked"
    assert result["recommended_budget"] == 0


def test_invalid_amounts_are_blocked():
    result = prepare_decision_fields(
        {"budget": float("inf")},
        {
            "requested_budget": float("inf"),
            "approved_budget": float("nan"),
            "approved": True,
            "reason": "Invalid amounts",
        },
    )
    assert result["status"] == "blocked"
    assert result["recommended_budget"] == 0
