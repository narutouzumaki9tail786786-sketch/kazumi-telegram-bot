import importlib
import sys
import types
import unittest
from unittest.mock import patch

from telegram.error import RetryAfter, TimedOut


class _Collection:
    def find(self, *args, **kwargs):
        return []


fake_database = types.ModuleType("kazumi.database")
fake_database.users_collection = _Collection()
fake_database.sudoers_collection = _Collection()
fake_database.groups_collection = _Collection()
sys.modules["kazumi.database"] = fake_database

utils = importlib.import_module("kazumi.utils")


class TelegramRetryWrapperTests(unittest.IsolatedAsyncioTestCase):
    def test_stale_reply_metadata_is_removed_for_fallback(self):
        fallback = utils._without_reply_target(
            {
                "reply_to_message_id": 123,
                "reply_parameters": object(),
                "parse_mode": "HTML",
            },
            supports_do_quote=True,
        )

        self.assertNotIn("reply_to_message_id", fallback)
        self.assertNotIn("reply_parameters", fallback)
        self.assertEqual(fallback["do_quote"], False)
        self.assertEqual(fallback["parse_mode"], "HTML")

    async def test_retries_timeout_once_before_success(self):
        calls = {"count": 0}

        async def flaky():
            calls["count"] += 1
            if calls["count"] == 1:
                raise TimedOut("slow network")
            return "ok"

        with patch("kazumi.utils.asyncio.sleep", autospec=True) as mocked_sleep:
            result = await utils._call_with_telegram_retries("send_message", flaky)

        self.assertEqual(result, "ok")
        self.assertEqual(calls["count"], 2)
        mocked_sleep.assert_awaited_once()

    async def test_edit_methods_get_extra_retry_budget(self):
        calls = {"count": 0}

        async def flaky():
            calls["count"] += 1
            if calls["count"] < 3:
                raise TimedOut("slow edit")
            return "edited"

        with patch("kazumi.utils.asyncio.sleep", autospec=True):
            result = await utils._call_with_telegram_retries("edit_message_text", flaky)

        self.assertEqual(result, "edited")
        self.assertEqual(calls["count"], 3)

    async def test_short_retry_after_is_retried(self):
        calls = {"count": 0}

        async def flaky():
            calls["count"] += 1
            if calls["count"] == 1:
                raise RetryAfter(2)
            return "done"

        with patch("kazumi.utils.asyncio.sleep", autospec=True) as mocked_sleep:
            result = await utils._call_with_telegram_retries("send_message", flaky)

        self.assertEqual(result, "done")
        self.assertEqual(calls["count"], 2)
        mocked_sleep.assert_awaited_once_with(2.0)


if __name__ == "__main__":
    unittest.main()
