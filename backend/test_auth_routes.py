import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth import get_db, hash_password, create_access_token
from database import Base, UserDB, SubscriptionDB
from main import app


@pytest.fixture
def auth_route_setup(monkeypatch):
    monkeypatch.setenv("ADPILOT_ENVIRONMENT", "development")

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(bind=engine)

    TestingSession = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    db = TestingSession()

    def override_get_db():
        yield db

    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = override_get_db

    client = TestClient(app)

    yield client, db

    client.close()
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous_overrides)

    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def create_test_user(db, email="existing@example.com"):
    password = "AdPilot-Test-Password-123!"

    user = UserDB(
        email=email,
        password_hash=hash_password(password),
        is_active=True,
        is_admin=False,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user, password


def test_registration_creates_user_and_subscription(
    auth_route_setup,
):
    client, db = auth_route_setup

    response = client.post(
        "/auth/register",
        json={
            "email": "newuser@example.com",
            "password": "Secure-Test-Password-123!",
            "first_name": "Test",
            "last_name": "User",
        },
    )

    assert response.status_code == 200, response.text

    user = db.query(UserDB).filter_by(
        email="newuser@example.com"
    ).first()

    assert user is not None
    assert user.password_hash != "Secure-Test-Password-123!"
    assert user.password_hash.startswith("$argon2")

    subscription = db.query(SubscriptionDB).filter_by(
        user_id=user.id
    ).first()

    assert subscription is not None
    assert subscription.status == "pending"


def test_registration_rejects_duplicate_email(
    auth_route_setup,
):
    client, db = auth_route_setup

    create_test_user(db, "duplicate@example.com")

    response = client.post(
        "/auth/register",
        json={
            "email": "duplicate@example.com",
            "password": "Secure-Test-Password-123!",
        },
    )

    assert response.status_code == 400


def test_registration_rejects_short_password(
    auth_route_setup,
):
    client, db = auth_route_setup

    response = client.post(
        "/auth/register",
        json={
            "email": "short@example.com",
            "password": "123",
        },
    )

    assert response.status_code == 422


def test_login_returns_valid_access_token(
    auth_route_setup,
):
    client, db = auth_route_setup

    user, password = create_test_user(db)

    response = client.post(
        "/auth/login",
        data={
            "username": user.email,
            "password": password,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["access_token"]
    assert data["token_type"] == "bearer"
    assert data["user"]["id"] == user.id


def test_login_rejects_wrong_password(
    auth_route_setup,
):
    client, db = auth_route_setup

    user, _ = create_test_user(db)

    response = client.post(
        "/auth/login",
        data={
            "username": user.email,
            "password": "Definitely-Wrong-Password",
        },
    )

    assert response.status_code == 401


def test_current_user_requires_authentication(
    auth_route_setup,
):
    client, _ = auth_route_setup

    response = client.get("/auth/me")

    assert response.status_code == 401


def test_current_user_accepts_valid_token(
    auth_route_setup,
):
    client, db = auth_route_setup

    user, _ = create_test_user(db)

    token = create_access_token(user.id)

    response = client.get(
        "/auth/me",
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    assert response.status_code == 200
    assert response.json()["id"] == user.id
    assert response.json()["email"] == user.email


def test_current_user_rejects_invalid_token(
    auth_route_setup,
):
    client, _ = auth_route_setup

    response = client.get(
        "/auth/me",
        headers={
            "Authorization": "Bearer invalid-token"
        },
    )

    assert response.status_code == 401


def test_inactive_user_cannot_login_or_access_account(
    auth_route_setup,
):
    client, db = auth_route_setup

    user, password = create_test_user(db)

    token = create_access_token(user.id)

    user.is_active = False
    db.commit()

    login = client.post(
        "/auth/login",
        data={
            "username": user.email,
            "password": password,
        },
    )

    assert login.status_code == 401

    me = client.get(
        "/auth/me",
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    assert me.status_code == 401
