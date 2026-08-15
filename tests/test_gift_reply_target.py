import importlib.util
import sys
import types
import unittest
from pathlib import Path


STATE = {
    "users": {},
    "resolve_calls": [],
    "balance_calls": [],
}


def _clone_user(user):
    return {
        key: (list(value) if key == "inventory" else value)
        for key, value in user.items()
    }


def _ensure_user_exists(tg_user):
    return STATE["users"][tg_user.id]


async def _resolve_target(update, context, specific_arg=None):
    STATE["resolve_calls"].append(specific_arg)
    reply = getattr(update.effective_message, "reply_to_message", None)
    if reply:
        return STATE["users"][reply.from_user.id], None
    if specific_arg and specific_arg.isdigit():
        return STATE["users"][int(specific_arg)], None
    return None, "No target"


def _remove_one_inventory_item(sender, item_id):
    inventory = sender.get("inventory", [])
    for index, item in enumerate(inventory):
        if item.get("id") == item_id:
            return inventory.pop(index)
    return None


class _UsersCollection:
    def update_one(self, filter_doc, update_doc):
        user = STATE["users"][filter_doc["user_id"]]
        if "$push" in update_doc and "inventory" in update_doc["$push"]:
            user.setdefault("inventory", []).append(update_doc["$push"]["inventory"])


def _adjust_user_balance(user_id, amount, *args, **kwargs):
    STATE["balance_calls"].append((user_id, amount, kwargs.get("source")))
    user = STATE["users"][user_id]
    new_balance = user.get("balance", 0) + amount
    if kwargs.get("require_gte") and user.get("balance", 0) < kwargs["require_gte"]:
        return False
    user["balance"] = new_balance
    return True


fake_utils = types.ModuleType("kazumi.utils")
fake_utils.ensure_user_exists = _ensure_user_exists
fake_utils.resolve_target = _resolve_target
fake_utils.get_mention = lambda user: user.get("name", "User")
fake_utils.format_money = lambda amount: f"${amount:,}"
fake_utils.stylize_text = lambda text: text
fake_utils.remove_one_inventory_item = _remove_one_inventory_item

fake_database = types.ModuleType("kazumi.database")
fake_database.users_collection = _UsersCollection()

fake_ledger = types.ModuleType("kazumi.ledger")
fake_ledger.adjust_user_balance = _adjust_user_balance

fake_config = types.ModuleType("kazumi.config")
fake_config.SHOP_ITEMS = {}

_stubs = {
    "kazumi.utils": fake_utils,
    "kazumi.database": fake_database,
    "kazumi.ledger": fake_ledger,
    "kazumi.config": fake_config,
}
_saved = {name: sys.modules.get(name) for name in _stubs}
sys.modules.update(_stubs)
try:
    module_path = Path(__file__).parents[1] / "kazumi" / "plugins" / "gift.py"
    spec = importlib.util.spec_from_file_location("gift_subject", module_path)
    gift = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gift)
finally:
    for name, module in _saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


class _Message:
    def __init__(self, reply_to_message=None):
        self.reply_to_message = reply_to_message
        self.sent = []

    async def reply_text(self, text, **kwargs):
        self.sent.append((text, kwargs))


class GiftReplyTargetTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        STATE["users"].clear()
        STATE["resolve_calls"].clear()
        STATE["balance_calls"].clear()
        STATE["users"][1] = {
            "user_id": 1,
            "name": "Sender",
            "balance": 5000,
            "inventory": [{"id": "knife", "name": "Knife"}],
        }
        STATE["users"][2] = {
            "user_id": 2,
            "name": "Receiver",
            "balance": 200,
            "inventory": [],
        }

    async def test_item_gift_works_on_reply_without_tag_argument(self):
        reply_user = types.SimpleNamespace(id=2)
        message = _Message(reply_to_message=types.SimpleNamespace(from_user=reply_user))
        update = types.SimpleNamespace(
            effective_user=types.SimpleNamespace(id=1),
            effective_chat=types.SimpleNamespace(id=-100),
            effective_message=message,
            message=message,
        )
        context = types.SimpleNamespace(args=["knife"])

        await gift.gift_command(update, context)

        self.assertEqual(STATE["resolve_calls"], [None])
        self.assertEqual(STATE["users"][1]["inventory"], [])
        self.assertEqual(STATE["users"][2]["inventory"][0]["id"], "knife")
        self.assertIn("Gift Delivered", message.sent[0][0])

    async def test_coin_gift_works_on_reply_without_tag_argument(self):
        reply_user = types.SimpleNamespace(id=2)
        message = _Message(reply_to_message=types.SimpleNamespace(from_user=reply_user))
        update = types.SimpleNamespace(
            effective_user=types.SimpleNamespace(id=1),
            effective_chat=types.SimpleNamespace(id=-100),
            effective_message=message,
            message=message,
        )
        context = types.SimpleNamespace(args=["coins", "1000"])

        await gift.gift_command(update, context)

        self.assertEqual(STATE["resolve_calls"], [None])
        self.assertEqual(STATE["users"][1]["balance"], 4000)
        self.assertEqual(STATE["users"][2]["balance"], 1200)
        self.assertEqual(len(STATE["balance_calls"]), 2)
        self.assertIn("Gift Sent", message.sent[0][0])


if __name__ == "__main__":
    unittest.main()
