from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from main import shadow_decisions, CampaignDB, AIDecisionDB


class FakeQuery:
    def __init__(self, result):
        self.result = result
        self.filters = []

    def filter(self, *conditions):
        self.filters.extend(conditions)
        return self

    def order_by(self, *args):
        return self

    def first(self):
        return self.result

    def all(self):
        return self.result


class FakeDB:
    def __init__(self, campaign, decisions=None):
        self.campaign = campaign
        self.decisions = decisions or []
        self.queries = {}

    def query(self, model):
        result = self.campaign if model is CampaignDB else self.decisions
        query = FakeQuery(result)
        self.queries[model] = query
        return query


def assert_filter(query, column_name, expected_value):
    for condition in query.filters:
        left = getattr(condition, "left", None)
        right = getattr(condition, "right", None)
        if (
            getattr(left, "name", None) == column_name
            and getattr(right, "value", object()) == expected_value
        ):
            return
    pytest.fail(
        f"Missing filter {column_name} == {expected_value!r}"
    )


def test_shadow_decisions_checks_campaign_owner_and_status():
    user = SimpleNamespace(id=123)
    campaign = SimpleNamespace(id=7, user_id=123)
    decision = SimpleNamespace(
        id=21,
        decision_type="region",
        platform="meta",
        country="United States",
        region="Montana",
        audience="general",
        day_of_week="Monday",
        hour=10,
        recommended_budget=25.0,
        expected_roas=2.0,
        confidence=0.8,
        reason="Test recommendation",
        status="shadow",
        created_at=datetime(2026, 1, 1),
    )
    db = FakeDB(campaign, [decision])

    result = shadow_decisions(7, user, db)

    assert len(result) == 1
    assert result[0]["id"] == 21
    assert result[0]["status"] == "shadow"

    campaign_query = db.queries[CampaignDB]
    assert_filter(campaign_query, "user_id", user.id)

    decision_query = db.queries[AIDecisionDB]
    assert_filter(decision_query, "campaign_id", campaign.id)
    assert_filter(decision_query, "status", "shadow")


def test_shadow_decisions_returns_404_for_unowned_or_missing_campaign():
    user = SimpleNamespace(id=123)
    db = FakeDB(None)

    with pytest.raises(HTTPException) as exc:
        shadow_decisions(999, user, db)

    assert exc.value.status_code == 404
    assert CampaignDB in db.queries
    assert AIDecisionDB not in db.queries
    assert_filter(db.queries[CampaignDB], "user_id", user.id)
