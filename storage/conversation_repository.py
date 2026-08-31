"""保存用户会话与消息历史的 SQLite 仓储。"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from utils.path_tool import get_abs_path


@dataclass(frozen=True)
class ConversationSummary:
    conversation_id: str
    title: str
    preview: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ConversationMessage:
    message_id: str
    role: str
    content: str
    traces: list[str]
    agent: str | None
    created_at: str


class ConversationRepository:
    """通过 user_id 约束所有会话读写，避免跨账户访问。"""

    def __init__(self, database_path: str | Path | None = None):
        self.database_path = Path(database_path or get_abs_path("data/support.db"))
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    conversation_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_conversations_user_updated
                ON conversations(user_id, updated_at DESC)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    message_id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    message_order INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    traces_json TEXT NOT NULL DEFAULT '[]',
                    agent TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(conversation_id, message_order),
                    FOREIGN KEY(conversation_id) REFERENCES conversations(conversation_id)
                )
                """
            )

    def create_conversation(self, user_id: str, title: str) -> ConversationSummary:
        conversation_id = uuid.uuid4().hex
        normalized_title = " ".join(title.split()).strip()[:50] or "新会话"
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            user_exists = connection.execute(
                "SELECT 1 FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            if user_exists is None:
                raise ValueError(f"用户不存在：{user_id}")
            connection.execute(
                """
                INSERT INTO conversations(conversation_id, user_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (conversation_id, user_id, normalized_title, now, now),
            )
        return ConversationSummary(
            conversation_id=conversation_id,
            title=normalized_title,
            preview="",
            created_at=now,
            updated_at=now,
        )

    def list_conversations(self, user_id: str) -> list[ConversationSummary]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    c.conversation_id,
                    c.title,
                    COALESCE((
                        SELECT m.content FROM conversation_messages AS m
                        WHERE m.conversation_id = c.conversation_id
                        ORDER BY m.message_order DESC LIMIT 1
                    ), '') AS preview,
                    c.created_at,
                    c.updated_at
                FROM conversations AS c
                WHERE c.user_id = ?
                ORDER BY c.updated_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [ConversationSummary(**dict(row)) for row in rows]

    def get_conversation(
        self,
        user_id: str,
        conversation_id: str,
    ) -> tuple[ConversationSummary, list[ConversationMessage]] | None:
        with self._connect() as connection:
            conversation = connection.execute(
                """
                SELECT conversation_id, title, '' AS preview, created_at, updated_at
                FROM conversations WHERE conversation_id = ? AND user_id = ?
                """,
                (conversation_id, user_id),
            ).fetchone()
            if conversation is None:
                return None
            message_rows = connection.execute(
                """
                SELECT message_id, role, content, traces_json, agent, created_at
                FROM conversation_messages
                WHERE conversation_id = ? ORDER BY message_order ASC
                """,
                (conversation_id,),
            ).fetchall()

        messages = [
            ConversationMessage(
                message_id=row["message_id"],
                role=row["role"],
                content=row["content"],
                traces=json.loads(row["traces_json"]),
                agent=row["agent"],
                created_at=row["created_at"],
            )
            for row in message_rows
        ]
        return ConversationSummary(**dict(conversation)), messages

    def add_message(
        self,
        user_id: str,
        conversation_id: str,
        *,
        role: str,
        content: str,
        traces: list[str] | None = None,
        agent: str | None = None,
    ) -> ConversationMessage:
        if role not in {"user", "assistant"}:
            raise ValueError(f"不支持的消息角色：{role}")
        message_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            conversation = connection.execute(
                """
                SELECT 1 FROM conversations WHERE conversation_id = ? AND user_id = ?
                """,
                (conversation_id, user_id),
            ).fetchone()
            if conversation is None:
                raise PermissionError("会话不存在或无权访问")
            next_order = connection.execute(
                """
                SELECT COALESCE(MAX(message_order), 0) + 1
                FROM conversation_messages WHERE conversation_id = ?
                """,
                (conversation_id,),
            ).fetchone()[0]
            connection.execute(
                """
                INSERT INTO conversation_messages(
                    message_id, conversation_id, message_order, role,
                    content, traces_json, agent, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    conversation_id,
                    next_order,
                    role,
                    content,
                    json.dumps(traces or [], ensure_ascii=False),
                    agent,
                    now,
                ),
            )
            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE conversation_id = ?",
                (now, conversation_id),
            )
        return ConversationMessage(
            message_id=message_id,
            role=role,
            content=content,
            traces=traces or [],
            agent=agent,
            created_at=now,
        )

    def delete_conversation(self, user_id: str, conversation_id: str) -> bool:
        with self._connect() as connection:
            owned = connection.execute(
                """
                SELECT 1 FROM conversations WHERE conversation_id = ? AND user_id = ?
                """,
                (conversation_id, user_id),
            ).fetchone()
            if owned is None:
                return False
            connection.execute(
                "DELETE FROM conversation_messages WHERE conversation_id = ?",
                (conversation_id,),
            )
            connection.execute(
                "DELETE FROM conversations WHERE conversation_id = ? AND user_id = ?",
                (conversation_id, user_id),
            )
        return True
