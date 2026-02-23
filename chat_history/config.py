from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ENV_PATH = Path("data") / ".env"


def _as_bool(raw_value: str | None, default: bool) -> bool:
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _optional_path(raw_value: str | None) -> Path | None:
    if not raw_value:
        return None
    return Path(raw_value).expanduser()


def _normalize_provider_path(path: Path | None, filename: str = "conversations.json") -> Path | None:
    if path is None:
        return None
    if path.exists() and path.is_dir():
        return path / filename
    return path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    chatgpt_path: Path | None
    claude_path: Path | None
    gemini_path: Path | None
    settings_db_path: Path
    openai_api_key: str | None
    openai_organization: str | None
    openai_enabled: bool
    embedding_model: str

    def provider_embeddings_db_path(self, provider: str) -> Path:
        return self.data_dir / provider / "embeddings.db"

    @property
    def export_dir(self) -> Path:
        return self.data_dir / "export"


def load_settings() -> Settings:
    load_dotenv(dotenv_path=Path.cwd() / ENV_PATH, override=False)

    data_dir = Path(os.getenv("CHAT_HISTORY_DATA_DIR", "data")).expanduser()
    default_chatgpt_path = data_dir / "conversations.json"
    chatgpt_path = _normalize_provider_path(_optional_path(os.getenv("CHAT_HISTORY_CHATGPT_PATH")))
    claude_path = _normalize_provider_path(_optional_path(os.getenv("CHAT_HISTORY_CLAUDE_PATH")))
    gemini_path = _normalize_provider_path(_optional_path(os.getenv("CHAT_HISTORY_GEMINI_PATH")))

    if chatgpt_path is None and default_chatgpt_path.exists():
        chatgpt_path = default_chatgpt_path

    settings_db_path = _optional_path(os.getenv("CHAT_HISTORY_SETTINGS_DB_PATH")) or (
        data_dir / "settings.db"
    )

    openai_api_key = os.getenv("OPENAI_API_KEY")
    openai_organization = os.getenv("OPENAI_ORGANIZATION")
    openai_enabled = _as_bool(os.getenv("CHAT_HISTORY_OPENAI_ENABLED"), default=False) and bool(
        openai_api_key
    )
    embedding_model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

    return Settings(
        data_dir=data_dir,
        chatgpt_path=chatgpt_path,
        claude_path=claude_path,
        gemini_path=gemini_path,
        settings_db_path=settings_db_path,
        openai_api_key=openai_api_key,
        openai_organization=openai_organization,
        openai_enabled=openai_enabled,
        embedding_model=embedding_model,
    )
