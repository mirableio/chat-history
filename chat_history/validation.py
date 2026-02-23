"""Validation reporter for parser-level field auditing.

Collects unrecognized keys encountered during parsing so that format
drift (new fields added by a provider) is surfaced at load time rather
than silently ignored.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class ValidationReport:
    """Accumulates unhandled fields / warnings during a single parse run."""

    provider: str
    _conversation_keys: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _chunked_prompt_keys: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _chunk_keys: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _part_keys: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _run_settings_keys: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _skipped_files: list[str] = field(default_factory=list)
    _warnings: list[str] = field(default_factory=list)

    # -- recording helpers ---------------------------------------------------

    def record_conversation_key(self, key: str) -> None:
        self._conversation_keys[key] += 1

    def record_chunked_prompt_key(self, key: str) -> None:
        self._chunked_prompt_keys[key] += 1

    def record_chunk_key(self, key: str) -> None:
        self._chunk_keys[key] += 1

    def record_part_key(self, key: str) -> None:
        self._part_keys[key] += 1

    def record_run_settings_key(self, key: str) -> None:
        self._run_settings_keys[key] += 1

    def record_skipped_file(self, filename: str) -> None:
        self._skipped_files.append(filename)

    def record_warning(self, message: str) -> None:
        self._warnings.append(message)

    # -- bulk helpers --------------------------------------------------------

    def check_keys(
        self,
        actual: dict,
        known: set[str],
        recorder: str,
    ) -> None:
        """Record any keys in *actual* that are not in *known*."""
        record_fn = getattr(self, f"record_{recorder}_key")
        for key in actual:
            if key not in known:
                record_fn(key)

    # -- query / output ------------------------------------------------------

    def has_issues(self) -> bool:
        return bool(
            self._conversation_keys
            or self._chunked_prompt_keys
            or self._chunk_keys
            or self._part_keys
            or self._run_settings_keys
            or self._skipped_files
            or self._warnings
        )

    def log(self) -> None:
        """Print a human-readable summary to stdout (matches service log style)."""
        if not self.has_issues():
            return

        parts: list[str] = []

        for label, mapping in [
            ("conversation", self._conversation_keys),
            ("chunkedPrompt", self._chunked_prompt_keys),
            ("chunk", self._chunk_keys),
            ("part", self._part_keys),
            ("runSettings", self._run_settings_keys),
        ]:
            if not mapping:
                continue
            top = sorted(mapping.items(), key=lambda item: -item[1])[:8]
            summary = ", ".join(f"{k} ({v}x)" for k, v in top)
            parts.append(f"{label}: {summary}")

        if self._skipped_files:
            parts.append(f"skipped files: {', '.join(self._skipped_files[:5])}")

        for warning in self._warnings[:3]:
            parts.append(f"warning: {warning}")

        if parts:
            print(f"-- {self.provider.capitalize()} validation: {'; '.join(parts)}")
