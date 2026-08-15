import importlib.util
import sys
import types
import unittest
from pathlib import Path


class _UsersCollection:
    def __init__(self):
        self.last_filter = None
        self.last_update = None

    def update_one(self, filter_doc, update_doc):
        self.last_filter = filter_doc
        self.last_update = update_doc


fake_database = types.ModuleType("kazumi.database")
fake_database.users_collection = _UsersCollection()

fake_utils = types.ModuleType("kazumi.utils")
fake_utils.add_xp = lambda *args, **kwargs: None
fake_utils.ensure_user_exists = lambda user: user
fake_utils.format_money = lambda amount: f"${amount:,}"
fake_utils.get_mention = lambda user: "user"
fake_utils.stylize_text = lambda text: text

fake_config = types.ModuleType("kazumi.config")
fake_config.XP_PER_GAME_WIN = 25

_stubs = {
    "kazumi.database": fake_database,
    "kazumi.utils": fake_utils,
    "kazumi.config": fake_config,
}
_saved = {name: sys.modules.get(name) for name in _stubs}
sys.modules.update(_stubs)
try:
    module_path = Path(__file__).parents[1] / "kazumi" / "plugins" / "pets.py"
    spec = importlib.util.spec_from_file_location("pets_subject", module_path)
    pets = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pets)
finally:
    for name, module in _saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


class MultiPetInventoryTests(unittest.TestCase):
    def test_load_pet_state_migrates_legacy_single_pet(self):
        user = {
            "pet": {
                "id": "wolf",
                "name": "🐺 ᴡᴏʟғ",
                "power": 20,
                "hp": 90,
                "hunger": 80,
                "level": 2,
                "xp": 15,
            }
        }

        owned, active_pet, active_pet_id = pets._load_pet_state(user)

        self.assertEqual(len(owned), 1)
        self.assertEqual(active_pet_id, "wolf")
        self.assertEqual(active_pet["id"], "wolf")
        self.assertEqual(active_pet["level"], 2)

    def test_load_pet_state_prefers_explicit_active_pet(self):
        user = {
            "pets": [
                {"id": "dog", "name": "🐕 ᴅᴏɢ", "power": 10},
                {"id": "dragon", "name": "🐉 ᴅʀᴀɢᴏɴ", "power": 80},
            ],
            "active_pet_id": "dragon",
        }

        owned, active_pet, active_pet_id = pets._load_pet_state(user)

        self.assertEqual(len(owned), 2)
        self.assertEqual(active_pet_id, "dragon")
        self.assertEqual(active_pet["name"], "🐉 ᴅʀᴀɢᴏɴ")

    def test_save_pet_state_updates_shadow_pet_field(self):
        owned = [
            pets._build_pet_record("dog", pets.PETS["dog"]),
            pets._build_pet_record("tiger", pets.PETS["tiger"]),
        ]

        active_pet = pets._save_pet_state(55, owned, "tiger")

        self.assertEqual(active_pet["id"], "tiger")
        self.assertEqual(fake_database.users_collection.last_filter, {"user_id": 55})
        saved = fake_database.users_collection.last_update["$set"]
        self.assertEqual(saved["active_pet_id"], "tiger")
        self.assertEqual(saved["pet"]["id"], "tiger")
        self.assertEqual(len(saved["pets"]), 2)


if __name__ == "__main__":
    unittest.main()
