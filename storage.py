from __future__ import annotations

import sqlite3
from pathlib import Path


class SettingsStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='favorites'"
            )
            table_exists = cursor.fetchone() is not None

            if table_exists:
                cursor.execute("PRAGMA table_info(favorites)")
                columns = [row[1] for row in cursor.fetchall()]
                expected_columns = {"provider", "conversation_id", "is_favorite"}
                if set(columns) != expected_columns:
                    # Direct cutover by design: no migration of legacy favorites.
                    cursor.execute("DROP TABLE favorites")

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS favorites (
                    provider TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    is_favorite INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY (provider, conversation_id)
                )
                """
            )
            connection.commit()

    def favorite_keys(self) -> set[tuple[str, str]]:
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT provider, conversation_id FROM favorites WHERE is_favorite = 1"
            )
            rows = cursor.fetchall()
        return {(provider, conversation_id) for provider, conversation_id in rows}

    def toggle_favorite(self, provider: str, conversation_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT is_favorite
                FROM favorites
                WHERE provider = ? AND conversation_id = ?
                """,
                (provider, conversation_id),
            )
            row = cursor.fetchone()

            if row is None:
                cursor.execute(
                    """
                    INSERT INTO favorites (provider, conversation_id, is_favorite)
                    VALUES (?, ?, 1)
                    """,
                    (provider, conversation_id),
                )
                is_favorite = True
            else:
                is_favorite = not bool(row[0])
                cursor.execute(
                    """
                    UPDATE favorites
                    SET is_favorite = ?
                    WHERE provider = ? AND conversation_id = ?
                    """,
                    (1 if is_favorite else 0, provider, conversation_id),
                )

            connection.commit()
        return is_favorite
