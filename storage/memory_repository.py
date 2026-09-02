"""管理工作记忆、事件记忆及其生命周期。"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from utils.path_tool import get_abs_path


@dataclass(frozen=True)
class WorkingMemory:
    summary: str
    recent_messages: list[dict[str, str]]
    summarized_message_count: int


@dataclass(frozen=True)
class MemoryItem:
    memory_id: str
    user_id: str
    device_id: str | None
    conversation_id: str | None
    memory_type: str
    memory_key: str
    agent_name: str
    skill_id: str
    content: str
    confidence: float
    sensitivity: str
    version: int
    status: str
    created_at: str
    updated_at: str
    last_accessed_at: str | None
    expires_at: str | None


class MemoryRepository:
    """以 SQLite 为事实源，按用户和设备隔离可供模型使用的记忆。"""

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
                CREATE TABLE IF NOT EXISTS conversation_memory_summaries (
                    conversation_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    summarized_message_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_items (
                    memory_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    device_id TEXT NOT NULL DEFAULT '',
                    conversation_id TEXT,
                    memory_type TEXT NOT NULL,
                    memory_key TEXT NOT NULL,
                    agent_name TEXT NOT NULL DEFAULT '',
                    skill_id TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL,
                    source_message_ids_json TEXT NOT NULL DEFAULT '[]',
                    confidence REAL NOT NULL DEFAULT 1.0,
                    sensitivity TEXT NOT NULL DEFAULT 'normal',
                    version INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_accessed_at TEXT,
                    expires_at TEXT,
                    supersedes_id TEXT,
                    UNIQUE(user_id, device_id, memory_type, memory_key)
                )
                """
            )
            self._ensure_column(connection, "memory_items", "agent_name", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "memory_items", "skill_id", "TEXT NOT NULL DEFAULT ''")
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memory_items_lookup
                ON memory_items(user_id, device_id, memory_type, status, updated_at DESC)
                """
            )

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        table_name: str,
        column_name: str,
        declaration: str,
    ) -> None:
        columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name not in columns:
            connection.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {declaration}"
            )

    def get_working_context(
        self,
        user_id: str,
        conversation_id: str,
        *,
        recent_limit: int = 8,
    ) -> WorkingMemory:
        with self._connect() as connection:
            owned = connection.execute(
                """
                SELECT 1 FROM conversations
                WHERE conversation_id = ? AND user_id = ?
                """,
                (conversation_id, user_id),
            ).fetchone()
            if owned is None:
                raise PermissionError("会话不存在或无权访问")
            summary_row = connection.execute(
                """
                SELECT summary, summarized_message_count
                FROM conversation_memory_summaries
                WHERE conversation_id = ? AND user_id = ?
                """,
                (conversation_id, user_id),
            ).fetchone()
            rows = connection.execute(
                """
                SELECT role, content FROM conversation_messages
                WHERE conversation_id = ?
                ORDER BY message_order DESC LIMIT ?
                """,
                (conversation_id, max(0, recent_limit)),
            ).fetchall()

        recent_messages = [dict(row) for row in reversed(rows)]
        return WorkingMemory(
            summary=summary_row["summary"] if summary_row else "",
            recent_messages=recent_messages,
            summarized_message_count=(
                summary_row["summarized_message_count"] if summary_row else 0
            ),
        )

    def refresh_conversation_summary(
        self,
        user_id: str,
        conversation_id: str,
        *,
        retain_recent: int = 8,
        max_chars: int = 2000,
    ) -> WorkingMemory:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT m.role, m.content
                FROM conversation_messages AS m
                JOIN conversations AS c ON c.conversation_id = m.conversation_id
                WHERE m.conversation_id = ? AND c.user_id = ?
                ORDER BY m.message_order ASC
                """,
                (conversation_id, user_id),
            ).fetchall()
            if not rows and connection.execute(
                "SELECT 1 FROM conversations WHERE conversation_id = ? AND user_id = ?",
                (conversation_id, user_id),
            ).fetchone() is None:
                raise PermissionError("会话不存在或无权访问")

            split_at = max(0, len(rows) - max(0, retain_recent))
            older_rows = rows[:split_at]
            summary_lines = [
                f"{'用户' if row['role'] == 'user' else '客服'}：{row['content'].strip()}"
                for row in older_rows
                if row["content"].strip()
            ]
            summary = "\n".join(summary_lines)
            if len(summary) > max_chars:
                summary = "…" + summary[-max_chars:]
            now = datetime.now(timezone.utc).isoformat()
            connection.execute(
                """
                INSERT INTO conversation_memory_summaries(
                    conversation_id, user_id, summary,
                    summarized_message_count, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(conversation_id) DO UPDATE SET
                    user_id = excluded.user_id,
                    summary = excluded.summary,
                    summarized_message_count = excluded.summarized_message_count,
                    updated_at = excluded.updated_at
                """,
                (conversation_id, user_id, summary, len(older_rows), now),
            )

        return self.get_working_context(
            user_id,
            conversation_id,
            recent_limit=retain_recent,
        )

    def upsert_fault_episode(
        self,
        user_id: str,
        *,
        query: str,
        answer: str,
        device_id: str | None = None,
        conversation_id: str | None = None,
        source_message_ids: list[str] | None = None,
        ttl_days: int = 180,
    ) -> MemoryItem:
        normalized_query = " ".join(query.lower().split())
        memory_key = hashlib.sha256(normalized_query.encode("utf-8")).hexdigest()[:24]
        normalized_device_id = device_id or ""
        content = f"故障描述：{query.strip()}\n处理结果：{answer.strip()}"
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()
        expires_at = (now_dt + timedelta(days=ttl_days)).isoformat()
        source_json = json.dumps(source_message_ids or [], ensure_ascii=False)

        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT memory_id, version, created_at FROM memory_items
                WHERE user_id = ? AND device_id = ?
                  AND memory_type = 'episodic' AND memory_key = ?
                """,
                (user_id, normalized_device_id, memory_key),
            ).fetchone()
            if existing:
                memory_id = existing["memory_id"]
                version = existing["version"] + 1
                created_at = existing["created_at"]
                connection.execute(
                    """
                    UPDATE memory_items SET
                        conversation_id = ?, content = ?, source_message_ids_json = ?,
                        confidence = 1.0, version = ?, status = 'active',
                        agent_name = 'diagnosis_agent', skill_id = 'fault_triage',
                        updated_at = ?, last_accessed_at = NULL, expires_at = ?
                    WHERE memory_id = ?
                    """,
                    (
                        conversation_id,
                        content,
                        source_json,
                        version,
                        now,
                        expires_at,
                        memory_id,
                    ),
                )
            else:
                memory_id = uuid.uuid4().hex
                version = 1
                created_at = now
                connection.execute(
                    """
                    INSERT INTO memory_items(
                        memory_id, user_id, device_id, conversation_id,
                        memory_type, memory_key, agent_name, skill_id,
                        content, source_message_ids_json,
                        confidence, sensitivity, version, status,
                        created_at, updated_at, expires_at
                    ) VALUES (?, ?, ?, ?, 'episodic', ?, 'diagnosis_agent',
                              'fault_triage', ?, ?, 1.0, 'normal',
                              ?, 'active', ?, ?, ?)
                    """,
                    (
                        memory_id,
                        user_id,
                        normalized_device_id,
                        conversation_id,
                        memory_key,
                        content,
                        source_json,
                        version,
                        created_at,
                        now,
                        expires_at,
                    ),
                )

        return MemoryItem(
            memory_id=memory_id,
            user_id=user_id,
            device_id=device_id,
            conversation_id=conversation_id,
            memory_type="episodic",
            memory_key=memory_key,
            agent_name="diagnosis_agent",
            skill_id="fault_triage",
            content=content,
            confidence=1.0,
            sensitivity="normal",
            version=version,
            status="active",
            created_at=created_at,
            updated_at=now,
            last_accessed_at=None,
            expires_at=expires_at,
        )

    def upsert_profile_fact(
        self,
        user_id: str,
        *,
        profile_key: str,
        content: str,
        source_message_ids: list[str] | None = None,
        confidence: float = 0.9,
    ) -> MemoryItem:
        now = datetime.now(timezone.utc).isoformat()
        source_json = json.dumps(source_message_ids or [], ensure_ascii=False)
        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT memory_id, version, created_at FROM memory_items
                WHERE user_id = ? AND device_id = ''
                  AND memory_type = 'profile' AND memory_key = ?
                """,
                (user_id, profile_key),
            ).fetchone()
            if existing:
                memory_id = existing["memory_id"]
                version = existing["version"] + 1
                created_at = existing["created_at"]
                connection.execute(
                    """
                    UPDATE memory_items SET
                        content = ?, source_message_ids_json = ?, confidence = ?,
                        version = ?, status = 'active', updated_at = ?,
                        last_accessed_at = NULL, expires_at = NULL
                    WHERE memory_id = ?
                    """,
                    (content, source_json, confidence, version, now, memory_id),
                )
            else:
                memory_id = uuid.uuid4().hex
                version = 1
                created_at = now
                connection.execute(
                    """
                    INSERT INTO memory_items(
                        memory_id, user_id, device_id, memory_type, memory_key,
                        agent_name, skill_id, content, source_message_ids_json,
                        confidence, sensitivity, version, status, created_at, updated_at
                    ) VALUES (?, ?, '', 'profile', ?, '', '', ?, ?, ?, 'normal',
                              ?, 'active', ?, ?)
                    """,
                    (
                        memory_id,
                        user_id,
                        profile_key,
                        content,
                        source_json,
                        confidence,
                        version,
                        created_at,
                        now,
                    ),
                )
        return MemoryItem(
            memory_id=memory_id,
            user_id=user_id,
            device_id=None,
            conversation_id=None,
            memory_type="profile",
            memory_key=profile_key,
            agent_name="",
            skill_id="",
            content=content,
            confidence=confidence,
            sensitivity="normal",
            version=version,
            status="active",
            created_at=created_at,
            updated_at=now,
            last_accessed_at=None,
            expires_at=None,
        )

    def list_active_memories(
        self,
        user_id: str,
        *,
        device_id: str | None = None,
        memory_type: str | None = None,
        limit: int = 3,
    ) -> list[MemoryItem]:
        self.expire_due_memories()
        conditions = ["user_id = ?", "status = 'active'"]
        parameters: list[object] = [user_id]
        if device_id is not None:
            conditions.append("device_id IN (?, '')")
            parameters.append(device_id)
        if memory_type is not None:
            conditions.append("memory_type = ?")
            parameters.append(memory_type)
        parameters.append(max(0, limit))

        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT memory_id, user_id, device_id, conversation_id,
                       memory_type, memory_key, agent_name, skill_id,
                       content, confidence, sensitivity,
                       version, status, created_at, updated_at,
                       last_accessed_at, expires_at
                FROM memory_items
                WHERE {' AND '.join(conditions)}
                ORDER BY updated_at DESC LIMIT ?
                """,
                parameters,
            ).fetchall()
            now = datetime.now(timezone.utc).isoformat()
            if rows:
                connection.executemany(
                    "UPDATE memory_items SET last_accessed_at = ? WHERE memory_id = ?",
                    [(now, row["memory_id"]) for row in rows],
                )

        return [self._row_to_memory(row, last_accessed_at=now) for row in rows]

    def update_memory_content(
        self,
        user_id: str,
        memory_id: str,
        content: str,
    ) -> MemoryItem | None:
        normalized_content = " ".join(content.split()).strip()
        if not normalized_content:
            raise ValueError("记忆内容不能为空")
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE memory_items SET content = ?, version = version + 1,
                    updated_at = ?, status = 'active'
                WHERE memory_id = ? AND user_id = ? AND status = 'active'
                """,
                (normalized_content, now, memory_id, user_id),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                """
                SELECT memory_id, user_id, device_id, conversation_id,
                       memory_type, memory_key, agent_name, skill_id,
                       content, confidence, sensitivity, version, status,
                       created_at, updated_at, last_accessed_at, expires_at
                FROM memory_items WHERE memory_id = ?
                """,
                (memory_id,),
            ).fetchone()
        return self._row_to_memory(row)

    def compact_memories(self, *, max_events_per_scope: int = 20) -> int:
        self.expire_due_memories()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT memory_id, user_id, device_id, agent_name, skill_id
                FROM memory_items
                WHERE memory_type = 'episodic' AND status = 'active'
                ORDER BY updated_at DESC
                """
            ).fetchall()
            scope_counts: dict[tuple[str, str, str, str], int] = {}
            superseded_ids: list[str] = []
            for row in rows:
                scope = (
                    row["user_id"],
                    row["device_id"],
                    row["agent_name"],
                    row["skill_id"],
                )
                scope_counts[scope] = scope_counts.get(scope, 0) + 1
                if scope_counts[scope] > max_events_per_scope:
                    superseded_ids.append(row["memory_id"])
            now = datetime.now(timezone.utc).isoformat()
            if superseded_ids:
                connection.executemany(
                    """
                    UPDATE memory_items SET status = 'superseded', updated_at = ?
                    WHERE memory_id = ?
                    """,
                    [(now, memory_id) for memory_id in superseded_ids],
                )
        return len(superseded_ids)

    def expire_due_memories(self, now: datetime | None = None) -> int:
        current = (now or datetime.now(timezone.utc)).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE memory_items SET status = 'expired', updated_at = ?
                WHERE status = 'active' AND expires_at IS NOT NULL AND expires_at <= ?
                """,
                (current, current),
            )
        return cursor.rowcount

    def delete_conversation_memory(self, user_id: str, conversation_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM conversation_memory_summaries
                WHERE conversation_id = ? AND user_id = ?
                """,
                (conversation_id, user_id),
            )

    def delete_user_memory(self, user_id: str, memory_id: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE memory_items SET status = 'deleted', updated_at = ?
                WHERE memory_id = ? AND user_id = ? AND status != 'deleted'
                """,
                (now, memory_id, user_id),
            )
        return cursor.rowcount > 0

    @staticmethod
    def _row_to_memory(
        row: sqlite3.Row,
        *,
        last_accessed_at: str | None = None,
    ) -> MemoryItem:
        device_id = row["device_id"] or None
        return MemoryItem(
            memory_id=row["memory_id"],
            user_id=row["user_id"],
            device_id=device_id,
            conversation_id=row["conversation_id"],
            memory_type=row["memory_type"],
            memory_key=row["memory_key"],
            agent_name=row["agent_name"],
            skill_id=row["skill_id"],
            content=row["content"],
            confidence=row["confidence"],
            sensitivity=row["sensitivity"],
            version=row["version"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_accessed_at=last_accessed_at or row["last_accessed_at"],
            expires_at=row["expires_at"],
        )
