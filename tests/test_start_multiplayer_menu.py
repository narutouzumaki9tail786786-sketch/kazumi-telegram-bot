import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path

from telegram import InlineKeyboardButton
from telegram.error import Forbidden


fake_config = types.ModuleType("kazumi.config")
fake_config.SUPPORT_CHANNEL = "https://t.me/updates"
fake_config.SUPPORT_GROUP = "https://t.me/support"
fake_config.OWNER_LINK = "https://t.me/owner"
fake_config.BOT_NAME = "Kazumi"
fake_config.START_IMG_URL = ""
fake_config.HELP_IMG_URL = ""
fake_config.OWNER_ID = 1


def _button(text, **kwargs):
    kwargs.pop("style", None)
    return InlineKeyboardButton(text, **kwargs)


fake_utils = types.ModuleType("kazumi.utils")
fake_utils.Button = _button
fake_utils.SUDO_USERS = set()
fake_utils.apply_custom_emojis = lambda text, remove_fallback=False: text
fake_utils.ensure_user_exists = lambda user: {}
fake_utils.format_display_text = lambda text, parse_mode=None: text
fake_utils.get_mention = lambda user: user.first_name
fake_utils.log_to_channel = lambda *args, **kwargs: None
fake_utils.stylize_text = lambda text: text
fake_utils.track_group = lambda *args, **kwargs: None

_stubs = {"kazumi.config": fake_config, "kazumi.utils": fake_utils}
_saved = {name: sys.modules.get(name) for name in _stubs}
sys.modules.update(_stubs)
try:
    module_path = Path(__file__).parents[1] / "kazumi" / "plugins" / "start.py"
    spec = importlib.util.spec_from_file_location("start_menu_subject", module_path)
    start = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(start)
finally:
    for name, module in _saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


class MultiplayerHelpMenuTests(unittest.TestCase):
    def test_private_start_has_boost_button(self):
        self.assertIn("support_open", _callbacks(start.get_start_keyboard("KazumiRpgBot")))

    def test_main_help_has_multiplayer_button(self):
        self.assertIn("help_multiplayer", _callbacks(start.get_help_keyboard()))

    def test_group_game_shortcuts_open_multiplayer_help(self):
        callbacks = _callbacks(start.get_group_start_keyboard())
        self.assertGreaterEqual(callbacks.count("help_multiplayer"), 2)

    def test_solo_and_multiplayer_commands_are_separated(self):
        solo = start.HELP_SECTIONS["help_games"]
        multiplayer = start.HELP_SECTIONS["help_multiplayer"]

        for command in ("/blackjack", "/highlow", "/mines", "/memorymatch"):
            self.assertIn(command, solo)
        for command in ("/ttt", "/c4", "/taprace", "/wordbomb", "/rps", "/diceduel", "/war"):
            self.assertIn(command, multiplayer)
            self.assertNotIn(command, solo)

    def test_economy_help_mentions_support_command(self):
        self.assertIn("/support", start.HELP_SECTIONS["help_economy"])

    def test_start_does_not_retry_blocked_user_after_forbidden(self):
        previous_start_img = start.cfg.START_IMG_URL
        start.cfg.START_IMG_URL = "https://example.com/start.jpg"

        class BlockedMessage:
            async def reply_photo(self, **kwargs):
                raise Forbidden("bot was blocked by the user")

            async def reply_text(self, *args, **kwargs):
                raise AssertionError("text fallback should not run after Forbidden")

        class Bot:
            async def send_message(self, *args, **kwargs):
                raise AssertionError("final send fallback should not run after Forbidden")

        update = types.SimpleNamespace(
            callback_query=None,
            effective_message=BlockedMessage(),
            effective_chat=types.SimpleNamespace(id=123),
            effective_user=types.SimpleNamespace(first_name="Nagi"),
        )
        context = types.SimpleNamespace(bot=Bot())

        try:
            result = asyncio.run(start.send_or_edit_start(update, context, "hello", None))
        finally:
            start.cfg.START_IMG_URL = previous_start_img

        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
