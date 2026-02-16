from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from chat_history.cli import (
    _is_claude_default_export_zip_name,
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


if __name__ == "__main__":
    unittest.main()
