from typing import Any


# ============================================================
# CAMPAIGN RULE ENGINE
# ============================================================

def evaluate_campaign_rules(
    campaign: dict[str, Any],
    allocation: dict[str, Any],
):
    """
    Customer/business rules that must be respected before
    an AI allocation can be used.

    This is intentionally separate from the optimizer.
    """

    rules = campaign.get(
        "rules",
        {},
    )

    # --------------------------------------------------------
    # Allowed platforms
    # --------------------------------------------------------

    allowed_platforms = rules.get(
        "allowed_platforms"
    )

    if allowed_platforms:

        platform = str(
            allocation.get(
                "platform",
                "",
            )
        ).lower()

        normalized = {
            str(item).lower()
            for item in allowed_platforms
        }

        if platform not in normalized:
            return False, (
                "Platform is not allowed by campaign rules."
            )

    # --------------------------------------------------------
    # Allowed countries
    # --------------------------------------------------------

    allowed_countries = rules.get(
        "allowed_countries"
    )

    if allowed_countries:

        country = allocation.get(
            "country"
        )

        if country not in allowed_countries:
            return False, (
                "Country is not allowed by campaign rules."
            )

    # --------------------------------------------------------
    # Blocked countries
    # --------------------------------------------------------

    blocked_countries = rules.get(
        "blocked_countries",
        [],
    )

    country = allocation.get(
        "country"
    )

    if country in blocked_countries:
        return False, (
            "Country is blocked by campaign rules."
        )

    # --------------------------------------------------------
    # Maximum allocation
    # --------------------------------------------------------

    maximum_allocation = rules.get(
        "maximum_allocation"
    )

    if maximum_allocation is not None:

        budget = float(
            allocation.get(
                "budget",
                0,
            )
        )

        if budget > float(
            maximum_allocation
        ):
            return False, (
                "Allocation exceeds campaign maximum."
            )

    return True, "approved"


# ============================================================
# FILTER ALLOCATIONS
# ============================================================

def filter_allocations(
    campaign: dict[str, Any],
    allocations: list[dict[str, Any]],
):

    approved = []
    rejected = []

    for allocation in allocations:

        allowed, reason = evaluate_campaign_rules(
            campaign,
            allocation,
        )

        if allowed:
            approved.append(allocation)

        else:
            rejected.append({
                "allocation": allocation,
                "reason": reason,
            })

    return {
        "approved": approved,
        "rejected": rejected,
    }
