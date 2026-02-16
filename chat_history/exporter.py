from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable

from chat_history.models import ConversationRecord, MessageRecord


def _visible_message_text(
    message: MessageRecord,
    *,
    include_system: bool,
    include_tool: bool,
    include_thinking: bool,
    include_attachments: bool,
) -> str:
    if not include_system and message.role == "system":
        return ""
    if not include_tool and message.role == "tool":
        return ""

    parts: list[str] = []
    for block in message.iter_visible_blocks(
        include_system=include_system,
        include_tool=include_tool,
        include_thinking=include_thinking,
        include_attachments=include_attachments,
    ):
        block_text = block.text.strip()
        if not block_text:
            continue

        if block.type in {"text", "code"}:
            parts.append(block_text)
        else:
            parts.append(f"**[{block.type}]**\n\n{block_text}")

    return "\n\n".join(parts).strip()


def _iter_messages(
    conversation: ConversationRecord,
    *,
    include_system: bool,
    include_tool: bool,
    include_thinking: bool,
    include_attachments: bool,
) -> Iterable[str]:
    for message in conversation.messages:
        text = _visible_message_text(
            message,
            include_system=include_system,
            include_tool=include_tool,
            include_thinking=include_thinking,
            include_attachments=include_attachments,
        )
        if not text:
            continue

        yield f"## {message.created_str} - {message.role}\n\n{text}"


def _file_hash(conversation_id: str) -> str:
    return hashlib.sha1(conversation_id.encode("utf-8")).hexdigest()[:12]


def _file_name(conversation: ConversationRecord) -> str:
    date_part = conversation.created.astimezone().strftime("%Y-%m-%d")
    hash_part = _file_hash(conversation.id)
    return f"{date_part}-{hash_part}.md"


def export_conversation(
    *,
    conversation: ConversationRecord,
    output_dir: Path,
    include_system: bool,
    include_tool: bool,
    include_thinking: bool,
    include_attachments: bool,
) -> Path:
    provider_dir = output_dir / conversation.provider
    provider_dir.mkdir(parents=True, exist_ok=True)
    output_path = provider_dir / _file_name(conversation)

    message_sections = list(
        _iter_messages(
            conversation,
            include_system=include_system,
            include_tool=include_tool,
            include_thinking=include_thinking,
            include_attachments=include_attachments,
        )
    )

    header = [
        f"# {conversation.title_str}",
        "",
        f"- Provider: `{conversation.provider}`",
        f"- Conversation ID: `{conversation.id}`",
        f"- Created: `{conversation.created_str}`",
        f"- Open URL: {conversation.open_url}",
        "",
    ]
    payload = "\n".join(header + message_sections + [""])

    output_path.write_text(payload, encoding="utf-8")
    return output_path
