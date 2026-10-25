from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from main import (
    CampaignDB,
    _GrowthCampaignDB,
    get_campaign,
    _adpilot_owned_campaign,
)


class FakeQuery:
    def __init__(self, result):
        self.result = result
        self.filters = []

    def filter(self, *conditions):
        self.filters.extend(conditions)
        return self

    def first(self):
        return self.result


class FakeDB:
    def __init__(self, result):
        self.query_result = FakeQuery(result)
        self.queried_model = None

    def query(self, model):
        self.queried_model = model
        return self.query_result


def assert_user_ownership_filter(db, user_id):
    assert db.query_result.filters, "Expected ownership filters"
    assert any(
        getattr(condition, "left", None) is not None
        and condition.left.name == "user_id"
        and getattr(condition.right, "value", None) == user_id
        for condition in db.query_result.filters
    ), "Query must filter by the logged-in user's ID"


def test_standard_campaign_query_checks_owner():
    user = SimpleNamespace(id=123)
    campaign = SimpleNamespace(id=7, user_id=user.id)
    db = FakeDB(campaign)

    result = get_campaign(7, user, db)

    assert result is campaign
    assert db.queried_model is CampaignDB
    assert_user_ownership_filter(db, user.id)


def test_standard_campaign_not_found_for_user_returns_404():
    user = SimpleNamespace(id=123)
    db = FakeDB(None)

    with pytest.raises(HTTPException) as exc:
        get_campaign(7, user, db)

    assert exc.value.status_code == 404
    assert_user_ownership_filter(db, user.id)


def test_growth_campaign_query_checks_owner():
    user = SimpleNamespace(id=456)
    campaign = SimpleNamespace(id=8, user_id=user.id)
    db = FakeDB(campaign)

    result = _adpilot_owned_campaign(8, user, db)

    assert result is campaign
    assert db.queried_model is _GrowthCampaignDB
    assert_user_ownership_filter(db, user.id)


def test_growth_campaign_not_found_for_user_returns_404():
    user = SimpleNamespace(id=456)
    db = FakeDB(None)

    with pytest.raises(HTTPException) as exc:
        _adpilot_owned_campaign(8, user, db)

    assert exc.value.status_code == 404
    assert_user_ownership_filter(db, user.id)
