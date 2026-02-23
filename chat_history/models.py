from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Literal

import tiktoken


Provider = Literal["chatgpt", "claude", "gemini"]

THINKING_BLOCK_TYPES = {"thinking", "thoughts", "reasoning_recap"}
TOOL_BLOCK_TYPES = {"tool_use", "tool_result", "execution_output", "tether_browsing_display"}
ATTACHMENT_BLOCK_TYPES = {
    "image_asset_pointer",
    "audio_asset_pointer",
    "real_time_user_audio_video_asset_pointer",
    "attachment",
    "file",
    "inline_image",
    "inline_audio",
    "drive_document",
    "drive_video",
}
GROUNDING_BLOCK_TYPES = {"grounding"}
SYSTEM_BLOCK_TYPES = {"system_error"}


def _safe_encoding(model_name: str | None):
    if model_name:
        try:
            return tiktoken.encoding_for_model(model_name)
        except KeyError:
            pass
    return tiktoken.get_encoding("cl100k_base")


def to_local_display(dt: datetime) -> str:
    return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")


@dataclass(slots=True)
class ContentBlock:
    type: str
    text: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MessageRecord:
    id: str
    provider: Provider
    role: str
    created: datetime
    updated: datetime | None
    model: str | None
    content: list[ContentBlock]

    def iter_visible_blocks(
        self,
        *,
        include_system: bool = True,
        include_tool: bool = True,
        include_thinking: bool = True,
        include_attachments: bool = True,
    ) -> Iterable[ContentBlock]:
        if not include_system and self.role == "system":
            return []

        visible_blocks = []
        for block in self.content:
            block_type = block.type
            if not include_thinking and block_type in THINKING_BLOCK_TYPES:
                continue
            if not include_tool and (block_type in TOOL_BLOCK_TYPES or self.role == "tool"):
                continue
            if not include_attachments and block_type in ATTACHMENT_BLOCK_TYPES:
                continue
            if not include_system and block_type in SYSTEM_BLOCK_TYPES:
                continue
            visible_blocks.append(block)
        return visible_blocks

    def text(
        self,
        *,
        include_system: bool = True,
        include_tool: bool = True,
        include_thinking: bool = True,
        include_attachments: bool = True,
    ) -> str:
        blocks = self.iter_visible_blocks(
            include_system=include_system,
            include_tool=include_tool,
            include_thinking=include_thinking,
            include_attachments=include_attachments,
        )
        parts = [block.text.strip() for block in blocks if block.text.strip()]
        return "\n\n".join(parts).strip()

    def count_tokens(self) -> int:
        message_text = self.text()
        if not message_text:
            return 0
        encoding = _safe_encoding(self.model)
        return len(encoding.encode(message_text))

    @property
    def created_str(self) -> str:
        return to_local_display(self.created)


@dataclass(slots=True)
class ConversationRecord:
    id: str
    provider: Provider
    title: str
    created: datetime
    updated: datetime
    messages: list[MessageRecord]

    @property
    def title_str(self) -> str:
        return self.title or "[Untitled]"

    @property
    def created_str(self) -> str:
        return to_local_display(self.created)

    @property
    def total_length_seconds(self) -> float:
        if not self.messages:
            return 0.0
        end_time = max(message.created for message in self.messages)
        return max((end_time - self.created).total_seconds(), 0.0)

    @property
    def open_url(self) -> str:
        if self.provider == "claude":
            return f"https://claude.ai/chat/{self.id}"
        if self.provider == "gemini":
            return "https://aistudio.google.com/"
        return f"https://chat.openai.com/c/{self.id}"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
