from __future__ import annotations

import os
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from config import load_settings
from exporter import export_conversation
from manage import run_export
from services import ChatHistoryService


FIXTURES_DIR = Path(__file__).parent / "fixtures"


class ExporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_env = {key: os.environ.get(key) for key in self._env_keys()}
        self._tmp_dir = tempfile.TemporaryDirectory()
        os.environ["CHAT_HISTORY_DATA_DIR"] = self._tmp_dir.name
        os.environ["CHAT_HISTORY_CHATGPT_PATH"] = str(FIXTURES_DIR / "chatgpt_2026_sample.json")
        os.environ["CHAT_HISTORY_CLAUDE_PATH"] = str(FIXTURES_DIR / "claude_2026_sample.json")
        os.environ["CHAT_HISTORY_OPENAI_ENABLED"] = "false"
        os.environ.pop("OPENAI_API_KEY", None)

    def tearDown(self) -> None:
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

    def _build_service(self) -> ChatHistoryService:
        settings = load_settings()
        service = ChatHistoryService(settings)
        service.load(build_embeddings=False)
        return service

    def test_export_conversation_writes_markdown_file(self) -> None:
        service = self._build_service()
        conversation = service.conversations[0]
        output_dir = Path(self._tmp_dir.name) / "export-basic"
        output_path = export_conversation(
            conversation=conversation,
            output_dir=output_dir,
            output_format="markdown",
            include_system=True,
            include_tool=True,
            include_thinking=True,
            include_attachments=True,
        )

        self.assertTrue(output_path.exists())
        content = output_path.read_text(encoding="utf-8")
        self.assertIn(f"Provider: `{conversation.provider}`", content)
        self.assertIn(f"Conversation ID: `{conversation.id}`", content)

    def test_run_export_clean_removes_provider_specific_old_files(self) -> None:
        service = self._build_service()
        output_dir = Path(self._tmp_dir.name) / "export-clean"
        output_dir.mkdir(parents=True, exist_ok=True)
        stale_claude = output_dir / "claude--stale-entry--old.md"
        stale_chatgpt = output_dir / "chatgpt--stale-entry--old.md"
        stale_claude.write_text("stale claude", encoding="utf-8")
        stale_chatgpt.write_text("stale chatgpt", encoding="utf-8")

        args = Namespace(
            provider="claude",
            format="markdown",
            out=output_dir,
            clean=True,
            exclude_system=False,
            exclude_tool=False,
            exclude_thinking=False,
            exclude_attachments=False,
        )

        exit_code = run_export(service, args)
        self.assertEqual(exit_code, 0)
        self.assertFalse(stale_claude.exists())
        self.assertTrue(stale_chatgpt.exists())
        exported_claude = list(output_dir.glob("claude--*.md"))
        self.assertGreater(len(exported_claude), 0)


if __name__ == "__main__":
    unittest.main()
