from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from server import create_app


FIXTURES_DIR = Path(__file__).parent / "fixtures"


class ApiSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_env = {key: os.environ.get(key) for key in self._env_keys()}
        self._tmp_dir = tempfile.TemporaryDirectory()
        os.environ["CHAT_HISTORY_DATA_DIR"] = self._tmp_dir.name
        os.environ["CHAT_HISTORY_CHATGPT_PATH"] = str(FIXTURES_DIR / "chatgpt_2026_sample.json")
        os.environ["CHAT_HISTORY_CLAUDE_PATH"] = str(FIXTURES_DIR / "claude_2026_sample.json")
        os.environ["CHAT_HISTORY_OPENAI_ENABLED"] = "false"
        os.environ.pop("OPENAI_API_KEY", None)

        self._app = create_app()
        self._client_cm = TestClient(self._app)
        self.client = self._client_cm.__enter__()

    def tearDown(self) -> None:
        self._client_cm.__exit__(None, None, None)
        self._tmp_dir.cleanup()
        for key, value in self._old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    @staticmethod
    def _env_keys() -> list[str]:
        return [
            "CHAT_HISTORY_DATA_DIR",
            "CHAT_HISTORY_CHATGPT_PATH",
            "CHAT_HISTORY_CLAUDE_PATH",
            "CHAT_HISTORY_OPENAI_ENABLED",
            "OPENAI_API_KEY",
        ]

    def test_core_endpoints(self) -> None:
        conversations_response = self.client.get("/api/conversations")
        self.assertEqual(conversations_response.status_code, 200)
        conversations = conversations_response.json()
        self.assertGreater(len(conversations), 0)
        providers = {conversation["provider"] for conversation in conversations}
        self.assertEqual(providers, {"chatgpt", "claude"})

        first = conversations[0]
        messages_response = self.client.get(
            f"/api/conversations/{first['provider']}/{first['id']}/messages"
        )
        self.assertEqual(messages_response.status_code, 200)
        payload = messages_response.json()
        self.assertIn("messages", payload)
        non_internal = [m for m in payload["messages"] if m.get("role") != "internal"]
        self.assertGreater(len(non_internal), 0)
        self.assertIn("blocks", non_internal[0])

        statistics_response = self.client.get("/api/statistics")
        self.assertEqual(statistics_response.status_code, 200)
        stats = statistics_response.json()
        self.assertIn("Conversations", stats)
        self.assertIn("Providers", stats)

        token_response = self.client.get("/api/ai-cost")
        self.assertEqual(token_response.status_code, 200)
        token_stats = token_response.json()
        self.assertTrue(isinstance(token_stats, list))

    def test_search_strict_mode_returns_results(self) -> None:
        response = self.client.get('/api/search?query=%22from%20metadata%22')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(len(data), 0)
        providers = {item["provider"] for item in data}
        self.assertIn("chatgpt", providers)

    def test_activity_endpoint_returns_daily_counts(self) -> None:
        response = self.client.get("/api/activity")
        self.assertEqual(response.status_code, 200)
        activity = response.json()
        self.assertTrue(isinstance(activity, dict))
        self.assertGreater(len(activity), 0)
        first_key = next(iter(activity.keys()))
        self.assertRegex(first_key, r"^\d{4}-\d{2}-\d{2}$")


if __name__ == "__main__":
    unittest.main()
