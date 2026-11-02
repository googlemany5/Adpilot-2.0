import math
import unittest
from unittest.mock import patch
from datetime import date
from types import SimpleNamespace

from budget_controller import BudgetController
from platform_executor import PlatformExecutor


class BudgetInputValidationTests(unittest.TestCase):
    def setUp(self):
        today = date.today()
        self.campaign = SimpleNamespace(
            id=1,
            user_id=1,
            status="active",
            monthly_budget=3000.0,
            spent_today=0.0,
            spent_this_month=0.0,
            discovery_budget=500.0,
            discovery_spent=0.0,
            spending_date=today,
            spending_month=today.month,
            spending_year=today.year,
        )

    def test_budget_controller_rejects_malformed_amounts(self):
        controller = BudgetController(db=None, campaign=self.campaign)

        for value in ("abc", None, float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value):
                result = controller.build_execution_request(
                    {"platform": "google", "budget": value}
                )
                self.assertFalse(result["approved"])
                self.assertEqual(result["approved_budget"], 0.0)
                self.assertFalse(result["platform_execution"])

    def test_executor_rejects_malformed_amounts_without_crashing(self):
        executor = PlatformExecutor(db=None, campaign=self.campaign)

        with patch.object(
            executor,
            "check_platform",
            return_value={"connected": True, "platform": "google"},
        ):
            for value in ("abc", None, float("nan"), float("inf"), -float("inf")):
                with self.subTest(value=value):
                    result = executor.prepare_execution(
                        {"platform": "google", "budget": value}
                    )
                    self.assertFalse(result["approved"])
                    self.assertFalse(result["executed"])
                    self.assertEqual(result["approved_budget"], 0.0)


if __name__ == "__main__":
    unittest.main()
