from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

from markdown import markdown

from chat_history.config import Settings
from chat_history.embeddings import (
    TYPE_CONVERSATION,
    ProviderEmbeddingIndex,
    build_provider_embedding_index,
    create_openai_client,
    semantic_search,
)
from chat_history.models import (
    ATTACHMENT_BLOCK_TYPES,
    THINKING_BLOCK_TYPES,
    TOOL_BLOCK_TYPES,
    ConversationRecord,
    MessageRecord,
)
from chat_history.parsers import load_provider_conversations
from chat_history.storage import SettingsStore
from chat_history.utils import human_readable_time, time_group


class ChatHistoryService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.settings_store: SettingsStore | None = None
        self.conversations: list[ConversationRecord] = []
        self._conversation_map: dict[tuple[str, str], ConversationRecord] = {}
        self._message_map: dict[tuple[str, str], tuple[ConversationRecord, MessageRecord]] = {}
        self._openai_client = None
        self._embedding_indices: list[ProviderEmbeddingIndex] = []

    def load(self, *, build_embeddings: bool = True) -> None:
        self._ensure_dirs()
        self.settings_store = SettingsStore(self.settings.settings_db_path)

        self.conversations = load_provider_conversations(
            chatgpt_path=self.settings.chatgpt_path,
            claude_path=self.settings.claude_path,
        )
        self._conversation_map = {
            (conversation.provider, conversation.id): conversation
            for conversation in self.conversations
        }
        self._message_map = {}
        for conversation in self.conversations:
            for message in conversation.messages:
                self._message_map[(conversation.provider, message.id)] = (conversation, message)

        if self.settings.openai_enabled and build_embeddings:
            self._openai_client = create_openai_client(
                self.settings.openai_api_key or "",
                self.settings.openai_organization,
            )
            self._embedding_indices = self._build_embedding_indices()
        else:
            self._openai_client = None
            self._embedding_indices = []

        by_provider = defaultdict(int)
        for conversation in self.conversations:
            by_provider[conversation.provider] += 1
        print(f"-- Loaded {len(self.conversations)} conversations: {dict(by_provider)}")

    def _ensure_dirs(self) -> None:
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.settings.export_dir.mkdir(parents=True, exist_ok=True)
        (self.settings.data_dir / "chatgpt").mkdir(parents=True, exist_ok=True)
        (self.settings.data_dir / "claude").mkdir(parents=True, exist_ok=True)
        self.settings.settings_db_path.parent.mkdir(parents=True, exist_ok=True)

    def _build_embedding_indices(self) -> list[ProviderEmbeddingIndex]:
        if not self._openai_client:
            return []

        indices: list[ProviderEmbeddingIndex] = []
        for provider in ("chatgpt", "claude"):
            provider_conversations = [
                conversation
                for conversation in self.conversations
                if conversation.provider == provider
            ]
            if not provider_conversations:
                continue

            index = build_provider_embedding_index(
                provider=provider,
                conversations=provider_conversations,
                db_path=self.settings.provider_embeddings_db_path(provider),
                client=self._openai_client,
                model=self.settings.embedding_model,
            )
            if index:
                indices.append(index)
        return indices

    def _require_settings_store(self) -> SettingsStore:
        if self.settings_store is None:
            raise RuntimeError("Settings store is not initialized")
        return self.settings_store

    def _favorite_keys(self) -> set[tuple[str, str]]:
        return self._require_settings_store().favorite_keys()

    def list_conversations(self) -> list[dict[str, Any]]:
        favorite_keys = self._favorite_keys()
        return [
            {
                "group": time_group(conversation.created),
                "id": conversation.id,
                "provider": conversation.provider,
                "title": conversation.title_str,
                "created": conversation.created_str,
                "total_length": human_readable_time(conversation.total_length_seconds, short=True),
                "is_favorite": (conversation.provider, conversation.id) in favorite_keys,
                "open_url": conversation.open_url,
            }
            for conversation in self.conversations
        ]

    def get_conversation(self, provider: str, conversation_id: str) -> ConversationRecord | None:
        return self._conversation_map.get((provider, conversation_id))

    def _serialize_message_blocks(self, message: MessageRecord) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        for block in message.content:
            text = block.text.strip()
            if not text:
                continue
            blocks.append(
                {
                    "type": block.type,
                    "text": text,
                    "data": block.data,
                }
            )
        return blocks

    def get_messages(self, provider: str, conversation_id: str) -> dict[str, Any] | None:
        conversation = self.get_conversation(provider, conversation_id)
        if not conversation:
            return None

        payload_messages: list[dict[str, Any]] = []
        previous_created: datetime | None = None

        for message in sorted(conversation.messages, key=lambda item: item.created):
            if previous_created:
                delta_seconds = (message.created - previous_created).total_seconds()
                if delta_seconds >= 3600:
                    payload_messages.append(
                        {
                            "text": f"{human_readable_time(delta_seconds)} passed",
                            "role": "internal",
                            "blocks": [],
                        }
                    )

            blocks = self._serialize_message_blocks(message)
            payload_messages.append(
                {
                    "text": message.text(),
                    "blocks": blocks,
                    "role": message.role,
                    "created": message.created_str,
                }
            )
            previous_created = message.created

        return {
            "conversation_id": conversation.id,
            "provider": conversation.provider,
            "open_url": conversation.open_url,
            "messages": payload_messages,
        }

    def get_activity(self) -> dict[str, Any]:
        activity_by_day: dict[str, dict[str, Any]] = {}
        provider_totals = defaultdict(int)

        for conversation in self.conversations:
            provider = conversation.provider
            for message in conversation.messages:
                day = str(message.created.date())
                day_entry = activity_by_day.setdefault(day, {"total": 0, "providers": {}})
                day_entry["total"] += 1
                day_entry["providers"][provider] = day_entry["providers"].get(provider, 0) + 1
                provider_totals[provider] += 1

        sorted_days = {day: activity_by_day[day] for day in sorted(activity_by_day.keys())}
        providers = sorted(provider_totals.keys())

        return {
            "providers": providers,
            "provider_totals": {provider: provider_totals[provider] for provider in providers},
            "days": sorted_days,
        }

    def get_activity_day(
        self,
        *,
        day: str,
        provider: str | None = None,
    ) -> dict[str, Any]:
        conversations: list[dict[str, Any]] = []
        total_messages = 0

        for conversation in self.conversations:
            if provider and conversation.provider != provider:
                continue

            message_count = sum(
                1
                for message in conversation.messages
                if str(message.created.date()) == day
            )
            if message_count == 0:
                continue

            conversations.append(
                {
                    "provider": conversation.provider,
                    "id": conversation.id,
                    "message_count": message_count,
                }
            )
            total_messages += message_count

        return {
            "date": day,
            "provider": provider,
            "conversations": conversations,
            "total_messages": total_messages,
        }

    @staticmethod
    def _format_stats_for_conversations(
        conversations: list[ConversationRecord],
    ) -> dict[str, str]:
        message_timestamps = [
            message.created
            for conversation in conversations
            for message in conversation.messages
        ]
        message_count = len(message_timestamps)

        stats = {
            "Conversations": str(len(conversations)),
            "Messages": str(message_count),
            "Chat backup age": "N/A",
            "Last chat message": "N/A",
            "First chat message": "N/A",
        }
        if not message_timestamps:
            return stats

        first_message = min(message_timestamps)
        last_message = max(message_timestamps)
        stats["Chat backup age"] = human_readable_time(
            (datetime.now(timezone.utc) - last_message).total_seconds()
        )
        stats["Last chat message"] = last_message.astimezone().strftime("%Y-%m-%d")
        stats["First chat message"] = first_message.astimezone().strftime("%Y-%m-%d")
        return stats

    def get_statistics(self) -> dict[str, Any]:
        provider_groups: dict[str, list[ConversationRecord]] = defaultdict(list)
        for conversation in self.conversations:
            provider_groups[conversation.provider].append(conversation)

        summary = self._format_stats_for_conversations(self.conversations)
        summary["Providers"] = (
            ", ".join(
                f"{provider}: {len(provider_groups[provider])}"
                for provider in sorted(provider_groups.keys())
            )
            if provider_groups
            else "N/A"
        )

        by_provider = {
            provider: self._format_stats_for_conversations(conversations)
            for provider, conversations in sorted(provider_groups.items())
        }
        return {
            "summary": summary,
            "by_provider": by_provider,
        }

    def get_token_statistics(self) -> list[dict[str, Any]]:
        by_provider_model: dict[tuple[str, str], dict[str, int]] = {}

        for conversation in self.conversations:
            for message in conversation.messages:
                token_count = message.count_tokens()
                if token_count == 0:
                    continue
                model = message.model or "unknown"
                key = (conversation.provider, model)
                if key not in by_provider_model:
                    by_provider_model[key] = {"input_tokens": 0, "output_tokens": 0}
                if message.role == "user":
                    by_provider_model[key]["input_tokens"] += token_count
                else:
                    by_provider_model[key]["output_tokens"] += token_count

        rows = []
        for (provider, model), stats in by_provider_model.items():
            total_tokens = stats["input_tokens"] + stats["output_tokens"]
            rows.append(
                {
                    "provider": provider,
                    "model": model,
                    "input_tokens": stats["input_tokens"],
                    "output_tokens": stats["output_tokens"],
                    "total_tokens": total_tokens,
                }
            )
        rows.sort(key=lambda item: (item["provider"], -item["total_tokens"], item["model"]))
        return rows

    def search(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        query = query.strip()
        if not query:
            return []

        exact_query = None
        if query.startswith('"') and query.endswith('"') and len(query) > 1:
            exact_query = query[1:-1].strip().lower()

        if exact_query is None and self._openai_client and self._embedding_indices:
            try:
                semantic_results = self._semantic_search(query, limit=limit)
                if semantic_results:
                    return semantic_results
            except Exception as exc:
                print(f"-- Semantic search failed, falling back to strict search: {exc}")

        strict_query = exact_query if exact_query is not None else query.lower()
        return self._strict_search(strict_query, limit=limit)

    def _build_search_result(
        self,
        *,
        result_type: str,
        conversation: ConversationRecord,
        message: MessageRecord | None,
    ) -> dict[str, Any]:
        text_source = message.text() if message else conversation.title_str
        created_str = message.created_str if message else conversation.created_str
        role = message.role if message else "conversation"
        return {
            "type": result_type,
            "provider": conversation.provider,
            "id": conversation.id,
            "title": conversation.title_str,
            "text": markdown(text_source, extensions=["fenced_code"]),
            "role": role,
            "created": created_str,
            "internal_url": f"/?{urlencode({'provider': conversation.provider, 'conv_id': conversation.id})}",
            "open_url": conversation.open_url,
        }

    def _strict_search(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        query_lower = query.lower()

        for conversation in self.conversations:
            if query_lower in conversation.title_str.lower():
                preview_message = conversation.messages[0] if conversation.messages else None
                results.append(
                    self._build_search_result(
                        result_type=TYPE_CONVERSATION,
                        conversation=conversation,
                        message=preview_message,
                    )
                )

            for message in conversation.messages:
                if query_lower in message.text().lower():
                    results.append(
                        self._build_search_result(
                            result_type="message",
                            conversation=conversation,
                            message=message,
                        )
                    )
                if len(results) >= limit:
                    return results

            if len(results) >= limit:
                return results

        return results

    def _semantic_search(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        if not self._openai_client:
            return []

        hits = semantic_search(
            query=query,
            indices=self._embedding_indices,
            client=self._openai_client,
            model=self.settings.embedding_model,
            top_n=limit,
        )

        results: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for hit in hits:
            dedupe_key = (hit.provider, hit.entry_type, hit.item_id)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            conversation = self.get_conversation(hit.provider, hit.conversation_id)
            if not conversation:
                continue

            if hit.entry_type == TYPE_CONVERSATION:
                preview_message = conversation.messages[0] if conversation.messages else None
                results.append(
                    self._build_search_result(
                        result_type=TYPE_CONVERSATION,
                        conversation=conversation,
                        message=preview_message,
                    )
                )
                continue

            message_tuple = self._message_map.get((hit.provider, hit.item_id))
            if not message_tuple:
                continue

            _, message = message_tuple
            results.append(
                self._build_search_result(
                    result_type="message",
                    conversation=conversation,
                    message=message,
                )
            )

            if len(results) >= limit:
                break

        return results

    def toggle_favorite(self, provider: str, conversation_id: str) -> bool:
        return self._require_settings_store().toggle_favorite(provider, conversation_id)
