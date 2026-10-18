from typing import Any

from sqlalchemy.orm import Session

from database import (
    CampaignDB,
    PlatformConnectionDB,
)
from budget_controller import BudgetController


# ============================================================
# PLATFORM EXECUTOR
# ============================================================

class PlatformExecutor:
    """
    Central execution layer.

    IMPORTANT:
    The optimizer never talks directly to Google or Meta.

    Flow:

        Optimizer
            ↓
        Budget Controller
            ↓
        Platform Executor
            ↓
        Google / Meta

    Real API calls will be added once OAuth credentials are
    configured.
    """

    SUPPORTED_PLATFORMS = {
        "google",
        "google_ads",
        "meta",
        "facebook",
        "instagram",
    }

    def __init__(
        self,
        db: Session,
        campaign: CampaignDB,
    ):
        self.db = db
        self.campaign = campaign

    # ========================================================
    # CONNECTION
    # ========================================================

    def get_connection(
        self,
        platform: str,
    ):

        normalized = platform.lower()

        if normalized == "google_ads":
            normalized = "google"

        if normalized in {
            "facebook",
            "instagram",
        }:
            normalized = "meta"

        return (
            self.db.query(PlatformConnectionDB)
            .filter(
                PlatformConnectionDB.user_id
                == self.campaign.user_id,

                PlatformConnectionDB.platform
                == normalized,

                PlatformConnectionDB.is_active
                == True,
            )
            .first()
        )

    # ========================================================
    # CHECK PLATFORM
    # ========================================================

    def check_platform(
        self,
        platform: str,
    ):

        normalized = platform.lower()

        if normalized == "google_ads":
            normalized = "google"

        if normalized in {
            "facebook",
            "instagram",
        }:
            normalized = "meta"

        if normalized not in {
            "google",
            "meta",
        }:
            return {
                "connected": False,
                "platform": normalized,
                "reason": "Unsupported platform",
            }

        connection = self.get_connection(
            normalized
        )

        if not connection:
            return {
                "connected": False,
                "platform": normalized,
                "reason": "Platform account is not connected",
            }

        return {
            "connected": True,
            "platform": normalized,
            "account_id": connection.account_id,
        }

    # ========================================================
    # CREATE EXECUTION REQUEST
    # ========================================================

    def prepare_execution(
        self,
        allocation: dict[str, Any],
    ):

        platform = allocation.get(
            "platform",
            "unknown",
        )

        requested_budget = float(
            allocation.get(
                "budget",
                0,
            )
        )

        platform_status = self.check_platform(
            platform
        )

        if not platform_status["connected"]:
            return {
                "approved": False,
                "executed": False,
                "reason": platform_status["reason"],
                "platform": platform,
                "requested_budget": requested_budget,
            }

        controller = BudgetController(
            db=self.db,
            campaign=self.campaign,
        )

        request = controller.build_execution_request(
            allocation
        )

        if not request["approved"]:
            return {
                **request,
                "executed": False,
            }

        return {
            **request,
            "executed": False,
            "platform_ready": True,
        }

    # ========================================================
    # GOOGLE EXECUTION PLACEHOLDER
    # ========================================================

    def execute_google(
        self,
        request: dict[str, Any],
    ):

        """
        Real Google Ads API execution will be implemented here.

        For now this intentionally does NOT spend money.
        """

        return {
            "executed": False,
            "platform": "google",
            "reason": (
                "Google Ads API credentials are not configured."
            ),
            "request": request,
        }

    # ========================================================
    # META EXECUTION PLACEHOLDER
    # ========================================================

    def execute_meta(
        self,
        request: dict[str, Any],
    ):

        """
        Real Meta Marketing API execution will be implemented here.

        For now this intentionally does NOT spend money.
        """

        return {
            "executed": False,
            "platform": "meta",
            "reason": (
                "Meta Marketing API credentials are not configured."
            ),
            "request": request,
        }

    # ========================================================
    # EXECUTE
    # ========================================================

    def execute(
        self,
        allocation: dict[str, Any],
    ):

        request = self.prepare_execution(
            allocation
        )

        if not request.get("approved"):
            return request

        platform = str(
            request.get(
                "platform",
                "",
            )
        ).lower()

        if platform in {
            "google",
            "google_ads",
        }:
            return self.execute_google(
                request
            )

        if platform in {
            "meta",
            "facebook",
            "instagram",
        }:
            return self.execute_meta(
                request
            )

        return {
            "executed": False,
            "reason": "Unsupported platform",
            "request": request,
        }


# ============================================================
# PLATFORM DATA SYNC
# ============================================================

def sync_platform_data(
    db: Session,
    campaign: CampaignDB,
    platform: str,
):
    """
    Placeholder for importing performance data from Google
    Ads or Meta.

    Later this will retrieve:

    - impressions
    - clicks
    - spend
    - conversions
    - revenue
    - campaigns
    - ad sets
    - ads
    - audiences
    - geography
    - dates
    - hours

    The imported data will feed the ML and optimization engines.
    """

    executor = PlatformExecutor(
        db=db,
        campaign=campaign,
    )

    status = executor.check_platform(
        platform
    )

    if not status["connected"]:
        return {
            "synced": False,
            "platform": platform,
            "reason": status["reason"],
        }

    return {
        "synced": False,
        "platform": platform,
        "reason": (
            "Platform connected. "
            "Data synchronization will be implemented "
            "with the platform API credentials."
        ),
    }
