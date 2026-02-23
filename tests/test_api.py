from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from chat_history.server import create_app


FIXTURES_DIR = Path(__file__).parent / "fixtures"


class ApiSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_env = {key: os.environ.get(key) for key in self._env_keys()}
        self._tmp_dir = tempfile.TemporaryDirectory()
        os.environ["CHAT_HISTORY_DATA_DIR"] = self._tmp_dir.name
        os.environ["CHAT_HISTORY_CHATGPT_PATH"] = str(FIXTURES_DIR / "chatgpt_2026_sample.json")
        os.environ["CHAT_HISTORY_CLAUDE_PATH"] = str(FIXTURES_DIR / "claude_2026_sample.json")
        os.environ["CHAT_HISTORY_GEMINI_PATH"] = str(FIXTURES_DIR / "gemini_2026_sample.json")
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
            "CHAT_HISTORY_GEMINI_PATH",
            "CHAT_HISTORY_OPENAI_ENABLED",
            "OPENAI_API_KEY",
        ]

    def test_core_endpoints(self) -> None:
        conversations_response = self.client.get("/api/conversations")
        self.assertEqual(conversations_response.status_code, 200)
        conversations = conversations_response.json()
        self.assertGreater(len(conversations), 0)
        providers = {conversation["provider"] for conversation in conversations}
        self.assertEqual(providers, {"chatgpt", "claude", "gemini"})

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
        self.assertIn("summary", stats)
        self.assertIn("by_provider", stats)
        self.assertIn("Conversations", stats["summary"])
        self.assertIn("Providers", stats["summary"])
        self.assertNotIn("Shortest conversation", stats["summary"])
        self.assertNotIn("Longest conversation", stats["summary"])
        self.assertNotIn("Average chat length", stats["summary"])
        self.assertEqual(set(stats["by_provider"].keys()), {"chatgpt", "claude", "gemini"})

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
        self.assertIn("internal_url", data[0])
        self.assertTrue(data[0]["internal_url"].startswith("/?provider="))

    def test_activity_endpoint_returns_daily_counts(self) -> None:
        response = self.client.get("/api/activity")
        self.assertEqual(response.status_code, 200)
        activity = response.json()
        self.assertTrue(isinstance(activity, dict))
        self.assertIn("days", activity)
        self.assertIn("providers", activity)
        self.assertIn("provider_totals", activity)
        self.assertGreater(len(activity["days"]), 0)
        first_key = next(iter(activity["days"].keys()))
        self.assertRegex(first_key, r"^\d{4}-\d{2}-\d{2}$")

    def test_activity_day_endpoint_filters_by_provider(self) -> None:
        activity_response = self.client.get("/api/activity")
        self.assertEqual(activity_response.status_code, 200)
        activity = activity_response.json()

        claude_day = next(
            day
            for day, entry in activity["days"].items()
            if entry.get("providers", {}).get("claude", 0) > 0
        )

        day_response = self.client.get(f"/api/activity/day?date={claude_day}&provider=claude")
        self.assertEqual(day_response.status_code, 200)
        payload = day_response.json()
        self.assertEqual(payload["date"], claude_day)
        self.assertEqual(payload["provider"], "claude")
        self.assertGreater(payload["total_messages"], 0)
        self.assertGreater(len(payload["conversations"]), 0)
        for conversation in payload["conversations"]:
            self.assertEqual(conversation["provider"], "claude")
            self.assertIn("id", conversation)
            self.assertGreater(conversation["message_count"], 0)

    def test_asset_endpoint_serves_resolved_images(self) -> None:
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\nIDATx\x9cc`\x00\x00\x00\x02\x00\x01"
            b"\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        wav_bytes = (
            b"RIFF$\x00\x00\x00WAVEfmt "
            b"\x10\x00\x00\x00\x01\x00\x01\x00@\x1f\x00\x00\x80>\x00\x00"
            b"\x02\x00\x10\x00data\x00\x00\x00\x00"
        )
        export_payload = [
            {
                "id": "chatgpt-image-conv",
                "title": "Image conversation",
                "create_time": 1736000000.0,
                "update_time": 1736000001.0,
                "current_node": "assistant-node",
                "mapping": {
                    "root": {
                        "id": "root",
                        "parent": None,
                        "children": ["assistant-node"],
                        "message": None,
                    },
                    "assistant-node": {
                        "id": "assistant-node",
                        "parent": "root",
                        "children": [],
                        "message": {
                            "id": "assistant-msg",
                            "author": {"role": "assistant"},
                            "create_time": 1736000001.0,
                            "update_time": 1736000001.0,
                            "content": {
                                "content_type": "multimodal_text",
                                "parts": [
                                    {
                                        "content_type": "image_asset_pointer",
                                        "asset_pointer": "file-service://file-image-test",
                                        "width": 640,
                                        "height": 480,
                                    },
                                    {
                                        "content_type": "image_asset_pointer",
                                        "asset_pointer": "file-service://missing-image-test",
                                    },
                                    {
                                        "content_type": "audio_asset_pointer",
                                        "asset_pointer": "file-service://file-audio-test",
                                        "format": "wav",
                                        "size_bytes": 40,
                                    },
                                ],
                            },
                            "metadata": {},
                        },
                    },
                },
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            export_path = Path(tmpdir) / "conversations.json"
            image_path = Path(tmpdir) / "file-image-test-preview.png"
            audio_path = Path(tmpdir) / "file-audio-test-recording.wav"
            export_path.write_text(json.dumps(export_payload), encoding="utf-8")
            image_path.write_bytes(png_bytes)
            audio_path.write_bytes(wav_bytes)

            old_chatgpt_path = os.environ.get("CHAT_HISTORY_CHATGPT_PATH")
            old_claude_path = os.environ.get("CHAT_HISTORY_CLAUDE_PATH")
            try:
                os.environ["CHAT_HISTORY_CHATGPT_PATH"] = str(export_path)
                os.environ.pop("CHAT_HISTORY_CLAUDE_PATH", None)
                app = create_app()
                with TestClient(app) as client:
                    response = client.get("/api/conversations/chatgpt/chatgpt-image-conv/messages")
                    self.assertEqual(response.status_code, 200)
                    payload = response.json()

                    non_internal = [m for m in payload["messages"] if m.get("role") != "internal"]
                    self.assertGreater(len(non_internal), 0)
                    blocks = non_internal[0]["blocks"]
                    image_blocks = [block for block in blocks if block.get("type") == "image_asset_pointer"]
                    audio_blocks = [block for block in blocks if block.get("type") == "audio_asset_pointer"]
                    self.assertEqual(len(image_blocks), 2)
                    self.assertEqual(len(audio_blocks), 1)

                    resolved_asset = image_blocks[0]["data"]["asset"]
                    self.assertEqual(resolved_asset["kind"], "image")
                    self.assertTrue(resolved_asset["is_resolved"])
                    self.assertTrue(resolved_asset["asset_url"])
                    self.assertEqual(resolved_asset["width"], 640)
                    self.assertEqual(resolved_asset["height"], 480)

                    unresolved_asset = image_blocks[1]["data"]["asset"]
                    self.assertFalse(unresolved_asset["is_resolved"])
                    self.assertIsNone(unresolved_asset["asset_url"])

                    image_response = client.get(resolved_asset["asset_url"])
                    self.assertEqual(image_response.status_code, 200)
                    self.assertIn("image/png", image_response.headers.get("content-type", ""))
                    self.assertEqual(
                        image_response.headers.get("cache-control"),
                        "private, max-age=86400",
                    )

                    resolved_audio = audio_blocks[0]["data"]["asset"]
                    self.assertEqual(resolved_audio["kind"], "audio")
                    self.assertTrue(resolved_audio["is_resolved"])
                    self.assertTrue(resolved_audio["asset_url"])
                    audio_response = client.get(resolved_audio["asset_url"])
                    self.assertEqual(audio_response.status_code, 200)
                    self.assertIn("audio", audio_response.headers.get("content-type", ""))
                    self.assertEqual(
                        audio_response.headers.get("cache-control"),
                        "private, max-age=86400",
                    )

                    missing_response = client.get("/api/assets/chatgpt/not-found")
                    self.assertEqual(missing_response.status_code, 404)
            finally:
                if old_chatgpt_path is None:
                    os.environ.pop("CHAT_HISTORY_CHATGPT_PATH", None)
                else:
                    os.environ["CHAT_HISTORY_CHATGPT_PATH"] = old_chatgpt_path
                if old_claude_path is None:
                    os.environ.pop("CHAT_HISTORY_CLAUDE_PATH", None)
                else:
                    os.environ["CHAT_HISTORY_CLAUDE_PATH"] = old_claude_path


if __name__ == "__main__":
    unittest.main()
