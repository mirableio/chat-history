from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from models import ConversationRecord, MessageRecord


def _slugify(raw_text: str) -> str:
    text = raw_text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text[:80] or "untitled"


def _visible_message_text(
    message: MessageRecord,
    *,
    include_system: bool,
    include_tool: bool,
    include_thinking: bool,
    include_attachments: bool,
    markdown_mode: bool,
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

        if markdown_mode:
            if block.type in {"text", "code"}:
                parts.append(block_text)
            else:
                parts.append(f"**[{block.type}]**\n\n{block_text}")
        else:
            if block.type in {"text", "code"}:
                parts.append(block_text)
            else:
                parts.append(f"[{block.type}] {block_text}")

    return "\n\n".join(parts).strip()


def _iter_messages(
    conversation: ConversationRecord,
    *,
    include_system: bool,
    include_tool: bool,
    include_thinking: bool,
    include_attachments: bool,
    markdown_mode: bool,
) -> Iterable[str]:
    for message in conversation.messages:
        text = _visible_message_text(
            message,
            include_system=include_system,
            include_tool=include_tool,
            include_thinking=include_thinking,
            include_attachments=include_attachments,
            markdown_mode=markdown_mode,
        )
        if not text:
            continue

        if markdown_mode:
            yield f"## {message.created_str} - {message.role}\n\n{text}"
        else:
            yield f"{message.created_str} - {message.role}\n{text}"


def export_conversation(
    *,
    conversation: ConversationRecord,
    output_dir: Path,
    output_format: str,
    include_system: bool,
    include_tool: bool,
    include_thinking: bool,
    include_attachments: bool,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    extension = "md" if output_format == "markdown" else "txt"
    slug = _slugify(conversation.title_str)
    file_name = f"{conversation.provider}--{slug}--{conversation.id}.{extension}"
    output_path = output_dir / file_name

    markdown_mode = output_format == "markdown"
    message_sections = list(
        _iter_messages(
            conversation,
            include_system=include_system,
            include_tool=include_tool,
            include_thinking=include_thinking,
            include_attachments=include_attachments,
            markdown_mode=markdown_mode,
        )
    )

    if markdown_mode:
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
    else:
        header = [
            conversation.title_str,
            f"Provider: {conversation.provider}",
            f"Conversation ID: {conversation.id}",
            f"Created: {conversation.created_str}",
            f"Open URL: {conversation.open_url}",
            "",
        ]
        payload = "\n\n".join(header + message_sections + [""])

    output_path.write_text(payload, encoding="utf-8")
    return output_path
