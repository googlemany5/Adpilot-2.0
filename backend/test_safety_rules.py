from datetime import date
from types import SimpleNamespace

from safety import validate_spend


def fake_campaign(
    status="active",
    monthly_budget=3000.0,
    spent_today=0.0,
    spent_this_month=0.0,
    discovery_budget=500.0,
    discovery_spent=0.0,
):
    today = date.today()

    return SimpleNamespace(
        id=999999,
        status=status,
        monthly_budget=monthly_budget,
        spent_today=spent_today,
        spent_this_month=spent_this_month,
        discovery_budget=discovery_budget,
        discovery_spent=discovery_spent,
        spending_date=today,
        spending_month=today.month,
    )


tests = [
    (
        "Draft campaign blocked",
        fake_campaign(status="draft"),
        10,
        "normal",
        False,
        "Campaign is not active.",
    ),
    (
        "Emergency-paused campaign blocked",
        fake_campaign(status="emergency_paused"),
        10,
        "normal",
        False,
        "Campaign is not active.",
    ),
    (
        "Daily budget limit enforced",
        fake_campaign(spent_today=100),
        1,
        "normal",
        False,
        "Daily advertising limit exceeded.",
    ),
    (
        "Monthly budget limit enforced",
        fake_campaign(spent_this_month=3000),
        1,
        "normal",
        False,
        "Monthly advertising limit exceeded.",
    ),
    (
        "Discovery budget limit enforced",
        fake_campaign(discovery_budget=50, discovery_spent=50),
        1,
        "discovery",
        False,
        "Discovery budget exceeded.",
    ),
    (
        "Negative spending rejected",
        fake_campaign(),
        -1,
        "normal",
        False,
        "Spend amount must be greater than zero.",
    ),
    (
        "NaN spending rejected",
        fake_campaign(),
        float("nan"),
        "normal",
        False,
        "Spend amount must be a finite number.",
    ),
    (
        "Infinite spending rejected",
        fake_campaign(),
        float("inf"),
        "normal",
        False,
        "Spend amount must be a finite number.",
    ),
    (
        "Zero spending rejected",
        fake_campaign(),
        0,
        "normal",
        False,
        "Spend amount must be greater than zero.",
    ),
    (
        "Oversized normal allocation blocked",
        fake_campaign(),
        60,
        "normal",
        False,
        "Allocation is too large for a single decision.",
    ),
    (
        "Oversized discovery allocation blocked",
        fake_campaign(),
        60,
        "discovery",
        False,
        "Allocation is too large for a single decision.",
    ),
    (
        "Invalid spending type rejected",
        fake_campaign(),
        10,
        "discover",
        False,
        "Invalid spending type.",
    ),
    (
        "Valid normal request approved",
        fake_campaign(),
        25,
        "normal",
        True,
        "approved",
    ),
]

failures = 0

print("\nADPILOT SAFETY RULE TESTS")
print("=" * 50)

for name, campaign, amount, spending_type, expected_ok, expected_reason in tests:
    approved, reason = validate_spend(
        campaign=campaign,
        amount=amount,
        spending_type=spending_type,
    )

    passed = approved == expected_ok and reason == expected_reason

    print(f"{'PASS' if passed else 'FAIL'}: {name}")

    if not passed:
        failures += 1
        print(f"  Expected: ({expected_ok}, {expected_reason!r})")
        print(f"  Received: ({approved}, {reason!r})")

print("=" * 50)
print(f"Results: {len(tests) - failures}/{len(tests)} passed")

if failures:
    raise SystemExit(1)

print("All safety tests passed.")
print("No real campaigns or database records were changed.")
