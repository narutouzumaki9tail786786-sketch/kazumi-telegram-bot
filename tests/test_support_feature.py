import importlib.util
import sys
import types
import unittest
from pathlib import Path

from telegram import InlineKeyboardButton


fake_config = types.ModuleType("kazumi.config")
fake_config.SUPPORT_CHANNEL = "https://t.me/kazumiupdates"
fake_config.SUPPORT_GROUP = "https://t.me/kazumisupport"
fake_config.OWNER_LINK = "https://t.me/kazumiowner"


def _button(text, **kwargs):
    kwargs.pop("style", None)
    return InlineKeyboardButton(text, **kwargs)


fake_utils = types.ModuleType("kazumi.utils")
fake_utils.Button = _button
fake_utils.ensure_user_exists = lambda user: {}
fake_utils.get_mention = lambda user: user.first_name
fake_utils.log_to_channel = lambda *args, **kwargs: None
fake_utils.stylize_text = lambda text: text

_stubs = {"kazumi.config": fake_config, "kazumi.utils": fake_utils}
_saved = {name: sys.modules.get(name) for name in _stubs}
sys.modules.update(_stubs)
try:
    module_path = Path(__file__).parents[1] / "kazumi" / "plugins" / "support.py"
    spec = importlib.util.spec_from_file_location("support_feature_subject", module_path)
    support = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(support)
finally:
    for name, module in _saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


class SupportFeatureTests(unittest.TestCase):
    def test_support_payload_round_trip(self):
        payload = support.support_payload(12345, 50)

        parsed = support.parse_support_payload(payload)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["user_id"], 12345)
        self.assertEqual(parsed["amount"], 50)
        self.assertTrue(parsed["token"])

    def test_invalid_payload_returns_none(self):
        self.assertIsNone(support.parse_support_payload("bad|payload"))

    def test_keyboard_has_buy_buttons_and_dm_link(self):
        markup = support.support_keyboard("KazumiRpgBot")
        callback_data = [
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
            if button.callback_data
        ]
        urls = [
            button.url
            for row in markup.inline_keyboard
            for button in row
            if button.url
        ]

        for amount in (10, 25, 50, 100):
            self.assertIn(f"support_buy|{amount}", callback_data)
        self.assertIn("support_open", callback_data)
        self.assertIn("https://t.me/KazumiRpgBot?start=support", urls)


class _PhotoMessage:
    def __init__(self):
        self.photo = [object()]
        self.caption_edits = []

    async def edit_caption(self, caption, **kwargs):
        self.caption_edits.append((caption, kwargs))

    async def edit_text(self, *args, **kwargs):
        raise AssertionError("photo start cards must edit their caption")


class _SupportQuery:
    def __init__(self, message):
        self.data = "support_open"
        self.message = message
        self.from_user = types.SimpleNamespace(id=123)
        self.answered = False

    async def answer(self, *args, **kwargs):
        self.answered = True


class SupportCallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_boost_button_edits_caption_on_photo_start_card(self):
        message = _PhotoMessage()
        query = _SupportQuery(message)
        update = types.SimpleNamespace(callback_query=query)
        context = types.SimpleNamespace(bot=types.SimpleNamespace(username="KazumiRpgBot"))

        await support.support_callback(update, context)

        self.assertTrue(query.answered)
        self.assertEqual(len(message.caption_edits), 1)
        self.assertEqual(message.caption_edits[0][0], support.support_text())


if __name__ == "__main__":
    unittest.main()
