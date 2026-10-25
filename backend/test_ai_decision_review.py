from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from main import approve_ai_decision, reject_ai_decision
from auth import require_admin


class FakeQuery:
    def __init__(self, decision):
        self.decision = decision

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.decision


class FakeDB:
    def __init__(self, decision):
        self.decision = decision
        self.commit_count = 0

    def query(self, model):
        return FakeQuery(self.decision)

    def commit(self):
        self.commit_count += 1


def make_decision(status="shadow"):
    return SimpleNamespace(id=1, status=status)


def make_admin():
    return SimpleNamespace(is_admin=True)


def test_non_admin_is_forbidden():
    with pytest.raises(HTTPException) as exc:
        require_admin(SimpleNamespace(is_admin=False))

    assert exc.value.status_code == 403


def test_admin_is_allowed():
    admin = make_admin()
    assert require_admin(admin) is admin


def test_approve_shadow_decision():
    decision = make_decision()
    db = FakeDB(decision)

    result = approve_ai_decision(1, make_admin(), db)

    assert result["status"] == "approved"
    assert decision.status == "approved"
    assert db.commit_count == 1


def test_reject_shadow_decision():
    decision = make_decision()
    db = FakeDB(decision)

    result = reject_ai_decision(1, make_admin(), db)

    assert result["status"] == "rejected"
    assert decision.status == "rejected"
    assert db.commit_count == 1


@pytest.mark.parametrize("status", ["approved", "rejected", "blocked"])
def test_cannot_approve_decision_that_is_not_shadow(status):
    db = FakeDB(make_decision(status))

    with pytest.raises(HTTPException) as exc:
        approve_ai_decision(1, make_admin(), db)

    assert exc.value.status_code == 409
    assert db.commit_count == 0


@pytest.mark.parametrize("status", ["approved", "rejected", "blocked"])
def test_cannot_reject_decision_that_is_not_shadow(status):
    db = FakeDB(make_decision(status))

    with pytest.raises(HTTPException) as exc:
        reject_ai_decision(1, make_admin(), db)

    assert exc.value.status_code == 409
    assert db.commit_count == 0


def test_approve_missing_decision_returns_404():
    db = FakeDB(None)

    with pytest.raises(HTTPException) as exc:
        approve_ai_decision(999999, make_admin(), db)

    assert exc.value.status_code == 404
    assert db.commit_count == 0


def test_reject_missing_decision_returns_404():
    db = FakeDB(None)

    with pytest.raises(HTTPException) as exc:
        reject_ai_decision(999999, make_admin(), db)

    assert exc.value.status_code == 404
    assert db.commit_count == 0
