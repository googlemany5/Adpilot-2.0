import secrets
import uuid

import requests

BASE = "http://127.0.0.1:8000"


def test_campaigns_endpoint():
    email = f"campaign-test-{uuid.uuid4().hex}@example.com"
    password = secrets.token_urlsafe(24)

    registration = requests.post(
        f"{BASE}/auth/register",
        json={
            "email": email,
            "password": password,
            "first_name": "Campaign",
            "last_name": "Test",
        },
        timeout=15,
    )
    assert registration.status_code in (200, 201), (
        f"Registration failed: HTTP {registration.status_code}"
    )

    login = requests.post(
        f"{BASE}/auth/login",
        data={"username": email, "password": password},
        timeout=15,
    )
    assert login.status_code == 200, (
        f"Login failed: HTTP {login.status_code}"
    )

    token = login.json().get("access_token")
    assert token, "Login response did not contain an access token."

    response = requests.get(
        f"{BASE}/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    assert response.status_code == 200, (
        f"Campaign request failed: HTTP {response.status_code}"
    )

    data = response.json()
    campaigns = (
        data if isinstance(data, list) else data.get("campaigns", [])
    )
    assert isinstance(campaigns, list), (
        "Expected campaigns endpoint to return a list."
    )

    print(f"\nCampaign endpoint passed; found {len(campaigns)} campaigns.")
