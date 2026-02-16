from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from openai import OpenAI

try:
    import faiss  # type: ignore
except Exception:  # pragma: no cover - import guard for environments without faiss
    faiss = None

from models import ConversationRecord

TYPE_CONVERSATION = "conversation"
TYPE_MESSAGE = "message"


@dataclass(slots=True)
class SemanticHit:
    provider: str
    embedding_id: str
    entry_type: str
    conversation_id: str
    item_id: str
    score: float


@dataclass(slots=True)
class ProviderEmbeddingIndex:
    provider: str
    ids: list[str]
    metadata: dict[str, dict[str, str]]
    index: Any


def create_openai_client(api_key: str, organization: str | None) -> OpenAI:
    if organization:
        return OpenAI(api_key=api_key, organization=organization)
    return OpenAI(api_key=api_key)


def _embedding_key(entry_type: str, entry_id: str) -> str:
    prefix = "c" if entry_type == TYPE_CONVERSATION else "m"
    return f"{prefix}:{entry_id}"


def _truncate_for_embedding(raw_text: str, max_chars: int = 16000) -> str:
    text = raw_text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def _ensure_schema(connection: sqlite3.Connection) -> None:
    cursor = connection.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS embeddings (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            conv_id TEXT NOT NULL,
            item_id TEXT NOT NULL,
            embedding BLOB NOT NULL
        )
        """
    )
    connection.commit()


def _load_embeddings(connection: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    cursor = connection.cursor()
    cursor.execute("SELECT id, type, conv_id, item_id, embedding FROM embeddings")
    rows = cursor.fetchall()
    embeddings: dict[str, dict[str, Any]] = {}
    for embedding_id, entry_type, conv_id, item_id, raw_embedding in rows:
        vector = np.frombuffer(raw_embedding, dtype=np.float32)
        embeddings[embedding_id] = {
            "type": entry_type,
            "conv_id": conv_id,
            "item_id": item_id,
            "embedding": vector,
        }
    return embeddings


def _save_embedding(
    connection: sqlite3.Connection,
    *,
    embedding_id: str,
    entry_type: str,
    conversation_id: str,
    item_id: str,
    vector: list[float],
) -> None:
    cursor = connection.cursor()
    vector_bytes = np.array(vector, dtype=np.float32).tobytes()
    cursor.execute(
        """
        REPLACE INTO embeddings (id, type, conv_id, item_id, embedding)
        VALUES (?, ?, ?, ?, ?)
        """,
        (embedding_id, entry_type, conversation_id, item_id, vector_bytes),
    )
    connection.commit()


def _embed_text(client: OpenAI, *, text: str, model: str) -> list[float]:
    response = client.embeddings.create(model=model, input=text)
    return list(response.data[0].embedding)


def build_provider_embedding_index(
    *,
    provider: str,
    conversations: list[ConversationRecord],
    db_path: Path,
    client: OpenAI,
    model: str,
) -> ProviderEmbeddingIndex | None:
    if faiss is None:
        return None

    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    try:
        _ensure_schema(connection)
        embeddings = _load_embeddings(connection)

        new_count = 0
        for conversation in conversations:
            if conversation.provider != provider:
                continue

            title_text = _truncate_for_embedding(conversation.title_str)
            conversation_key = _embedding_key(TYPE_CONVERSATION, conversation.id)
            if title_text and conversation_key not in embeddings:
                vector = _embed_text(client, text=title_text, model=model)
                _save_embedding(
                    connection,
                    embedding_id=conversation_key,
                    entry_type=TYPE_CONVERSATION,
                    conversation_id=conversation.id,
                    item_id=conversation.id,
                    vector=vector,
                )
                embeddings[conversation_key] = {
                    "type": TYPE_CONVERSATION,
                    "conv_id": conversation.id,
                    "item_id": conversation.id,
                    "embedding": np.array(vector, dtype=np.float32),
                }
                new_count += 1

            for message in conversation.messages:
                message_text = _truncate_for_embedding(message.text())
                if not message_text:
                    continue
                message_key = _embedding_key(TYPE_MESSAGE, message.id)
                if message_key in embeddings:
                    continue

                vector = _embed_text(client, text=message_text, model=model)
                _save_embedding(
                    connection,
                    embedding_id=message_key,
                    entry_type=TYPE_MESSAGE,
                    conversation_id=conversation.id,
                    item_id=message.id,
                    vector=vector,
                )
                embeddings[message_key] = {
                    "type": TYPE_MESSAGE,
                    "conv_id": conversation.id,
                    "item_id": message.id,
                    "embedding": np.array(vector, dtype=np.float32),
                }
                new_count += 1

        if new_count:
            print(f"-- [{provider}] created {new_count} new embeddings")

        if not embeddings:
            return None

        ids = list(embeddings.keys())
        vectors = np.array([embeddings[item_id]["embedding"] for item_id in ids], dtype=np.float32)
        index = faiss.IndexFlatL2(vectors.shape[1])
        index.add(vectors)
        metadata = {
            item_id: {
                "type": str(embeddings[item_id]["type"]),
                "conv_id": str(embeddings[item_id]["conv_id"]),
                "item_id": str(embeddings[item_id]["item_id"]),
            }
            for item_id in ids
        }
        return ProviderEmbeddingIndex(provider=provider, ids=ids, metadata=metadata, index=index)
    finally:
        connection.close()


def semantic_search(
    *,
    query: str,
    indices: list[ProviderEmbeddingIndex],
    client: OpenAI,
    model: str,
    top_n: int = 10,
) -> list[SemanticHit]:
    if faiss is None or not indices:
        return []

    query_vector = np.array(_embed_text(client, text=query, model=model), dtype=np.float32).reshape(1, -1)
    hits: list[SemanticHit] = []

    for provider_index in indices:
        if provider_index.index is None or provider_index.index.ntotal == 0:
            continue

        result_count = min(top_n, provider_index.index.ntotal)
        distances, indices_result = provider_index.index.search(query_vector, result_count)
        for distance, idx in zip(distances[0], indices_result[0]):
            embedding_id = provider_index.ids[idx]
            metadata = provider_index.metadata[embedding_id]
            hits.append(
                SemanticHit(
                    provider=provider_index.provider,
                    embedding_id=embedding_id,
                    entry_type=metadata["type"],
                    conversation_id=metadata["conv_id"],
                    item_id=metadata["item_id"],
                    score=float(distance),
                )
            )

    hits.sort(key=lambda hit: hit.score)
    return hits[:top_n]
