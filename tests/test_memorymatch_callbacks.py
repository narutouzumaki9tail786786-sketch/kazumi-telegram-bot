import importlib.util
import sys
import types
import unittest
from asyncio import Event
from pathlib import Path
from unittest.mock import AsyncMock, patch


async def _add_xp(*args, **kwargs):
    return None


fake_utils = types.ModuleType("kazumi.utils")
fake_utils.add_xp = _add_xp
fake_utils.ensure_user_exists = lambda user: {"user_id": user.id, "balance": 1000}
fake_utils.format_money = lambda amount: f"${amount:,}"
fake_utils.get_mention = lambda user: user.full_name
fake_utils.stylize_text = lambda text: text

fake_ledger = types.ModuleType("kazumi.ledger")
fake_ledger.adjust_user_balance = lambda *args, **kwargs: True

fake_missions = types.ModuleType("kazumi.missions")
fake_missions.track_mission = lambda *args, **kwargs: None

fake_timeouts = types.ModuleType("kazumi.game_timeouts")
fake_timeouts.refund_locked_bet = lambda *args, **kwargs: {"refund": 0, "fee": 0}

_stubs = {
    "kazumi.utils": fake_utils,
    "kazumi.ledger": fake_ledger,
    "kazumi.missions": fake_missions,
    "kazumi.game_timeouts": fake_timeouts,
}
_saved = {name: sys.modules.get(name) for name in _stubs}
sys.modules.update(_stubs)
try:
    module_path = Path(__file__).parents[1] / "kazumi" / "plugins" / "arcade_games.py"
    spec = importlib.util.spec_from_file_location("memorymatch_callback_subject", module_path)
    arcade_games = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(arcade_games)
finally:
    for name, module in _saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


class _Message:
    def __init__(self, message_id, edit_error=None):
        self.message_id = message_id
        self.edits = []
        self.edit_error = edit_error

    async def edit_text(self, *args, **kwargs):
        self.edits.append((args, kwargs))
        if self.edit_error:
            raise self.edit_error


class _Query:
    def __init__(self, data, user_id, message_id, edit_error=None):
        self.data = data
        self.from_user = types.SimpleNamespace(id=user_id)
        self.message = _Message(message_id, edit_error=edit_error)
        self.answers = []

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))


class _Application:
    def __init__(self):
        self.tasks = []

    def create_task(self, coroutine):
        task = arcade_games.asyncio.create_task(coroutine)
        self.tasks.append(task)
        return task


class MemoryMatchCallbackTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        arcade_games.active_memory.clear()

    async def test_rapid_second_tap_from_same_message_is_accepted(self):
        game = {
            "uid": 42,
            "bet": 100,
            "board": ["A", "A"] + list("BCDEFGHIJKLMNO"),
            "matched": set(),
            "opened": [0],
            "mistakes": 0,
            "locked": False,
            "revision": 1,
            "token": "memory:test",
            "chat_id": -100,
            "message_id": 77,
        }
        arcade_games.active_memory[42] = game
        query = _Query("mm_open|42|0|1", user_id=42, message_id=77)
        update = types.SimpleNamespace(callback_query=query)

        await arcade_games.memory_callback(update, types.SimpleNamespace())

        self.assertEqual(game["matched"], {0, 1})
        self.assertNotIn("Old button. Use the latest board.", [answer[0] for answer in query.answers])

    async def test_button_from_previous_game_message_is_rejected(self):
        game = {
            "uid": 42,
            "bet": 100,
            "board": list("AABBCCDDEEFFGGHH"),
            "matched": set(),
            "opened": [],
            "mistakes": 0,
            "locked": False,
            "revision": 0,
            "token": "memory:new",
            "chat_id": -100,
            "message_id": 77,
        }
        arcade_games.active_memory[42] = game
        query = _Query("mm_open|42|0|1", user_id=42, message_id=76)
        update = types.SimpleNamespace(callback_query=query)

        await arcade_games.memory_callback(update, types.SimpleNamespace())

        self.assertEqual(game["opened"], [])
        self.assertEqual(query.answers[0][0], "Game expired.")

    async def test_edit_failure_does_not_leave_mismatch_locked(self):
        game = {
            "uid": 42,
            "bet": 100,
            "board": list("ABCDEFGHIJKLMNOP"),
            "matched": set(),
            "opened": [0],
            "mistakes": 0,
            "locked": False,
            "revision": 1,
            "token": "memory:flood",
            "chat_id": -100,
            "message_id": 77,
        }
        arcade_games.active_memory[42] = game
        query = _Query(
            "mm_open|42|1|1",
            user_id=42,
            message_id=77,
            edit_error=arcade_games.TelegramError("flood control"),
        )
        application = _Application()
        context = types.SimpleNamespace(
            application=application,
            bot=types.SimpleNamespace(edit_message_text=AsyncMock()),
        )
        update = types.SimpleNamespace(callback_query=query)

        with patch.object(arcade_games.asyncio, "sleep", new=AsyncMock()):
            await arcade_games.memory_callback(update, context)
            if application.tasks:
                await arcade_games.asyncio.gather(*application.tasks)

        self.assertFalse(game["locked"])
        self.assertEqual(game["opened"], [])

    async def test_third_tap_is_rejected_while_second_card_is_resolving(self):
        game = {
            "uid": 42,
            "bet": 100,
            "board": ["A", "B", "C"] + list("DEFGHIJKLMNOP"),
            "matched": set(),
            "opened": [0],
            "mistakes": 0,
            "locked": False,
            "revision": 1,
            "token": "memory:race",
            "chat_id": -100,
            "message_id": 77,
        }
        arcade_games.active_memory[42] = game
        gate = Event()
        release = Event()

        second_query = _Query("mm_open|42|1|1", user_id=42, message_id=77)

        async def delayed_answer(text=None, **kwargs):
            second_query.answers.append((text, kwargs))
            gate.set()
            await release.wait()

        second_query.answer = delayed_answer
        update_second = types.SimpleNamespace(callback_query=second_query)

        context = types.SimpleNamespace(
            application=_Application(),
            bot=types.SimpleNamespace(edit_message_text=AsyncMock()),
        )
        second_task = arcade_games.asyncio.create_task(
            arcade_games.memory_callback(update_second, context)
        )

        await gate.wait()

        third_query = _Query("mm_open|42|1|2", user_id=42, message_id=77)
        await arcade_games.memory_callback(
            types.SimpleNamespace(callback_query=third_query),
            context,
        )

        self.assertEqual(game["opened"], [0, 1])
        self.assertTrue(game["locked"])
        self.assertEqual(third_query.answers[0][0], "Wait for the cards to close.")

        release.set()
        await second_task


if __name__ == "__main__":
    unittest.main()
