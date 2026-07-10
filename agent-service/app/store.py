from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from .models import ConversationState


class ConversationStore(Protocol):
    def exists(self, conversation_id: str) -> bool: ...

    def count(self) -> int: ...

    def get(self, conversation_id: str) -> ConversationState: ...

    def save(self, state: ConversationState) -> None: ...

    def list_recent(self, limit: int = 50) -> list[ConversationState]: ...


class InMemoryConversationStore:
    def __init__(self) -> None:
        self._items: dict[str, ConversationState] = {}

    def exists(self, conversation_id: str) -> bool:
        return conversation_id in self._items

    def count(self) -> int:
        return len(self._items)

    def get(self, conversation_id: str) -> ConversationState:
        if conversation_id not in self._items:
            self._items[conversation_id] = ConversationState(conversation_id=conversation_id)
        return self._items[conversation_id]

    def save(self, state: ConversationState) -> None:
        state.updated_at = datetime.now(timezone.utc).isoformat()
        self._items[state.conversation_id] = state

    def list_recent(self, limit: int = 50) -> list[ConversationState]:
        return sorted(self._items.values(), key=lambda item: item.updated_at, reverse=True)[:limit]


class SQLiteConversationStore:
    """Local optional persistence.

    The stored payload is redacted before serialization. This keeps the generated SQLite
    database safe to inspect locally and aligned with the public debug endpoint.
    """

    def __init__(self, path: str | Path = "runtime/state/autoseguro.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    conversation_id TEXT PRIMARY KEY,
                    updated_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )

    def exists(self, conversation_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM conversations WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
        return row is not None

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()
        return int(row[0] if row else 0)

    def get(self, conversation_id: str) -> ConversationState:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM conversations WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
        if not row:
            return ConversationState(conversation_id=conversation_id)
        return ConversationState.model_validate_json(row[0])

    def save(self, state: ConversationState) -> None:
        state.updated_at = datetime.now(timezone.utc).isoformat()
        safe_state = self._redacted_copy(state)
        payload = safe_state.model_dump_json()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO conversations (conversation_id, updated_at, payload)
                VALUES (?, ?, ?)
                ON CONFLICT(conversation_id) DO UPDATE SET
                    updated_at = excluded.updated_at,
                    payload = excluded.payload
                """,
                (safe_state.conversation_id, safe_state.updated_at, payload),
            )

    def list_recent(self, limit: int = 50) -> list[ConversationState]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM conversations ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [ConversationState.model_validate_json(row[0]) for row in rows]

    @staticmethod
    def _redacted_copy(state: ConversationState) -> ConversationState:
        safe = state.model_copy(deep=True)
        for message in safe.messages:
            message.content = message.redacted_content
        return safe


def build_conversation_store() -> ConversationStore:
    store_kind = os.getenv("AUTOSEGURO_STATE_STORE", "memory").strip().casefold()
    if store_kind == "sqlite":
        return SQLiteConversationStore(os.getenv("AUTOSEGURO_SQLITE_PATH", "runtime/state/autoseguro.db"))
    if store_kind != "memory":
        raise ValueError("AUTOSEGURO_STATE_STORE deve ser 'memory' ou 'sqlite'.")
    return InMemoryConversationStore()
