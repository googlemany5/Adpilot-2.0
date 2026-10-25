import requests
import json
import sys
import os

BASE = "http://127.0.0.1:8000"

EMAIL = "test@adpilot.ai"
PASSWORD = os.environ.get("ADPILOT_TEST_PASSWORD")

if not PASSWORD:
    raise SystemExit(
        "Set ADPILOT_TEST_PASSWORD before running this test."
    )


def show(name, response):
    print(f"\n{'='*60}")
    print(name)
    print(f"STATUS: {response.status_code}")
    try:
        data = response.json()
        print(json.dumps(data, indent=2))
        return data
    except:
        print(response.text)
        return None

# Health
r = requests.get(f"{BASE}/health")
show("HEALTH", r)

# Register
r = requests.post(
    f"{BASE}/auth/register",
    json={
        "email": EMAIL,
        "password": PASSWORD,
        "first_name": "Test",
        "last_name": "User",
    },
)
show("REGISTER", r)

# Login
r = requests.post(
    f"{BASE}/auth/login",
    data={
        "username": EMAIL,
        "password": PASSWORD,
    },
)
login = show("LOGIN", r)

if r.status_code != 200:
    print("\nLOGIN FAILED - stopping test.")
    sys.exit(1)

token = login["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Current user
r = requests.get(f"{BASE}/auth/me", headers=headers)
show("AUTH ME", r)

# Create campaign
r = requests.post(
    f"{BASE}/campaigns",
    headers=headers,
    json={
        "name": "Test Campaign",
        "monthly_budget": 3000,
        "discovery_budget": 500,
        "country": "United States",
    },
)
campaign = show("CREATE CAMPAIGN", r)

if r.status_code not in (200, 201):
    print("\nCAMPAIGN CREATION FAILED - stopping test.")
    sys.exit(1)

campaign_id = campaign["id"]

# Get campaigns
r = requests.get(f"{BASE}/campaigns", headers=headers)
show("LIST CAMPAIGNS", r)

# Get campaign
r = requests.get(
    f"{BASE}/campaigns/{campaign_id}",
    headers=headers,
)
show("GET CAMPAIGN", r)

# Budget
r = requests.get(
    f"{BASE}/campaigns/{campaign_id}/budget",
    headers=headers,
)
show("CAMPAIGN BUDGET", r)

# Safety
r = requests.get(
    f"{BASE}/campaigns/{campaign_id}/safety",
    headers=headers,
)
show("SAFETY SUMMARY", r)

# Create experiment
r = requests.post(
    f"{BASE}/campaigns/{campaign_id}/experiments",
    headers=headers,
    json={
        "name": "US Market Test",
        "experiment_type": "country",
        "target": "United States",
        "platform": "meta",
        "budget": 100,
    },
)
experiment = show("CREATE EXPERIMENT", r)

if r.status_code in (200, 201):
    experiment_id = experiment["id"]

    # Experiment result
    r = requests.post(
        f"{BASE}/experiments/{experiment_id}/result",
        headers=headers,
        json={
            "spent": 75,
            "clicks": 50,
            "conversions": 5,
            "revenue": 300,
        },
    )
    show("EXPERIMENT RESULT", r)

# Optimizer
r = requests.get(
    f"{BASE}/campaigns/{campaign_id}/optimization",
    headers=headers,
)
show("OPTIMIZATION", r)

# Safe spend
r = requests.post(
    f"{BASE}/campaigns/{campaign_id}/safe-spend",
    headers=headers,
    params={
        "amount": 25,
        "platform": "meta",
        "country": "United States",
        "spending_type": "normal",
    },
)
show("SAFE SPEND", r)

# Safety again
r = requests.get(
    f"{BASE}/campaigns/{campaign_id}/safety",
    headers=headers,
)
show("SAFETY AFTER SPEND", r)

# Pause
r = requests.post(
    f"{BASE}/campaigns/{campaign_id}/pause",
    headers=headers,
)
show("PAUSE CAMPAIGN", r)

# Resume
r = requests.post(
    f"{BASE}/campaigns/{campaign_id}/resume",
    headers=headers,
)
show("RESUME CAMPAIGN", r)

# Safe spend after resume: should succeed only if campaign is active
r = requests.post(
    f"{BASE}/campaigns/{campaign_id}/safe-spend",
    headers=headers,
    params={
        "amount": 25,
        "platform": "meta",
        "country": "United States",
        "spending_type": "normal",
    },
)
show("SAFE SPEND AFTER RESUME", r)

# Verify recorded spending after the successful attempt
r = requests.get(
    f"{BASE}/campaigns/{campaign_id}/safety",
    headers=headers,
)
show("SAFETY AFTER ACTIVE SPEND", r)

# Platform status
r = requests.get(
    f"{BASE}/platforms/status",
    headers=headers,
)
show("PLATFORM STATUS", r)

# AI pipeline / Shadow Mode
r = requests.post(
    f"{BASE}/campaigns/{campaign_id}/run-ai",
    headers=headers,
)
show("AI PIPELINE / SHADOW MODE", r)

# Shadow decisions
r = requests.get(
    f"{BASE}/campaigns/{campaign_id}/shadow-decisions",
    headers=headers,
)
show("SHADOW DECISIONS", r)

# ML training
r = requests.post(
    f"{BASE}/ml/train",
    headers=headers,
    json=[
        {
            "spend": 100,
            "impressions": 5000,
            "clicks": 100,
            "conversions": 5,
            "revenue": 300,
        },
        {
            "spend": 150,
            "impressions": 7000,
            "clicks": 140,
            "conversions": 8,
            "revenue": 500,
        },
        {
            "spend": 200,
            "impressions": 9000,
            "clicks": 180,
            "conversions": 11,
            "revenue": 700,
        },
    ],
)
show("ML TRAIN", r)

# Emergency pause
r = requests.post(
    f"{BASE}/campaigns/{campaign_id}/emergency-pause",
    headers=headers,
)
show("EMERGENCY PAUSE", r)

print(f"\n{'='*60}")
print("ADPILOT BACKEND TEST FINISHED")
print(f"{'='*60}")
