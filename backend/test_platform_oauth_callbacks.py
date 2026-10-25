import hashlib

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import platform_oauth
from auth import get_db
from database import Base, PlatformConnectionDB, PlatformOAuthStateDB
from main import app
from platform_oauth import create_oauth_state
from token_crypto import decrypt_token


@pytest.fixture
def callback_setup(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False)

    db = TestingSession()

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setenv(
        "ADPILOT_TOKEN_ENCRYPTION_KEY",
        Fernet.generate_key().decode(),
    )
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-google-secret")
    monkeypatch.setenv(
        "GOOGLE_REDIRECT_URI",
        "http://localhost/platform-oauth/google/callback",
    )
    monkeypatch.setenv("META_APP_ID", "test-meta-app")
    monkeypatch.setenv("META_APP_SECRET", "test-meta-secret")
    monkeypatch.setenv(
        "META_REDIRECT_URI",
        "http://localhost/platform-oauth/meta/callback",
    )
    monkeypatch.setenv("META_GRAPH_API_VERSION", "v23.0")

    client = TestClient(app, raise_server_exceptions=True)

    yield client, db

    app.dependency_overrides.clear()
    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def fake_exchange(_url, data):
    if data.get("code") == "bad-provider-response":
        return {"unexpected": "payload"}
    return {
        "access_token": "test-access-token",
        "refresh_token": "test-refresh-token",
    }


def test_google_callback_saves_encrypted_inactive_connection(
    callback_setup, monkeypatch
):
    client, db = callback_setup
    monkeypatch.setattr(
        platform_oauth, "_exchange_oauth_code", fake_exchange
    )
    state = create_oauth_state(db, 123, "google")

    response = client.get(
        "/platform-oauth/google/callback",
        params={"code": "test-code", "state": state},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "pending_account_selection"
    assert "access_token" not in result

    connection = (
        db.query(PlatformConnectionDB)
        .filter_by(user_id=123, platform="google")
        .one()
    )
    assert connection.is_active is False
    assert connection.account_id is None
    assert connection.access_token != "test-access-token"
    assert decrypt_token(connection.access_token) == "test-access-token"
    assert decrypt_token(connection.refresh_token) == "test-refresh-token"


def test_meta_callback_saves_inactive_connection(
    callback_setup, monkeypatch
):
    client, db = callback_setup
    monkeypatch.setattr(
        platform_oauth, "_exchange_oauth_code", fake_exchange
    )
    state = create_oauth_state(db, 456, "meta")

    response = client.get(
        "/platform-oauth/meta/callback",
        params={"code": "test-code", "state": state},
    )

    assert response.status_code == 200
    connection = (
        db.query(PlatformConnectionDB)
        .filter_by(user_id=456, platform="meta")
        .one()
    )
    assert connection.is_active is False
    assert connection.account_id is None


def test_invalid_state_does_not_create_connection(callback_setup):
    client, db = callback_setup

    response = client.get(
        "/platform-oauth/google/callback",
        params={"code": "test-code", "state": "invalid-state"},
    )

    assert response.status_code == 400
    assert db.query(PlatformConnectionDB).count() == 0


def test_provider_error_does_not_create_connection(callback_setup):
    client, db = callback_setup
    state = create_oauth_state(db, 789, "google")

    response = client.get(
        "/platform-oauth/google/callback",
        params={"state": state, "error": "access_denied"},
    )

    assert response.status_code == 400
    assert db.query(PlatformConnectionDB).count() == 0


def test_used_state_cannot_create_second_connection(
    callback_setup, monkeypatch
):
    client, db = callback_setup
    monkeypatch.setattr(
        platform_oauth, "_exchange_oauth_code", fake_exchange
    )
    state = create_oauth_state(db, 321, "google")
    params = {"code": "test-code", "state": state}

    assert client.get(
        "/platform-oauth/google/callback", params=params
    ).status_code == 200

    second = client.get(
        "/platform-oauth/google/callback", params=params
    )
    assert second.status_code == 400
    assert db.query(PlatformConnectionDB).count() == 1
