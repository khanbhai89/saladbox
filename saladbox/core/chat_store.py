"""Persistent SQLite storage for all chat messages across platforms."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default DB path
DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "chats.db"


class ChatStore:
    """SQLite-backed persistent storage for all conversations and messages.

    Supports use as a context manager for automatic cleanup:
        with ChatStore() as store:
            store.save_message(...)
    """

    def __init__(self, db_path: str | Path | None = None):
        self._db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._init_db()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def _init_db(self) -> None:
        """Initialize the database schema."""
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                platform TEXT NOT NULL DEFAULT 'cli',
                user_id TEXT,
                channel_id TEXT,
                title TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                metadata TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                platform TEXT NOT NULL DEFAULT 'cli',
                user_id TEXT,
                tool_name TEXT,
                tool_call_id TEXT,
                metadata TEXT DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            );

            CREATE INDEX IF NOT EXISTS idx_messages_conversation
                ON messages(conversation_id);
            CREATE INDEX IF NOT EXISTS idx_messages_created
                ON messages(created_at);
            CREATE INDEX IF NOT EXISTS idx_conversations_platform
                ON conversations(platform);
            CREATE INDEX IF NOT EXISTS idx_conversations_updated
                ON conversations(updated_at);
        """)
        self._conn.commit()
        logger.info(f"Chat store initialized at {self._db_path}")

    def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        platform: str = "cli",
        user_id: str | None = None,
        channel_id: str | None = None,
        tool_name: str | None = None,
        tool_call_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Save a message and ensure the conversation exists. Returns message ID."""
        if not self._conn:
            raise RuntimeError("ChatStore is closed")

        now = datetime.now(timezone.utc).isoformat()
        msg_id = str(uuid.uuid4())

        with self._lock:
            return self._save_message_locked(
                msg_id, conversation_id, role, content, platform,
                user_id, channel_id, tool_name, tool_call_id, metadata, now,
            )

    def _save_message_locked(
        self,
        msg_id: str,
        conversation_id: str,
        role: str,
        content: str,
        platform: str,
        user_id: str | None,
        channel_id: str | None,
        tool_name: str | None,
        tool_call_id: str | None,
        metadata: dict[str, Any] | None,
        now: str,
    ) -> str:
        """Thread-safe inner save (caller holds self._lock)."""
        # Upsert conversation
        self._conn.execute(
            """
            INSERT INTO conversations (id, platform, user_id, channel_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at
            """,
            (conversation_id, platform, user_id, channel_id, now, now),
        )

        # Insert message
        self._conn.execute(
            """
            INSERT INTO messages (id, conversation_id, role, content, platform, user_id,
                                  tool_name, tool_call_id, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                msg_id,
                conversation_id,
                role,
                content,
                platform,
                user_id,
                tool_name,
                tool_call_id,
                json.dumps(metadata or {}),
                now,
            ),
        )

        # Auto-generate conversation title from first user message
        if role == "user":
            row = self._conn.execute(
                "SELECT title FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if row and not row["title"]:
                title = content[:80].strip()
                if len(content) > 80:
                    title += "..."
                self._conn.execute(
                    "UPDATE conversations SET title = ? WHERE id = ?",
                    (title, conversation_id),
                )

        self._conn.commit()
        return msg_id

    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation and all its messages."""
        if not self._conn:
            return False
        with self._lock:
            self._conn.execute(
                "DELETE FROM messages WHERE conversation_id = ?", (conversation_id,)
            )
            result = self._conn.execute(
                "DELETE FROM conversations WHERE id = ?", (conversation_id,)
            )
            self._conn.commit()
            return result.rowcount > 0

    def get_conversations(
        self,
        platform: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Get conversations, optionally filtered by platform."""
        query = """
            SELECT c.*,
                   COUNT(m.id) as message_count,
                   (SELECT content FROM messages
                    WHERE conversation_id = c.id AND role = 'user'
                    ORDER BY created_at DESC LIMIT 1) as last_user_message,
                   (SELECT content FROM messages
                    WHERE conversation_id = c.id AND role = 'assistant'
                    ORDER BY created_at DESC LIMIT 1) as last_assistant_message
            FROM conversations c
            LEFT JOIN messages m ON m.conversation_id = c.id
        """
        params: list[Any] = []

        if platform:
            query += " WHERE c.platform = ?"
            params.append(platform)

        query += " GROUP BY c.id ORDER BY c.updated_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self._conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_messages(
        self,
        conversation_id: str,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Get messages for a conversation."""
        rows = self._conn.execute(
            """
            SELECT * FROM messages
            WHERE conversation_id = ?
            ORDER BY created_at ASC
            LIMIT ? OFFSET ?
            """,
            (conversation_id, limit, offset),
        ).fetchall()
        return [dict(row) for row in rows]

    def search_messages(
        self,
        query: str,
        platform: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Full-text search across all messages."""
        sql = """
            SELECT m.*, c.platform as conv_platform, c.title as conv_title
            FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            WHERE m.content LIKE ?
        """
        params: list[Any] = [f"%{query}%"]

        if platform:
            sql += " AND c.platform = ?"
            params.append(platform)

        sql += " ORDER BY m.created_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_stats(self) -> dict[str, Any]:
        """Get aggregate statistics for the dashboard."""
        stats: dict[str, Any] = {}

        # Total counts
        row = self._conn.execute(
            "SELECT COUNT(*) as count FROM conversations"
        ).fetchone()
        stats["total_conversations"] = row["count"]

        row = self._conn.execute(
            "SELECT COUNT(*) as count FROM messages"
        ).fetchone()
        stats["total_messages"] = row["count"]

        # Per-platform breakdown
        rows = self._conn.execute(
            """
            SELECT c.platform, COUNT(DISTINCT c.id) as conversations, COUNT(m.id) as messages
            FROM conversations c
            LEFT JOIN messages m ON m.conversation_id = c.id
            GROUP BY c.platform
            """
        ).fetchall()
        stats["platforms"] = [dict(r) for r in rows]

        # Messages per day (last 30 days)
        rows = self._conn.execute(
            """
            SELECT DATE(created_at) as date, COUNT(*) as count
            FROM messages
            WHERE created_at >= datetime('now', '-30 days')
            GROUP BY DATE(created_at)
            ORDER BY date ASC
            """
        ).fetchall()
        stats["messages_per_day"] = [dict(r) for r in rows]

        # Role breakdown
        rows = self._conn.execute(
            """
            SELECT role, COUNT(*) as count
            FROM messages
            GROUP BY role
            """
        ).fetchall()
        stats["roles"] = {r["role"]: r["count"] for r in rows}

        # Recent activity (last 7 days)
        rows = self._conn.execute(
            """
            SELECT c.platform, COUNT(m.id) as count
            FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            WHERE m.created_at >= datetime('now', '-7 days')
            GROUP BY c.platform
            """
        ).fetchall()
        stats["recent_activity"] = [dict(r) for r in rows]

        # Average messages per conversation
        row = self._conn.execute(
            """
            SELECT AVG(cnt) as avg_messages FROM (
                SELECT COUNT(*) as cnt FROM messages
                GROUP BY conversation_id
            )
            """
        ).fetchone()
        stats["avg_messages_per_conversation"] = round(row["avg_messages"] or 0, 1)

        return stats

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
