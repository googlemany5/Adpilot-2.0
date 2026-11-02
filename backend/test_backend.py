"""Safe API smoke tests. Requires a running local API server."""

import os
import uuid

import pytest
import requests

BASE = os.getenv("ADPILOT_TEST_BASE_URL", "http://127.0.0.1:8000")
PASSWORD = os.getenv("ADPILOT_TEST_PASSWORD")


def test_health_endpoint():
    response = requests.get(f"{BASE}/health", timeout=10)
    assert response.status_code == 200, response.text


def test_registration_login_and_current_user():
    if not PASSWORD:
        pytest.fail("Set ADPILOT_TEST_PASSWORD before running this test.")

    email = f"smoke-{uuid.uuid4().hex}@adpilot.ai"

    # Register a fresh test user to avoid relying on an old account.
    register = requests.post(
        f"{BASE}/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "first_name": "Smoke",
            "last_name": "Test",
        },
        timeout=10,
    )
    assert register.status_code in (200, 201), (
        f"Registration failed: {register.status_code} {register.text}"
    )

    # Verify login with the newly registered account.
    login = requests.post(
        f"{BASE}/auth/login",
        data={"username": email, "password": PASSWORD},
        timeout=10,
    )
    assert login.status_code == 200, (
        f"Login failed: {login.status_code} {login.text}"
    )

    token = login.json().get("access_token")
    assert token, "Login response did not contain an access token."

    # Verify the token authenticates the user.
    me = requests.get(
        f"{BASE}/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert me.status_code == 200, (
        f"Authenticated user check failed: {me.status_code} {me.text}"
    )

    user = me.json()
    assert user.get("email", "").lower() == email.lower()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
