import importlib.util
import io
import sys
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


fake_config = types.ModuleType("kazumi.config")
fake_config.MISTRAL_API_KEY = "mistral-key"
fake_config.GROQ_API_KEY = "groq-key"
fake_config.GROQ_API_KEYS = []
fake_config.CODESTRAL_API_KEY = ""
fake_config.ENABLE_GROK_PROXY = False
fake_config.GROK_PROXY_URL = ""
fake_config.GROK_PROXY_MODEL = ""
fake_config.GROK_PROXY_API_KEY = ""
fake_config.BOT_NAME = "Kazumi"
fake_config.OWNER_LINK = "https://t.me/owner"


class DummyCollection:
    def find_one(self, *args, **kwargs):
        return None

    def update_one(self, *args, **kwargs):
        return None


fake_database = types.ModuleType("kazumi.database")
fake_database.chatbot_collection = DummyCollection()

fake_memory = types.ModuleType("kazumi.plugins.memory")
fake_memory.answer_memory_question = lambda *args, **kwargs: None
fake_memory.memory_context = lambda *args, **kwargs: ""
fake_memory.maybe_react_to_topic = lambda *args, **kwargs: None
fake_memory.observe_user_message = lambda *args, **kwargs: None

fake_utils = types.ModuleType("kazumi.utils")
fake_utils.stylize_text = lambda text: text

_stubs = {
    "kazumi.config": fake_config,
    "kazumi.database": fake_database,
    "kazumi.plugins.memory": fake_memory,
    "kazumi.utils": fake_utils,
}
_saved = {name: sys.modules.get(name) for name in _stubs}
sys.modules.update(_stubs)
try:
    module_path = Path(__file__).parents[1] / "kazumi" / "plugins" / "chatbot.py"
    spec = importlib.util.spec_from_file_location("chatbot_logging_subject", module_path)
    chatbot = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(chatbot)
finally:
    for name, module in _saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


class ChatbotProviderLoggingTests(unittest.TestCase):
    def test_provider_success_log_is_rate_limited(self):
        stream = io.StringIO()
        chatbot._PROVIDER_LOG_LAST.clear()

        with patch.object(chatbot.time, "time", side_effect=[100.0, 101.0, 170.0]):
            with redirect_stdout(stream):
                chatbot._log_provider_event("mistral", "success", "MISTRAL ok")
                chatbot._log_provider_event("mistral", "success", "MISTRAL ok")
                chatbot._log_provider_event("mistral", "success", "MISTRAL ok")

        self.assertEqual(stream.getvalue().count("MISTRAL ok"), 2)


if __name__ == "__main__":
    unittest.main()
