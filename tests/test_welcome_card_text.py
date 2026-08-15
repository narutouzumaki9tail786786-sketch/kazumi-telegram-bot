import importlib.util
import sys
import types
import unittest
from pathlib import Path


fake_database = types.ModuleType("kazumi.database")
fake_database.groups_collection = object()

fake_utils = types.ModuleType("kazumi.utils")
fake_utils.get_mention = lambda user: "user"
fake_utils.ensure_user_exists = lambda user: {}

fake_config = types.ModuleType("kazumi.config")
fake_config.WELCOME_IMG_URL = ""
fake_config.BOT_NAME = "Kazumi"
fake_config.START_IMG_URL = ""
fake_config.SUPPORT_GROUP = "https://t.me/support"
fake_config.WELCOME_CARD_ENABLED = True

_stubs = {
    "kazumi.database": fake_database,
    "kazumi.utils": fake_utils,
    "kazumi.config": fake_config,
}
_saved = {name: sys.modules.get(name) for name in _stubs}
sys.modules.update(_stubs)
try:
    module_path = Path(__file__).parents[1] / "kazumi" / "plugins" / "welcome.py"
    spec = importlib.util.spec_from_file_location("welcome_card_subject", module_path)
    welcome = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(welcome)
finally:
    for name, module in _saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


class WelcomeCardTextTests(unittest.TestCase):
    def test_fancy_unicode_name_becomes_readable_text(self):
        text = welcome._card_safe_text("—͟͞Ɗᴇꜱᴛʀᴏʏᴇʀ~𝐗️♝", 18)
        self.assertIn("Destroyer", text)
        self.assertIn("X", text)
        self.assertNotIn("\ufe0f", text)

    def test_symbols_only_name_uses_fallback(self):
        self.assertEqual(welcome._card_safe_text("༺༒༻", 18, fallback="Nagi"), "Nagi")


if __name__ == "__main__":
    unittest.main()
