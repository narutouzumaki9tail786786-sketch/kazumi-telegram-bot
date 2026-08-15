import importlib
import sys
import types
import unittest


class _Collection:
    def find(self, *args, **kwargs):
        return []


fake_database = types.ModuleType("kazumi.database")
fake_database.users_collection = _Collection()
fake_database.sudoers_collection = _Collection()
fake_database.groups_collection = _Collection()
sys.modules["kazumi.database"] = fake_database

utils = importlib.import_module("kazumi.utils")


class CustomEmojiButtonTests(unittest.TestCase):
    def test_emoji_only_button_hides_unicode_fallback(self):
        diamond = "\U0001f48e"
        emoji_id, _ = utils.get_icon_id(diamond)

        text, selected_id = utils._customize_button_text(diamond)

        self.assertEqual(selected_id, emoji_id)
        self.assertEqual(text, "\u200b")

    def test_button_wrapper_hides_unicode_fallback(self):
        diamond = "\U0001f48e"
        emoji_id, _ = utils.get_icon_id(diamond)

        button = utils.Button(diamond, callback_data="test")

        self.assertEqual(button.icon_custom_emoji_id, emoji_id)
        self.assertEqual(button.text, "\u200b")


if __name__ == "__main__":
    unittest.main()
