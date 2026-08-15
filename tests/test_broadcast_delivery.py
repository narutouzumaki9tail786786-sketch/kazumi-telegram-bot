import importlib.util
import sys
import types
import unittest
from pathlib import Path


class _Collection:
    def update_one(self, *args, **kwargs):
        return None


fake_utils = types.ModuleType("kazumi.utils")
fake_utils.SUDO_USERS = {1}
fake_database = types.ModuleType("kazumi.database")
fake_database.users_collection = _Collection()
fake_database.groups_collection = _Collection()

_stubs = {"kazumi.utils": fake_utils, "kazumi.database": fake_database}
_saved = {name: sys.modules.get(name) for name in _stubs}
sys.modules.update(_stubs)
try:
    module_path = Path(__file__).parents[1] / "kazumi" / "plugins" / "broadcast.py"
    spec = importlib.util.spec_from_file_location("broadcast_delivery_subject", module_path)
    broadcast = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(broadcast)
finally:
    for name, module in _saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


class _Reply:
    def __init__(self):
        self.reply_markup = object()
        self.copy_calls = []

    async def copy(self, chat_id, **kwargs):
        self.copy_calls.append((chat_id, kwargs))
        return types.SimpleNamespace(message_id=456)


class _Bot:
    def __init__(self):
        self.pin_calls = []

    async def pin_chat_message(self, **kwargs):
        self.pin_calls.append(kwargs)


class BroadcastDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_clean_delivery_keeps_source_inline_keyboard(self):
        reply = _Reply()
        bot = _Bot()

        copied, pinned = await broadcast._deliver_reply_broadcast(
            reply,
            chat_id=-1001,
            clean=True,
            pin=False,
            bot=bot,
        )

        self.assertEqual(copied.message_id, 456)
        self.assertFalse(pinned)
        self.assertIs(reply.copy_calls[0][1]["reply_markup"], reply.reply_markup)

    async def test_pin_uses_the_copied_message_id(self):
        reply = _Reply()
        bot = _Bot()

        _, pinned = await broadcast._deliver_reply_broadcast(
            reply,
            chat_id=-1002,
            clean=True,
            pin=True,
            bot=bot,
        )

        self.assertTrue(pinned)
        self.assertEqual(bot.pin_calls, [{"chat_id": -1002, "message_id": 456, "disable_notification": True}])


if __name__ == "__main__":
    unittest.main()
