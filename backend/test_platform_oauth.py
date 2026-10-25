from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, PlatformOAuthStateDB
from platform_oauth import create_oauth_state, consume_oauth_state


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_valid_state_can_be_consumed_once(db):
    state = create_oauth_state(db, user_id=123, platform="google")

    assert consume_oauth_state(db, state, "google") == 123

    with pytest.raises(HTTPException) as exc:
        consume_oauth_state(db, state, "google")

    assert exc.value.status_code == 400


def test_invalid_state_is_rejected(db):
    with pytest.raises(HTTPException) as exc:
        consume_oauth_state(db, "not-a-real-state", "google")

    assert exc.value.status_code == 400


def test_state_cannot_be_used_for_another_platform(db):
    state = create_oauth_state(db, user_id=123, platform="google")

    with pytest.raises(HTTPException) as exc:
        consume_oauth_state(db, state, "meta")

    assert exc.value.status_code == 400


def test_expired_state_is_rejected(db):
    state = create_oauth_state(db, user_id=123, platform="google")
    state_hash = __import__("hashlib").sha256(state.encode()).hexdigest()

    row = (
        db.query(PlatformOAuthStateDB)
        .filter_by(state_hash=state_hash)
        .one()
    )
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        consume_oauth_state(db, state, "google")

    assert exc.value.status_code == 400
