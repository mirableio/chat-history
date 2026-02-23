from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from chat_history.config import load_settings


ENV_KEYS = [
    "CHAT_HISTORY_DATA_DIR",
    "CHAT_HISTORY_CHATGPT_PATH",
    "CHAT_HISTORY_CLAUDE_PATH",
    "CHAT_HISTORY_GEMINI_PATH",
    "CHAT_HISTORY_SETTINGS_DB_PATH",
    "CHAT_HISTORY_OPENAI_ENABLED",
    "OPENAI_API_KEY",
    "OPENAI_ORGANIZATION",
    "OPENAI_EMBEDDING_MODEL",
]


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_cwd = Path.cwd()
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._env_backup = {key: os.environ.get(key) for key in ENV_KEYS}
        for key in ENV_KEYS:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        os.chdir(self._old_cwd)
        self._tmp_dir.cleanup()
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_load_settings_uses_cwd_data_dotenv_file(self) -> None:
        tmp_path = Path(self._tmp_dir.name)
        (tmp_path / "data").mkdir(parents=True, exist_ok=True)
        (tmp_path / "data" / ".env").write_text("CHAT_HISTORY_DATA_DIR=local-data\n", encoding="utf-8")

        os.chdir(tmp_path)
        settings = load_settings()

        self.assertEqual(settings.data_dir, Path("local-data"))
        self.assertEqual(settings.settings_db_path, Path("local-data") / "settings.db")

    def test_load_settings_does_not_read_repo_dotenv_when_cwd_has_no_data_dotenv(self) -> None:
        tmp_path = Path(self._tmp_dir.name)
        os.chdir(tmp_path)

        settings = load_settings()

        self.assertEqual(settings.data_dir, Path("data"))
        self.assertIsNone(settings.chatgpt_path)
        self.assertIsNone(settings.claude_path)
        self.assertIsNone(settings.gemini_path)


if __name__ == "__main__":
    unittest.main()
