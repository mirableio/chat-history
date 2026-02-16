from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from chat_history.models import ContentBlock, ConversationRecord, MessageRecord, Provider, utc_now

CITATION_MARKER_RE = re.compile(r"cite.*?")
MARKDOWN_LINK_URL_RE = re.compile(r"\((https?://[^)\s]+)\)")


def _parse_unix_datetime(raw_value: Any, fallback: datetime | None = None) -> datetime:
    if isinstance(raw_value, (int, float)):
        return datetime.fromtimestamp(float(raw_value), tz=timezone.utc)
    if isinstance(raw_value, str):
        try:
            return datetime.fromtimestamp(float(raw_value), tz=timezone.utc)
        except ValueError:
            pass
    if fallback is not None:
        return fallback
    return utc_now()


def _parse_iso_datetime(raw_value: Any, fallback: datetime | None = None) -> datetime:
    if isinstance(raw_value, str):
        normalized = raw_value.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass
    if fallback is not None:
        return fallback
    return utc_now()


def _humanize_identifier(raw_value: str) -> str:
    return raw_value.replace("_", " ").strip().capitalize()


def _lightweight_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    preserve_long_text_keys = {
        "asset_pointer",
        "audio_asset_pointer",
        "video_container_asset_pointer",
        "url",
        "ref_id",
        "file_name",
        "file_type",
        "tool_use_id",
        "command",
        "name",
        "id",
    }
    result: dict[str, Any] = {}
    for key, value in payload.items():
        if key in {"text", "thinking", "parts", "content", "thoughts"}:
            continue
        if isinstance(value, (int, float, bool)):
            result[key] = value
            continue
        if isinstance(value, str):
            if key in preserve_long_text_keys:
                result[key] = value if len(value) <= 2000 else value[:2000]
            elif len(value) <= 200:
                result[key] = value
    return result


def _extract_text(value: Any, depth: int = 0) -> str:
    if depth > 5 or value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        parts = [_extract_text(item, depth + 1) for item in value[:12]]
        return "\n".join(part for part in parts if part).strip()
    if isinstance(value, dict):
        skipped_keys = {
            "content_type",
            "type",
            "role",
            "status",
            "recipient",
            "channel",
        }
        priority_keys = (
            "text",
            "thinking",
            "summary",
            "message",
            "title",
            "name",
            "content",
            "url",
            "snippet",
            "domain",
        )
        ordered_keys = list(priority_keys) + [
            key for key in value.keys() if key not in priority_keys
        ]
        parts: list[str] = []
        for key in ordered_keys[:16]:
            if key in skipped_keys:
                continue
            text_value = _extract_text(value.get(key), depth + 1)
            if text_value:
                parts.append(text_value)
        return "\n".join(parts).strip()
    return ""


def _parse_chatgpt_part(content_type: str, part: Any) -> list[ContentBlock]:
    if isinstance(part, str):
        text = part.strip()
        return [ContentBlock(type=content_type, text=text)] if text else []

    if not isinstance(part, dict):
        return []

    part_type = str(part.get("content_type", "object"))
    text = (
        _extract_text(part.get("text"))
        or _extract_text(part.get("message"))
        or _extract_text(part.get("title"))
    )

    if not text:
        text = f"[{_humanize_identifier(part_type)}]"

    return [ContentBlock(type=part_type, text=text, data=_lightweight_metadata(part))]


def _normalize_text_for_dedupe(value: str) -> str:
    return " ".join(value.split()).strip()


def _normalize_reference_url(raw_url: str) -> str:
    cleaned = raw_url.strip()
    if not cleaned:
        return ""
    split = urlsplit(cleaned)
    if split.scheme not in {"http", "https"}:
        return cleaned
    filtered_query = [
        (key, value)
        for key, value in parse_qsl(split.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
    ]
    query = urlencode(filtered_query, doseq=True)
    return urlunsplit((split.scheme, split.netloc, split.path, query, split.fragment))


def _extract_reference_urls(reference: dict[str, Any]) -> list[str]:
    collected: list[str] = []

    alt = reference.get("alt")
    if isinstance(alt, str) and alt.strip():
        collected.extend(MARKDOWN_LINK_URL_RE.findall(alt))

    safe_urls = reference.get("safe_urls")
    if isinstance(safe_urls, list):
        for url in safe_urls:
            if isinstance(url, str) and url.strip():
                collected.append(url.strip())

    items = reference.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if isinstance(url, str) and url.strip():
                collected.append(url.strip())
    return collected


def _reference_label(url: str) -> str:
    split = urlsplit(url)
    if split.scheme not in {"http", "https"}:
        return url
    path = split.path or ""
    if path in {"", "/"}:
        return split.netloc
    return f"{split.netloc}{path}"


def _render_content_reference_links(references: list[dict[str, Any]]) -> str:
    deduped_urls: list[str] = []
    seen_urls: set[str] = set()
    for reference in references:
        for raw_url in _extract_reference_urls(reference):
            normalized = _normalize_reference_url(raw_url)
            if not normalized or normalized in seen_urls:
                continue
            seen_urls.add(normalized)
            deduped_urls.append(normalized)

    if not deduped_urls:
        return ""

    links = [f"[{_reference_label(url)}]({url})" for url in deduped_urls]
    return f"({' · '.join(links)})"


def _apply_chatgpt_content_references(
    text: str,
    message_metadata: dict[str, Any] | None,
) -> str:
    if not text:
        return text
    if not isinstance(message_metadata, dict):
        return CITATION_MARKER_RE.sub("", text)

    references = message_metadata.get("content_references")
    replacements: dict[str, str] = {}
    grouped_references: dict[str, list[dict[str, Any]]] = {}
    if isinstance(references, list):
        for reference in references:
            if not isinstance(reference, dict):
                continue
            matched_text = reference.get("matched_text")
            if not isinstance(matched_text, str) or not matched_text:
                continue
            grouped_references.setdefault(matched_text, []).append(reference)

    for matched_text, refs in grouped_references.items():
        replacement = _render_content_reference_links(refs)
        if replacement:
            replacements[matched_text] = replacement

    rendered = text
    for matched_text, replacement in sorted(
        replacements.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        rendered = rendered.replace(matched_text, replacement)

    return CITATION_MARKER_RE.sub("", rendered)


def _parse_chatgpt_content(
    content: Any,
    *,
    message_metadata: dict[str, Any] | None = None,
) -> list[ContentBlock]:
    if not isinstance(content, dict):
        return []

    content_type = str(content.get("content_type", "unknown"))
    blocks: list[ContentBlock] = []

    if content_type == "thoughts":
        thoughts_text = _extract_text(content.get("thoughts"))
        if thoughts_text:
            blocks.append(ContentBlock(type="thoughts", text=thoughts_text))
    elif content_type == "reasoning_recap":
        recap_text = _extract_text(content.get("content"))
        if recap_text:
            blocks.append(ContentBlock(type="reasoning_recap", text=recap_text))
    elif content_type == "tether_browsing_display":
        browsing_text = _extract_text(content.get("summary")) or _extract_text(content.get("result"))
        if browsing_text:
            blocks.append(ContentBlock(type="tether_browsing_display", text=browsing_text))
    else:
        direct_text = _extract_text(content.get("text"))
        if direct_text:
            blocks.append(
                ContentBlock(type=content_type, text=direct_text, data=_lightweight_metadata(content))
            )

        parts = content.get("parts")
        if isinstance(parts, list):
            for part in parts:
                blocks.extend(_parse_chatgpt_part(content_type, part))

    if content_type == "code" and not blocks:
        metadata = message_metadata or {}
        code_text = _extract_text(metadata.get("finished_text")) or _extract_text(
            metadata.get("initial_text")
        )
        if code_text:
            blocks.append(
                ContentBlock(
                    type="code",
                    text=code_text,
                    data=_lightweight_metadata({**metadata, **content}),
                )
            )

    if not blocks:
        fallback_text = _extract_text(content)
        if not fallback_text and content_type == "text":
            return []
        if fallback_text and fallback_text.strip().lower() == content_type.strip().lower():
            if content_type == "text":
                return []
            fallback_text = ""
        blocks.append(
            ContentBlock(
                type=content_type,
                text=fallback_text or f"[{_humanize_identifier(content_type)}]",
                data=_lightweight_metadata(content),
            )
        )

    deduplicated: list[ContentBlock] = []
    seen: set[tuple[str, str]] = set()
    for block in blocks:
        rendered_text = _apply_chatgpt_content_references(block.text, message_metadata).strip()
        if not rendered_text:
            continue
        key = (block.type, _normalize_text_for_dedupe(rendered_text))
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(ContentBlock(type=block.type, text=rendered_text, data=block.data))
    return deduplicated


def _build_active_branch_path(mapping: dict[str, Any], current_node: str | None) -> list[str]:
    if not mapping:
        return []

    if current_node and current_node in mapping:
        path: list[str] = []
        cursor = current_node
        seen: set[str] = set()
        while cursor and cursor in mapping and cursor not in seen:
            seen.add(cursor)
            path.append(cursor)
            cursor = mapping[cursor].get("parent")
        path.reverse()
        return path

    # Fallback when current_node is missing: sort by message timestamp.
    sortable_nodes: list[tuple[float, str]] = []
    for node_id, node in mapping.items():
        message = node.get("message")
        if not isinstance(message, dict):
            continue
        create_time = message.get("create_time")
        if isinstance(create_time, (int, float)):
            sortable_nodes.append((float(create_time), node_id))
    sortable_nodes.sort()
    return [node_id for _, node_id in sortable_nodes]


def parse_chatgpt_export(path: Path) -> list[ConversationRecord]:
    with path.open("r") as file_handle:
        raw_conversations = json.load(file_handle)

    conversations: list[ConversationRecord] = []
    for raw_conversation in raw_conversations:
        if not isinstance(raw_conversation, dict):
            continue

        conversation_id = str(
            raw_conversation.get("id") or raw_conversation.get("conversation_id") or ""
        ).strip()
        if not conversation_id:
            continue

        created = _parse_unix_datetime(raw_conversation.get("create_time"))
        updated = _parse_unix_datetime(raw_conversation.get("update_time"), fallback=created)
        title = str(raw_conversation.get("title") or "[Untitled]")
        default_model = raw_conversation.get("default_model_slug")

        mapping = raw_conversation.get("mapping") or {}
        if not isinstance(mapping, dict):
            mapping = {}
        node_ids = _build_active_branch_path(mapping, raw_conversation.get("current_node"))

        messages: list[MessageRecord] = []
        for node_id in node_ids:
            node = mapping.get(node_id) or {}
            raw_message = node.get("message")
            if not isinstance(raw_message, dict):
                continue

            message_id = str(raw_message.get("id") or node_id)
            author = raw_message.get("author") or {}
            role = str(author.get("role") or "unknown")
            message_created = _parse_unix_datetime(raw_message.get("create_time"), fallback=created)
            message_updated = _parse_unix_datetime(raw_message.get("update_time"), fallback=message_created)

            metadata = raw_message.get("metadata") or {}
            if isinstance(metadata, dict) and metadata.get("is_visually_hidden_from_conversation"):
                continue
            model = metadata.get("model_slug") or default_model

            content_blocks = _parse_chatgpt_content(
                raw_message.get("content"),
                message_metadata=metadata if isinstance(metadata, dict) else None,
            )
            if not content_blocks:
                continue

            messages.append(
                MessageRecord(
                    id=message_id,
                    provider="chatgpt",
                    role=role,
                    created=message_created,
                    updated=message_updated,
                    model=model,
                    content=content_blocks,
                )
            )

        if messages:
            created = min(created, messages[0].created)
            updated = max(updated, messages[-1].created)

        conversations.append(
            ConversationRecord(
                id=conversation_id,
                provider="chatgpt",
                title=title,
                created=created,
                updated=updated,
                messages=messages,
            )
        )

    return conversations


def _parse_claude_content_block(block: dict[str, Any]) -> ContentBlock:
    block_type = str(block.get("type") or "unknown")

    if block_type == "text":
        text = _extract_text(block.get("text"))
    elif block_type == "thinking":
        text = _extract_text(block.get("thinking"))
    elif block_type == "tool_use":
        text = _extract_text(block.get("message")) or _extract_text(block.get("input"))
    elif block_type == "tool_result":
        text = (
            _extract_text(block.get("message"))
            or _extract_text(block.get("content"))
            or _extract_text(block.get("display_content"))
        )
    elif block_type == "voice_note":
        text = _extract_text(block.get("text")) or _extract_text(block.get("title"))
    else:
        text = _extract_text(block)

    if not text:
        text = f"[{_humanize_identifier(block_type)}]"

    return ContentBlock(type=block_type, text=text, data=_lightweight_metadata(block))


def parse_claude_export(path: Path) -> list[ConversationRecord]:
    with path.open("r") as file_handle:
        raw_conversations = json.load(file_handle)

    conversations: list[ConversationRecord] = []
    for raw_conversation in raw_conversations:
        if not isinstance(raw_conversation, dict):
            continue

        conversation_id = str(raw_conversation.get("uuid") or "").strip()
        if not conversation_id:
            continue

        created = _parse_iso_datetime(raw_conversation.get("created_at"))
        updated = _parse_iso_datetime(raw_conversation.get("updated_at"), fallback=created)
        title = str(raw_conversation.get("name") or "[Untitled]")

        raw_messages = raw_conversation.get("chat_messages") or []
        if not isinstance(raw_messages, list):
            raw_messages = []

        messages: list[MessageRecord] = []
        for raw_message in raw_messages:
            if not isinstance(raw_message, dict):
                continue

            message_id = str(raw_message.get("uuid") or "")
            if not message_id:
                continue

            sender = str(raw_message.get("sender") or "unknown")
            role = "user" if sender == "human" else sender
            message_created = _parse_iso_datetime(raw_message.get("created_at"), fallback=created)
            message_updated = _parse_iso_datetime(raw_message.get("updated_at"), fallback=message_created)

            content_blocks: list[ContentBlock] = []
            structured_content = raw_message.get("content")
            if isinstance(structured_content, list):
                for block in structured_content:
                    if isinstance(block, dict):
                        content_blocks.append(_parse_claude_content_block(block))

            # Claude's top-level text is derived text; only use it if blocks are absent.
            if not content_blocks:
                fallback_text = _extract_text(raw_message.get("text"))
                if fallback_text:
                    content_blocks.append(ContentBlock(type="text", text=fallback_text))

            attachments = raw_message.get("attachments")
            if isinstance(attachments, list):
                for attachment in attachments:
                    if not isinstance(attachment, dict):
                        continue
                    file_name = str(attachment.get("file_name") or "attachment")
                    attachment_type = str(attachment.get("file_type") or "unknown")
                    content_blocks.append(
                        ContentBlock(
                            type="attachment",
                            text=f"[Attachment] {file_name} ({attachment_type})",
                            data=_lightweight_metadata(attachment),
                        )
                    )

            files = raw_message.get("files")
            if isinstance(files, list):
                for file_record in files:
                    if not isinstance(file_record, dict):
                        continue
                    file_name = str(file_record.get("file_name") or "file")
                    content_blocks.append(
                        ContentBlock(
                            type="file",
                            text=f"[File] {file_name}",
                            data=_lightweight_metadata(file_record),
                        )
                    )

            if not content_blocks:
                continue

            messages.append(
                MessageRecord(
                    id=message_id,
                    provider="claude",
                    role=role,
                    created=message_created,
                    updated=message_updated,
                    model=None,
                    content=content_blocks,
                )
            )

        messages.sort(key=lambda message: message.created)
        if messages:
            created = min(created, messages[0].created)
            updated = max(updated, messages[-1].created)

        conversations.append(
            ConversationRecord(
                id=conversation_id,
                provider="claude",
                title=title,
                created=created,
                updated=updated,
                messages=messages,
            )
        )

    return conversations


def load_provider_conversations(
    *,
    chatgpt_path: Path | None,
    claude_path: Path | None,
) -> list[ConversationRecord]:
    conversations: list[ConversationRecord] = []

    if chatgpt_path and chatgpt_path.exists():
        conversations.extend(parse_chatgpt_export(chatgpt_path))

    if claude_path and claude_path.exists():
        conversations.extend(parse_claude_export(claude_path))

    conversations.sort(key=lambda conversation: conversation.created, reverse=True)
    return conversations
