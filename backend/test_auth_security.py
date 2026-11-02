from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, UserDB
from auth import (
    ALGORITHM,
    SECRET_KEY,
    authenticate_user,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)


@pytest.fixture
def auth_setup():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(bind=engine)

    TestingSession = sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
    )

    db = TestingSession()
    password = "AdPilot-Test-Password-123!"

    user = UserDB(
        email="auth-test@example.com",
        password_hash=hash_password(password),
        is_active=True,
        is_admin=False,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    yield {"db": db, "user": user, "password": password}

    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_password_is_hashed_and_verifiable():
    password = "AdPilot-Test-Password-123!"
    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("Wrong-Password", hashed)


def test_password_hash_uses_argon2():
    hashed = hash_password("AdPilot-Test-Password-123!")
    assert hashed.startswith("$argon2")


def test_access_token_contains_user_id():
    token = create_access_token(123)
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

    assert payload["sub"] == "123"
    assert "exp" in payload


def test_expired_token_is_rejected(auth_setup):
    token = jwt.encode(
        {
            "sub": str(auth_setup["user"].id),
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )

    with pytest.raises(HTTPException) as exc:
        get_current_user(token=token, db=auth_setup["db"])

    assert exc.value.status_code == 401


def test_malformed_token_is_rejected(auth_setup):
    with pytest.raises(HTTPException) as exc:
        get_current_user(
            token="not-a-valid-token",
            db=auth_setup["db"],
        )

    assert exc.value.status_code == 401


def test_invalid_jwt_subject_is_rejected(auth_setup):
    token = jwt.encode(
        {
            "sub": ["not", "a", "valid", "user-id"],
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )

    with pytest.raises(HTTPException) as exc:
        get_current_user(token=token, db=auth_setup["db"])

    assert exc.value.status_code == 401


def test_wrong_user_password_fails(auth_setup):
    assert authenticate_user(
        auth_setup["db"],
        auth_setup["user"].email,
        "Definitely-Wrong-Password",
    ) is None


def test_correct_user_password_succeeds(auth_setup):
    result = authenticate_user(
        auth_setup["db"],
        auth_setup["user"].email,
        auth_setup["password"],
    )

    assert result is not None
    assert result.id == auth_setup["user"].id


def test_inactive_user_cannot_authenticate(auth_setup):
    user = auth_setup["user"]
    user.is_active = False
    auth_setup["db"].commit()

    assert authenticate_user(
        auth_setup["db"],
        user.email,
        auth_setup["password"],
    ) is None
