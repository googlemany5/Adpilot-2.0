"""Central configuration for AdPilot paid plans."""

PAID_PLAN_CAMPAIGN_LIMITS = {
    "starter": 3,
    "pro": 10,
    "business": 25,
}


def get_campaign_limit(plan):
    if not isinstance(plan, str):
        return None
    return PAID_PLAN_CAMPAIGN_LIMITS.get(plan.strip().lower())
