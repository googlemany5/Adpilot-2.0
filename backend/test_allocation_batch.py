import unittest
from datetime import date
from types import SimpleNamespace

from budget_controller import validate_allocation_batch


class AllocationBatchTests(unittest.TestCase):
    def make_campaign(self):
        return SimpleNamespace(
            id=99999,
            daily_target=100.0,
            monthly_budget=3000.0,
            discovery_budget=500.0,
            spent_today=0.0,
            spent_this_month=0.0,
            discovery_spent=0.0,
            status="active",
            spending_date=date.today(),
            spending_month=date.today().month,
        )

    def test_multiple_allocations_stay_within_daily_budget(self):
        result = validate_allocation_batch(
            db=None,
            campaign=self.make_campaign(),
            allocations=[
                {"budget": 80, "spending_type": "normal"},
                {"budget": 80, "spending_type": "normal"},
                {"budget": 80, "spending_type": "normal"},
            ],
        )

        self.assertLessEqual(result["total_approved"], 100.0)
        self.assertEqual(len(result["allocations"]), 3)
        self.assertAlmostEqual(
            result["total_approved"],
            sum(item["approved_budget"] for item in result["allocations"]),
        )

    def test_batch_does_not_approve_more_than_daily_capacity(self):
        result = validate_allocation_batch(
            db=None,
            campaign=self.make_campaign(),
            allocations=[
                {"budget": 80, "spending_type": "normal"},
                {"budget": 80, "spending_type": "normal"},
                {"budget": 80, "spending_type": "normal"},
            ],
        )

        self.assertLessEqual(result["total_approved"], 100.0)
        self.assertLess(result["total_approved"], result["total_requested"])
        self.assertEqual(result["total_requested"], 240.0)

    def test_empty_batch_approves_nothing(self):
        result = validate_allocation_batch(
            db=None,
            campaign=self.make_campaign(),
            allocations=[],
        )

        self.assertEqual(result["total_requested"], 0.0)
        self.assertEqual(result["total_approved"], 0.0)
        self.assertEqual(result["allocations"], [])




    def test_monthly_budget_limits_batch(self):
        campaign = self.make_campaign()
        campaign.spent_this_month = 2995.0

        result = validate_allocation_batch(
            db=None,
            campaign=campaign,
            allocations=[
                {"budget": 80, "spending_type": "normal"},
                {"budget": 80, "spending_type": "normal"},
            ],
        )

        self.assertLessEqual(result["total_approved"], 5.0)


    def test_discovery_budget_limits_batch(self):
        campaign = self.make_campaign()
        campaign.discovery_budget = 10.0

        result = validate_allocation_batch(
            db=None,
            campaign=campaign,
            allocations=[
                {"budget": 8, "spending_type": "discovery"},
                {"budget": 8, "spending_type": "discovery"},
            ],
        )

        self.assertLessEqual(result["total_approved"], 10.0)


    def test_negative_and_non_finite_requests_do_not_increase_totals(self):
        result = validate_allocation_batch(
            db=None,
            campaign=self.make_campaign(),
            allocations=[
                {"budget": -50, "spending_type": "normal"},
                {"budget": float("nan"), "spending_type": "normal"},
                {"budget": float("inf"), "spending_type": "normal"},
            ],
        )

        self.assertEqual(result["total_requested"], 0.0)
        self.assertEqual(result["total_approved"], 0.0)


    def test_unknown_spending_type_is_not_approved(self):
        result = validate_allocation_batch(
            db=None,
            campaign=self.make_campaign(),
            allocations=[
                {"budget": 20, "spending_type": "unknown"},
            ],
        )

        self.assertEqual(result["total_approved"], 0.0)
        self.assertFalse(result["allocations"][0]["approved"])


    def test_missing_budget_is_not_approved(self):
        result = validate_allocation_batch(
            db=None,
            campaign=self.make_campaign(),
            allocations=[
                {"spending_type": "normal"},
            ],
        )

        self.assertEqual(result["total_approved"], 0.0)
if __name__ == "__main__":
    unittest.main()
