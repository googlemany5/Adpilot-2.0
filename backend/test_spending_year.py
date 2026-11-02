import unittest
from datetime import date
from types import SimpleNamespace

from safety import reset_monthly_if_needed


class SpendingYearTests(unittest.TestCase):
    def make_campaign(self, year=None, month=None):
        today = date.today()

        return SimpleNamespace(
            spending_year=year if year is not None else today.year,
            spending_month=month if month is not None else today.month,
            spent_this_month=750.0,
            spent_today=45.0,
            discovery_spent=100.0,
        )

    def test_previous_year_resets_monthly_spending(self):
        today = date.today()
        campaign = self.make_campaign(year=today.year - 1)

        reset_monthly_if_needed(campaign)

        self.assertEqual(campaign.spent_this_month, 0.0)
        self.assertEqual(campaign.spending_year, today.year)
        self.assertEqual(campaign.spending_month, today.month)

    def test_same_year_and_month_preserves_spending(self):
        campaign = self.make_campaign()

        reset_monthly_if_needed(campaign)

        self.assertEqual(campaign.spent_this_month, 750.0)

    def test_monthly_reset_preserves_daily_and_discovery_counters(self):
        today = date.today()
        campaign = self.make_campaign(year=today.year - 1)

        reset_monthly_if_needed(campaign)

        self.assertEqual(campaign.spent_today, 45.0)
        self.assertEqual(campaign.discovery_spent, 100.0)


if __name__ == "__main__":
    unittest.main()
