from __future__ import annotations

import io
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from chat_history.cli import (
    _detect_provider,
    _is_claude_default_export_zip_name,
    _run_install_command,
    _scan_local_candidates,
    build_parser,
)


class CliCandidateTests(unittest.TestCase):
    def test_claude_default_zip_name_detection(self) -> None:
        self.assertTrue(_is_claude_default_export_zip_name("data-2026-02-16-18-17-35-batch-0000.zip"))
        self.assertTrue(_is_claude_default_export_zip_name("DATA-2026-02-16-18-17-35-BATCH-0001.ZIP"))

        self.assertFalse(_is_claude_default_export_zip_name("chatgpt-export.zip"))
        self.assertFalse(_is_claude_default_export_zip_name("data-2026-02-16-18-17-35.zip"))
        self.assertFalse(_is_claude_default_export_zip_name("data-2026-02-16-18-17-35-batch-0000.json"))

    def test_scan_local_candidates_includes_claude_default_zip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            claude_zip = tmp_path / "data-2026-02-16-18-17-35-batch-0000.zip"
            claude_zip.write_bytes(b"")

            candidates = _scan_local_candidates(tmp_path, "claude")

            self.assertIn(claude_zip, candidates)

    def test_scan_local_candidates_does_not_apply_claude_pattern_to_chatgpt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            (tmp_path / "data-2026-02-16-18-17-35-batch-0000.zip").write_bytes(b"")

            candidates = _scan_local_candidates(tmp_path, "chatgpt")

            self.assertEqual(candidates, [])

    def test_parser_supports_version_flag(self) -> None:
        parser = build_parser()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as context:
                parser.parse_args(["--version"])
        self.assertEqual(context.exception.code, 0)

    def test_parser_supports_install_command(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["install"])
        self.assertEqual(args.command, "install")
        self.assertTrue(callable(args.func))

    @patch("chat_history.cli.subprocess.run")
    def test_install_command_invokes_uvx_reinstall(self, run_mock) -> None:
        run_mock.return_value = subprocess.CompletedProcess(
            args=["uvx", "--reinstall", "chat-history", "--version"],
            returncode=0,
        )
        exit_code = _run_install_command(build_parser().parse_args(["install"]))
        self.assertEqual(exit_code, 0)
        run_mock.assert_called_once_with(
            ["uvx", "--reinstall", "chat-history", "--version"],
            check=False,
        )


class CliDetectProviderTests(unittest.TestCase):
    def test_detect_chatgpt(self) -> None:
        item = {"mapping": {}, "current_node": "abc"}
        self.assertEqual(_detect_provider(item), "chatgpt")

    def test_detect_claude(self) -> None:
        item = {"uuid": "abc", "chat_messages": []}
        self.assertEqual(_detect_provider(item), "claude")

    def test_detect_gemini(self) -> None:
        item = {"chunkedPrompt": {"chunks": [{"text": "Hello", "role": "user"}]}}
        self.assertEqual(_detect_provider(item), "gemini")

    def test_detect_unknown(self) -> None:
        item = {"foo": "bar"}
        self.assertIsNone(_detect_provider(item))


if __name__ == "__main__":
    unittest.main()
