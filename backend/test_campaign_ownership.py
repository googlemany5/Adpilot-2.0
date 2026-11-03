from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from main import (
    CampaignDB,
    _GrowthCampaignDB,
    get_campaign,
    get_campaigns,
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


# Additional tests for campaign update and deletion ownership.

from main import update_campaign, delete_campaign


class TrackingDB(FakeDB):
    def __init__(self, result):
        super().__init__(result)
        self.committed = False
        self.deleted = None
        self.refreshed = None

    def commit(self):
        self.committed = True

    def refresh(self, obj):
        self.refreshed = obj

    def delete(self, obj):
        self.deleted = obj


def test_update_campaign_checks_owner():
    user = SimpleNamespace(id=123)
    campaign = SimpleNamespace(
        id=7,
        user_id=user.id,
        name="Original",
        monthly_budget=300,
    )
    db = TrackingDB(campaign)
    data = SimpleNamespace(
        model_dump=lambda exclude_unset: {
            "name": "Updated",
            "monthly_budget": 400,
        }
    )

    result = update_campaign(7, data, user, db)

    assert result is campaign
    assert campaign.name == "Updated"
    assert campaign.monthly_budget == 400
    assert db.committed
    assert db.refreshed is campaign
    assert_user_ownership_filter(db, user.id)


def test_update_campaign_rejects_other_users_campaign():
    user = SimpleNamespace(id=123)
    db = TrackingDB(None)
    data = SimpleNamespace(
        model_dump=lambda exclude_unset: {"name": "Unauthorized"}
    )

    with pytest.raises(HTTPException) as exc:
        update_campaign(7, data, user, db)

    assert exc.value.status_code == 404
    assert not db.committed
    assert_user_ownership_filter(db, user.id)


def test_delete_campaign_checks_owner():
    user = SimpleNamespace(id=123)
    campaign = SimpleNamespace(id=7, user_id=user.id)
    db = TrackingDB(campaign)

    result = delete_campaign(7, user, db)

    assert result == {"message": "Campaign deleted"}
    assert db.deleted is campaign
    assert db.committed
    assert_user_ownership_filter(db, user.id)


def test_delete_campaign_rejects_other_users_campaign():
    user = SimpleNamespace(id=123)
    db = TrackingDB(None)

    with pytest.raises(HTTPException) as exc:
        delete_campaign(7, user, db)

    assert exc.value.status_code == 404
    assert db.deleted is None
    assert not db.committed
    assert_user_ownership_filter(db, user.id)


def test_campaign_list_filters_by_logged_in_user():
    user = SimpleNamespace(id=123)
    own_campaign = SimpleNamespace(id=7, user_id=123)
    db = FakeDB([own_campaign])

    db.query_result.all = lambda: db.query_result.result

    result = get_campaigns(user, db)

    assert result == [own_campaign]
    assert db.queried_model is CampaignDB
    assert_user_ownership_filter(db, user.id)
