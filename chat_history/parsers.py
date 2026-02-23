from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from chat_history.coerce import (
    float_or_none as _float_or_none,
    int_or_none as _int_or_none,
    string_or_none as _string_or_none,
)
from chat_history.models import ContentBlock, ConversationRecord, MessageRecord, Provider, utc_now
from chat_history.validation import ValidationReport

CITATION_MARKER_RE = re.compile(r"cite.*?")
MARKDOWN_LINK_URL_RE = re.compile(r"\((https?://[^)\s]+)\)")
CHATGPT_ASSET_KIND_BY_PART_TYPE = {
    "image_asset_pointer": "image",
    "audio_asset_pointer": "audio",
    "real_time_user_audio_video_asset_pointer": "audio",
}


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


def _chatgpt_asset_placeholder(part_type: str) -> str:
    kind = CHATGPT_ASSET_KIND_BY_PART_TYPE.get(part_type)
    if kind == "image":
        return "[Image]"
    if kind == "audio":
        return "[Audio]"
    return f"[{_humanize_identifier(part_type)}]"


def _extract_chatgpt_asset_pointer(part: dict[str, Any]) -> str | None:
    for key in ("asset_pointer", "audio_asset_pointer", "video_container_asset_pointer", "id"):
        value = _string_or_none(part.get(key))
        if value:
            return value
    return None


def _build_chatgpt_asset_metadata(part_type: str, part: dict[str, Any]) -> dict[str, Any] | None:
    kind = CHATGPT_ASSET_KIND_BY_PART_TYPE.get(part_type)
    if not kind:
        return None

    source_pointer = _extract_chatgpt_asset_pointer(part)
    duration = (
        _float_or_none(part.get("duration_seconds"))
        or _float_or_none(part.get("duration_sec"))
        or _float_or_none(part.get("duration"))
    )

    return {
        "asset_id": None,
        "kind": kind,
        "source_pointer": source_pointer,
        "mime_type": _string_or_none(part.get("mime_type")),
        "size_bytes": _int_or_none(part.get("size_bytes")),
        "width": _int_or_none(part.get("width")),
        "height": _int_or_none(part.get("height")),
        "format": _string_or_none(part.get("format")),
        "duration": duration,
        "is_resolved": False,
        "asset_url": None,
    }


def _fallback_file_name(prefix: str, index: int) -> str:
    return f"{prefix}-{index + 1}"


def _build_claude_attachment_block(
    attachment: dict[str, Any],
    *,
    attachment_index: int,
) -> ContentBlock:
    raw_file_name = _string_or_none(attachment.get("file_name"))
    file_name = raw_file_name or _fallback_file_name("attachment", attachment_index)
    file_type = _string_or_none(attachment.get("file_type")) or "unknown"
    extracted_content = _string_or_none(attachment.get("extracted_content"))
    file_size = _int_or_none(attachment.get("file_size"))

    metadata = _lightweight_metadata(attachment)
    metadata["file_name"] = file_name
    metadata["file_type"] = file_type
    metadata["attachment_index"] = attachment_index
    if file_size is not None:
        metadata["file_size"] = file_size

    if extracted_content:
        metadata["has_extracted_content"] = True
        metadata["attachment_label"] = f"{file_name} ({file_type})"
        metadata["extracted_content_length"] = len(extracted_content)
        text = extracted_content
    else:
        metadata["has_extracted_content"] = False
        text = f"[Attachment] {file_name} ({file_type})"

    return ContentBlock(type="attachment", text=text, data=metadata)


def _build_claude_file_block(file_record: dict[str, Any], *, file_index: int) -> ContentBlock:
    raw_file_name = _string_or_none(file_record.get("file_name"))
    file_name = raw_file_name or _fallback_file_name("file", file_index)
    metadata = _lightweight_metadata(file_record)
    metadata["file_name"] = file_name
    metadata["file_index"] = file_index
    return ContentBlock(
        type="file",
        text=f"[File] {file_name}",
        data=metadata,
    )


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
    asset_metadata = _build_chatgpt_asset_metadata(part_type, part)

    if not text:
        text = _chatgpt_asset_placeholder(part_type)

    metadata = _lightweight_metadata(part)
    if asset_metadata:
        metadata["asset"] = asset_metadata

    return [ContentBlock(type=part_type, text=text, data=metadata)]


def _normalize_text_for_dedupe(value: str) -> str:
    return " ".join(value.split()).strip()


def _chatgpt_block_dedupe_key(block: ContentBlock, rendered_text: str) -> tuple[str, ...]:
    normalized_text = _normalize_text_for_dedupe(rendered_text)
    block_data = block.data if isinstance(block.data, dict) else {}
    asset_payload = block_data.get("asset")
    if isinstance(asset_payload, dict):
        source_pointer = _string_or_none(asset_payload.get("source_pointer"))
        if source_pointer:
            return (block.type, normalized_text, source_pointer)

    source_pointer = _string_or_none(block_data.get("asset_pointer"))
    if source_pointer:
        return (block.type, normalized_text, source_pointer)

    return (block.type, normalized_text)


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
    seen: set[tuple[str, ...]] = set()
    for block in blocks:
        rendered_text = _apply_chatgpt_content_references(block.text, message_metadata).strip()
        if not rendered_text:
            continue
        key = _chatgpt_block_dedupe_key(block, rendered_text)
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
                for attachment_index, attachment in enumerate(attachments):
                    if not isinstance(attachment, dict):
                        continue
                    content_blocks.append(
                        _build_claude_attachment_block(
                            attachment,
                            attachment_index=attachment_index,
                        )
                    )

            files = raw_message.get("files")
            if isinstance(files, list):
                for file_index, file_record in enumerate(files):
                    if not isinstance(file_record, dict):
                        continue
                    content_blocks.append(
                        _build_claude_file_block(file_record, file_index=file_index)
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


# ---------------------------------------------------------------------------
# Gemini (Google AI Studio) parser
# ---------------------------------------------------------------------------

# Keys from the *merged* conversation envelope (id/title/times are added by the
# merger; everything else comes from the original file).
_GEMINI_CONVERSATION_KEYS = {
    "id", "title", "create_time", "update_time",
    "chunkedPrompt", "runSettings", "systemInstruction",
    "imagenPrompt",
}
_GEMINI_CHUNKED_PROMPT_KEYS = {
    "chunks", "pendingInputs",
}
_GEMINI_CHUNK_KEYS = {
    "text", "parts", "role", "tokenCount", "finishReason",
    "isEdited", "branchParent", "branchChildren",
    "grounding", "thoughtSignatures", "thinkingBudget",
    "inlineImage", "inlineAudio", "driveDocument", "driveVideo",
    "driveAudio", "driveImage",
    "inlineData", "isGeneratedUsingApiKey", "isThought",
}
_GEMINI_PART_KEYS = {
    "text", "thought", "thoughtSignature", "inlineData",
}
_GEMINI_RUN_SETTINGS_KEYS = {
    "model", "temperature", "topP", "topK", "maxOutputTokens",
    "safetySettings", "responseMimeType",
    "responseModalities", "thinkingConfig",
    "enableCodeExecution", "enableSearchAsATool",
    "enableBrowseAsATool", "enableAutoFunctionResponse",
    "outputResolution", "googleSearch", "thinkingLevel",
    "thinkingBudget", "assetCount", "aspectRatio",
}


def _parse_gemini_inline_data(inline_data: dict[str, Any], source: str) -> ContentBlock | None:
    """Build an inline_image or inline_audio block from a base64-carrying dict."""
    mime = _string_or_none(inline_data.get("mimeType")) or ""
    data_b64 = _string_or_none(inline_data.get("data")) or ""
    data_uri = f"data:{mime};base64,{data_b64}" if data_b64 else None

    if mime.startswith("image/"):
        return ContentBlock(
            type="inline_image",
            text="[Inline Image]",
            data={"mime_type": mime, "data_uri": data_uri, "source": source},
        )
    if mime.startswith("audio/"):
        return ContentBlock(
            type="inline_audio",
            text="[Inline Audio]",
            data={"mime_type": mime, "data_uri": data_uri, "source": source},
        )
    return None


def _parse_gemini_grounding(grounding: dict[str, Any]) -> ContentBlock | None:
    """Build a grounding block with formatted citation links."""
    text_parts: list[str] = []

    segments = grounding.get("corroborationSegments")
    if isinstance(segments, list):
        for segment in segments:
            if not isinstance(segment, dict):
                continue
            uri = _string_or_none(segment.get("uri")) or ""
            title = _string_or_none(segment.get("title")) or uri
            footnote = segment.get("footnoteNumber")
            if uri:
                prefix = f"[{footnote}] " if footnote is not None else ""
                text_parts.append(f"{prefix}[{title}]({uri})")

    sources = grounding.get("groundingSources")
    if isinstance(sources, list):
        for source in sources:
            if not isinstance(source, dict):
                continue
            uri = _string_or_none(source.get("uri")) or ""
            title = _string_or_none(source.get("title")) or uri
            footnote = source.get("footnoteNumber")
            if uri:
                prefix = f"[{footnote}] " if footnote is not None else ""
                text_parts.append(f"{prefix}[{title}]({uri})")

    queries = grounding.get("webSearchQueries")
    if isinstance(queries, list):
        for query in queries:
            if isinstance(query, str) and query.strip():
                text_parts.append(f"Search: {query.strip()}")

    if not text_parts:
        return None
    return ContentBlock(
        type="grounding",
        text="\n".join(text_parts),
        data={},
    )


def _parse_gemini_chunk(
    chunk: dict[str, Any],
    *,
    report: ValidationReport,
) -> list[ContentBlock]:
    """Parse a single Gemini chunk into ContentBlocks."""
    blocks: list[ContentBlock] = []

    # --- parts (structured text / inline data) ---
    # Consecutive text parts are streaming fragments of one reply — join
    # directly (no separator) so markdown renders correctly.
    # Consecutive thinking parts are logically separate thoughts — join
    # with a blank line so they read as distinct sections.
    parts = chunk.get("parts")
    if isinstance(parts, list):
        text_accum: list[str] = []
        thought_accum: list[str] = []

        def _flush_text() -> None:
            if text_accum:
                merged = text_accum[0]
                for fragment in text_accum[1:]:
                    if merged and fragment and merged[-1].isalpha() and fragment[0].isalpha():
                        merged += " "
                    merged += fragment
                blocks.append(ContentBlock(type="text", text=merged.strip()))
                text_accum.clear()

        def _flush_thought() -> None:
            if thought_accum:
                blocks.append(ContentBlock(
                    type="thinking",
                    text="\n\n".join(thought_accum),
                    data={},
                ))
                thought_accum.clear()

        def _flush_all() -> None:
            _flush_thought()
            _flush_text()

        for part in parts:
            if not isinstance(part, dict):
                continue

            report.check_keys(part, _GEMINI_PART_KEYS, "part")

            part_text = _string_or_none(part.get("text")) or ""
            is_thought = bool(part.get("thought"))

            if is_thought and part_text.strip():
                _flush_text()
                thought_accum.append(part_text.strip())
            elif part_text.strip():
                _flush_thought()
                text_accum.append(part_text)

            inline_data = part.get("inlineData")
            if isinstance(inline_data, dict):
                _flush_all()
                block = _parse_gemini_inline_data(inline_data, "part_inlineData")
                if block:
                    blocks.append(block)

        _flush_all()

    # --- fallback: top-level text (if no blocks from parts) ---
    if not blocks:
        top_text = _string_or_none(chunk.get("text"))
        if top_text and top_text.strip():
            blocks.append(ContentBlock(type="text", text=top_text.strip()))

    # --- chunk-level inlineImage (model-generated images) ---
    inline_image = chunk.get("inlineImage")
    if isinstance(inline_image, dict):
        mime = _string_or_none(inline_image.get("mimeType")) or "image/png"
        data_b64 = _string_or_none(inline_image.get("data")) or ""
        data_uri = f"data:{mime};base64,{data_b64}" if data_b64 else None
        blocks.append(ContentBlock(
            type="inline_image",
            text="[Generated Image]",
            data={"mime_type": mime, "data_uri": data_uri, "source": "inlineImage"},
        ))

    # --- chunk-level inlineAudio (user audio input) ---
    inline_audio = chunk.get("inlineAudio")
    if isinstance(inline_audio, dict):
        mime = _string_or_none(inline_audio.get("mimeType")) or "audio/wav"
        data_b64 = _string_or_none(inline_audio.get("data")) or ""
        data_uri = f"data:{mime};base64,{data_b64}" if data_b64 else None
        blocks.append(ContentBlock(
            type="inline_audio",
            text="[Audio Input]",
            data={"mime_type": mime, "data_uri": data_uri, "source": "inlineAudio"},
        ))

    # --- chunk-level inlineData (generic inline media) ---
    inline_data_top = chunk.get("inlineData")
    if isinstance(inline_data_top, dict):
        block = _parse_gemini_inline_data(inline_data_top, "chunk_inlineData")
        if block:
            blocks.append(block)

    # --- chunk-level driveImage (user-uploaded image from Drive) ---
    drive_image = chunk.get("driveImage")
    if isinstance(drive_image, dict):
        drive_id = _string_or_none(drive_image.get("id")) or ""
        blocks.append(ContentBlock(
            type="drive_document",
            text="[Drive Image]",
            data={"id": drive_id, "kind": "image"},
        ))

    # --- chunk-level driveAudio (user-uploaded audio from Drive) ---
    drive_audio = chunk.get("driveAudio")
    if isinstance(drive_audio, dict):
        drive_id = _string_or_none(drive_audio.get("id")) or ""
        blocks.append(ContentBlock(
            type="drive_document",
            text="[Drive Audio]",
            data={"id": drive_id, "kind": "audio"},
        ))

    # --- driveDocument ---
    drive_doc = chunk.get("driveDocument")
    if isinstance(drive_doc, dict):
        doc_name = _string_or_none(drive_doc.get("name")) or "[Drive Document]"
        blocks.append(ContentBlock(
            type="drive_document",
            text=f"[Drive Document] {doc_name}",
            data={k: v for k, v in drive_doc.items() if isinstance(v, (str, int, float, bool))},
        ))

    # --- driveVideo ---
    drive_video = chunk.get("driveVideo")
    if isinstance(drive_video, dict):
        video_name = _string_or_none(drive_video.get("name")) or "[Drive Video]"
        blocks.append(ContentBlock(
            type="drive_video",
            text=f"[Drive Video] {video_name}",
            data={k: v for k, v in drive_video.items() if isinstance(v, (str, int, float, bool))},
        ))

    # --- grounding (web search citations) ---
    grounding = chunk.get("grounding")
    if isinstance(grounding, dict):
        grounding_block = _parse_gemini_grounding(grounding)
        if grounding_block:
            blocks.append(grounding_block)

    # --- validation ---
    report.check_keys(chunk, _GEMINI_CHUNK_KEYS, "chunk")

    return blocks


def _extract_gemini_model(run_settings: dict[str, Any] | None) -> str | None:
    if not isinstance(run_settings, dict):
        return None
    raw = _string_or_none(run_settings.get("model"))
    if not raw:
        return None
    # Strip "models/" prefix for cleaner display
    if raw.startswith("models/"):
        return raw[len("models/"):]
    return raw


def _extract_gemini_system_text(
    raw_conversation: dict[str, Any],
) -> str | None:
    """Return a system prompt string from systemInstruction (top-level key)."""
    si = raw_conversation.get("systemInstruction")

    if isinstance(si, str) and si.strip():
        return si.strip()

    if isinstance(si, dict):
        # May contain {"parts": [{"text": "..."}]} or be empty
        si_parts = si.get("parts")
        if isinstance(si_parts, list):
            texts: list[str] = []
            for part in si_parts:
                if isinstance(part, dict):
                    text = _string_or_none(part.get("text"))
                    if text:
                        texts.append(text)
            return "\n".join(texts) if texts else None
        # Empty dict (seen in real data) — no system prompt
        return None

    return None


def parse_gemini_export(path: Path) -> list[ConversationRecord]:
    """Parse a merged Gemini conversations.json into ConversationRecords."""
    report = ValidationReport(provider="gemini")

    with path.open("r", encoding="utf-8") as file_handle:
        raw_conversations = json.load(file_handle)

    if not isinstance(raw_conversations, list):
        report.record_warning("Expected a JSON array at top level")
        report.log()
        return []

    conversations: list[ConversationRecord] = []

    for raw_conversation in raw_conversations:
        if not isinstance(raw_conversation, dict):
            continue

        conversation_id = str(raw_conversation.get("id") or "").strip()
        if not conversation_id:
            continue

        title = str(raw_conversation.get("title") or "[Untitled]")
        created = _parse_unix_datetime(raw_conversation.get("create_time"))
        updated = _parse_unix_datetime(raw_conversation.get("update_time"), fallback=created)

        run_settings = raw_conversation.get("runSettings")
        model_name = _extract_gemini_model(run_settings)

        # Validate conversation-level keys
        report.check_keys(raw_conversation, _GEMINI_CONVERSATION_KEYS, "conversation")

        # Validate runSettings keys
        if isinstance(run_settings, dict):
            report.check_keys(run_settings, _GEMINI_RUN_SETTINGS_KEYS, "run_settings")

        # Extract chunks from chunkedPrompt (real structure) or top-level (test fixture)
        chunked_prompt = raw_conversation.get("chunkedPrompt")
        if isinstance(chunked_prompt, dict):
            report.check_keys(chunked_prompt, _GEMINI_CHUNKED_PROMPT_KEYS, "chunked_prompt")
            chunks = chunked_prompt.get("chunks") or []
        else:
            # Fallback: top-level "chunks" for legacy/test data
            chunks = raw_conversation.get("chunks") or []
        if not isinstance(chunks, list):
            chunks = []

        # Skip imagenPrompt-only conversations (image generation, no chunks)
        if not chunks and "imagenPrompt" in raw_conversation:
            continue

        messages: list[MessageRecord] = []

        # --- system message ---
        system_text = _extract_gemini_system_text(raw_conversation)
        if system_text:
            messages.append(MessageRecord(
                id=f"{conversation_id}-system",
                provider="gemini",
                role="system",
                created=created,
                updated=None,
                model=model_name,
                content=[ContentBlock(type="text", text=system_text)],
            ))

        # --- chunks → messages ---
        for chunk_index, chunk in enumerate(chunks):
            if not isinstance(chunk, dict):
                continue

            # Real data uses role: "user"/"model"; fallback to isUser for tests
            raw_role = _string_or_none(chunk.get("role"))
            if raw_role == "user":
                is_user = True
            elif raw_role == "model":
                is_user = False
            else:
                is_user = bool(chunk.get("isUser", False))

            role = "user" if is_user else "assistant"
            message_id = f"{conversation_id}-{chunk_index}"
            message_created = created + timedelta(seconds=chunk_index)

            content_blocks = _parse_gemini_chunk(chunk, report=report)
            if not content_blocks:
                continue

            messages.append(MessageRecord(
                id=message_id,
                provider="gemini",
                role=role,
                created=message_created,
                updated=None,
                model=model_name if not is_user else None,
                content=content_blocks,
            ))

        if messages:
            non_system = [m for m in messages if m.role != "system"]
            if non_system:
                created = min(created, non_system[0].created)
                updated = max(updated, non_system[-1].created)

        conversations.append(ConversationRecord(
            id=conversation_id,
            provider="gemini",
            title=title,
            created=created,
            updated=updated,
            messages=messages,
        ))

    report.log()
    return conversations


# ---------------------------------------------------------------------------
# Provider merge
# ---------------------------------------------------------------------------

def load_provider_conversations(
    *,
    chatgpt_path: Path | None,
    claude_path: Path | None,
    gemini_path: Path | None = None,
) -> list[ConversationRecord]:
    conversations: list[ConversationRecord] = []

    if chatgpt_path and chatgpt_path.exists():
        conversations.extend(parse_chatgpt_export(chatgpt_path))

    if claude_path and claude_path.exists():
        conversations.extend(parse_claude_export(claude_path))

    if gemini_path and gemini_path.exists():
        conversations.extend(parse_gemini_export(gemini_path))

    conversations.sort(key=lambda conversation: conversation.created, reverse=True)
    return conversations
