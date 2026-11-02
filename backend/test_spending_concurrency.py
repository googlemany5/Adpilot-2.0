import threading
import unittest
import tempfile
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, CampaignDB, SpendingTransactionDB
from safety import record_spend


class SpendingConcurrencyTests(unittest.TestCase):
    def test_simultaneous_requests_cannot_use_stale_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "concurrency.db"

            engine = create_engine(
                f"sqlite:///{database_path}",
                connect_args={
                    "check_same_thread": False,
                    "timeout": 30,
                },
            )

            Base.metadata.create_all(engine)
            Session = sessionmaker(bind=engine)

            today = date.today()

            with Session() as db:
                campaign = CampaignDB(
                    user_id=1,
                    name="Concurrency test",
                    monthly_budget=3000.0,
                    discovery_budget=500.0,
                    status="active",
                    spent_today=60.0,
                    spending_date=today,
                    spent_this_month=60.0,
                    spending_month=today.month,
                    spending_year=today.year,
                    discovery_spent=0.0,
                )
                db.add(campaign)
                db.commit()
                campaign_id = campaign.id

            barrier = threading.Barrier(2)
            results = []

            def attempt_spend():
                with Session() as db:
                    try:
                        campaign = (
                            db.query(CampaignDB)
                            .filter(CampaignDB.id == campaign_id)
                            .first()
                        )

                        barrier.wait(timeout=10)

                        record_spend(
                            db=db,
                            campaign=campaign,
                            amount=20.0,
                            platform="test",
                            spending_type="normal",
                        )

                        results.append("approved")

                    except ValueError:
                        results.append("rejected")

                    except Exception as error:
                        results.append(f"error: {error}")

            threads = [
                threading.Thread(target=attempt_spend)
                for _ in range(2)
            ]

            for thread in threads:
                thread.start()

            for thread in threads:
                thread.join(timeout=40)

            self.assertTrue(
                all(not thread.is_alive() for thread in threads),
                "A spending request became stuck.",
            )

            self.assertEqual(results.count("approved"), 1, results)
            self.assertEqual(results.count("rejected"), 1, results)
            self.assertFalse(
                any(result.startswith("error:") for result in results),
                results,
            )

            with Session() as db:
                campaign = db.get(CampaignDB, campaign_id)

                transactions = (
                    db.query(SpendingTransactionDB)
                    .filter(
                        SpendingTransactionDB.campaign_id == campaign_id
                    )
                    .all()
                )

                self.assertEqual(campaign.spent_today, 80.0)
                self.assertEqual(len(transactions), 1)

            engine.dispose()


if __name__ == "__main__":
    unittest.main()
