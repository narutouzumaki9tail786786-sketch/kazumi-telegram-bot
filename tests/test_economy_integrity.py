import copy
import importlib.util
import sys
import types
import unittest
from datetime import datetime
from pathlib import Path


class FakeUsersCollection:
    def __init__(self, docs):
        self.docs = {int(doc["user_id"]): copy.deepcopy(doc) for doc in docs}

    def find_one_and_update(self, query, update, return_document=None):
        user_id = int(query["user_id"])
        doc = self.docs.get(user_id)
        if not doc:
            return None
        balance_filter = query.get("balance")
        if balance_filter and doc.get("balance", 0) < balance_filter.get("$gte", 0):
            return None

        before = copy.deepcopy(doc)
        for key, value in update.get("$inc", {}).items():
            doc[key] = doc.get(key, 0) + value
        for key, value in update.get("$set", {}).items():
            doc[key] = value
        for key, value in update.get("$push", {}).items():
            doc.setdefault(key, []).append(copy.deepcopy(value))
        return before


class FakeLogsCollection:
    def __init__(self):
        self.rows = []

    def insert_one(self, entry):
        self.rows.append(copy.deepcopy(entry))
        return types.SimpleNamespace(inserted_id=len(self.rows))


def load_ledger(users):
    fake_database = types.ModuleType("kazumi.database")
    fake_database.users_collection = users
    fake_database.balance_logs_collection = FakeLogsCollection()

    saved = sys.modules.get("kazumi.database")
    sys.modules["kazumi.database"] = fake_database
    try:
        path = Path(__file__).parents[1] / "kazumi" / "ledger.py"
        spec = importlib.util.spec_from_file_location("economy_integrity_ledger", path)
        ledger = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ledger)
    finally:
        if saved is None:
            sys.modules.pop("kazumi.database", None)
        else:
            sys.modules["kazumi.database"] = saved
    return ledger, fake_database.balance_logs_collection


class EconomyIntegrityTests(unittest.TestCase):
    def test_reward_credit_and_collected_item_are_atomic_and_logged(self):
        users = FakeUsersCollection([{"user_id": 1, "balance": 0, "waifus": []}])
        ledger, logs = load_ledger(users)
        waifu = {"name": "Hamakaze", "rarity": "Rare"}

        result = ledger.adjust_user_balance(
            1,
            500,
            "waifu_collect",
            "Collected Hamakaze",
            extra_push={"waifus": waifu},
        )

        self.assertIsNotNone(result)
        self.assertEqual(users.docs[1]["balance"], 500)
        self.assertEqual(users.docs[1]["waifus"], [waifu])
        self.assertEqual(logs.rows[-1]["category"], "waifu_collect")
        self.assertEqual(logs.rows[-1]["new_balance"], 500)

    def test_failed_receiver_refunds_loan_sender(self):
        users = FakeUsersCollection([{"user_id": 1, "balance": 1_000}])
        ledger, logs = load_ledger(users)

        result = ledger.transfer_user_balance(
            1,
            2,
            500,
            debit_category="loan_lend",
            debit_reason="Loaned coins",
            credit_category="loan_receive",
            credit_reason="Received loan",
            refund_category="loan_refund",
            refund_reason="Loan delivery failed",
        )

        self.assertIsNone(result)
        self.assertEqual(users.docs[1]["balance"], 1_000)
        self.assertEqual([row["delta"] for row in logs.rows], [-500, 500])

    def test_successful_transfer_updates_both_wallets(self):
        users = FakeUsersCollection([
            {"user_id": 1, "balance": 1_000},
            {"user_id": 2, "balance": 100},
        ])
        ledger, _ = load_ledger(users)

        result = ledger.transfer_user_balance(
            1,
            2,
            500,
            debit_category="loan_lend",
            debit_reason="Loaned coins",
            credit_category="loan_receive",
            credit_reason="Received loan",
        )

        self.assertIsNotNone(result)
        self.assertEqual(users.docs[1]["balance"], 500)
        self.assertEqual(users.docs[2]["balance"], 600)

    def test_history_timestamp_uses_configured_local_date_and_utc_iso(self):
        users = FakeUsersCollection([])
        ledger, _ = load_ledger(users)
        stamp = datetime(2026, 6, 15, 20, 30)

        self.assertEqual(ledger.format_history_time(stamp), "16 Jun 02:00 AM")
        self.assertEqual(ledger.to_utc_iso(stamp), "2026-06-15T20:30:00Z")


if __name__ == "__main__":
    unittest.main()
