import requests
from getpass import getpass

BASE = "http://127.0.0.1:8000"
EMAIL = "test@adpilot.ai"

password = getpass("Test account password: ")

# Log in
login = requests.post(
    f"{BASE}/auth/login",
    data={"username": EMAIL, "password": password},
    timeout=15,
)
print("\nLOGIN:", login.status_code)
login.raise_for_status()

token = login.json().get("access_token")
if not token:
    print("Login response:", login.json())
    raise SystemExit("No access token returned.")

headers = {"Authorization": f"Bearer {token}"}

# Fetch campaigns
response = requests.get(
    f"{BASE}/campaigns",
    headers=headers,
    timeout=15,
)
print("CAMPAIGNS:", response.status_code)
response.raise_for_status()

data = response.json()
campaigns = data if isinstance(data, list) else data.get("campaigns", [])

print("\nYour campaigns:")
for campaign in campaigns:
    print(
        f"ID {campaign.get('id')}: "
        f"{campaign.get('name', 'Unnamed')} — "
        f"{campaign.get('status', 'unknown')}"
    )

# Select a campaign
campaign_id = input("\\nEnter the ID of your test campaign: ").strip()

if not campaign_id.isdigit():
    raise SystemExit("Please enter a numeric campaign ID.")

selected = next(
    (c for c in campaigns if c.get("id") == int(campaign_id)),
    None,
)

if selected is None:
    raise SystemExit("That campaign ID was not found.")

print("\nSelected campaign:")
print("ID:", selected.get("id"))
print("Name:", selected.get("name"))
print("Status:", selected.get("status"))
print("\nTEST COMPLETE — no campaign settings were changed.")
