import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
import main


class FakeQuery:
    def __init__(self, campaign):
        self.campaign = campaign

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.campaign


class FakeDB:
    def __init__(self, campaign):
        self.campaign = campaign

    def query(self, model):
        return FakeQuery(self.campaign)


class PlatformExecutionGuardTests(unittest.TestCase):
    def test_inactive_campaigns_cannot_execute(self):
        for status in ("draft", "paused", "emergency_paused"):
            with self.subTest(status=status):
                campaign = SimpleNamespace(
                    id=1,
                    user_id=1,
                    status=status,
                )
                db = FakeDB(campaign)

                with patch.object(main, "PlatformExecutor") as executor:
                    with self.assertRaises(HTTPException) as error:
                        main.platform_execute(
                            campaign_id=1,
                            allocation={},
                            current_user=SimpleNamespace(id=1),
                            db=db,
                        )

                self.assertEqual(error.exception.status_code, 409)
                executor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
