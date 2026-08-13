"""用于保存知识库运营状态和客服业务数据的 SQLite 仓储。"""

from __future__ import annotations

import sqlite3
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from utils.path_tool import get_abs_path


@dataclass(frozen=True)
class KnowledgeDocument:
    document_id: str
    source_path: str
    filename: str
    content_hash: str
    status: str
    chunk_count: int
    risk_level: str
    failure_reason: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class SupportUser:
    user_id: str
    display_name: str
    city: str


@dataclass(frozen=True)
class UsageRecord:
    user_id: str
    month: str
    feature: str
    efficiency: str
    consumables: str
    comparison: str


class SupportRepository:
    """独立于 Chroma 元数据，持久化文档入库状态与业务数据。"""

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
                CREATE TABLE IF NOT EXISTS knowledge_documents (
                    document_id TEXT PRIMARY KEY,
                    source_path TEXT NOT NULL UNIQUE,
                    filename TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    chunk_count INTEGER NOT NULL DEFAULT 0,
                    risk_level TEXT NOT NULL DEFAULT 'none',
                    failure_reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    city TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    device_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    purchased_at TEXT NOT NULL,
                    warranty_until TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS usage_records (
                    user_id TEXT NOT NULL,
                    month TEXT NOT NULL,
                    feature TEXT NOT NULL,
                    efficiency TEXT NOT NULL,
                    consumables TEXT NOT NULL,
                    comparison TEXT NOT NULL,
                    PRIMARY KEY(user_id, month),
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                )
                """
            )

    def get_knowledge_document(self, document_id: str) -> KnowledgeDocument | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM knowledge_documents WHERE document_id = ?", (document_id,)
            ).fetchone()
        return self._row_to_document(row)

    def get_knowledge_document_by_source(self, source_path: str | Path) -> KnowledgeDocument | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM knowledge_documents WHERE source_path = ?", (str(Path(source_path).resolve()),)
            ).fetchone()
        return self._row_to_document(row)

    def list_knowledge_documents(self) -> list[KnowledgeDocument]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM knowledge_documents ORDER BY updated_at DESC, filename ASC"
            ).fetchall()
        return [self._row_to_document(row) for row in rows]

    def save_knowledge_document(
        self,
        *,
        document_id: str,
        source_path: str | Path,
        filename: str,
        content_hash: str,
        status: str,
        chunk_count: int = 0,
        risk_level: str = "none",
        failure_reason: str | None = None,
    ) -> KnowledgeDocument:
        now = datetime.now(timezone.utc).isoformat()
        resolved_source = str(Path(source_path).resolve())
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT created_at FROM knowledge_documents WHERE source_path = ?", (resolved_source,)
            ).fetchone()
            created_at = existing["created_at"] if existing else now
            connection.execute(
                """
                INSERT INTO knowledge_documents (
                    document_id, source_path, filename, content_hash, status, chunk_count,
                    risk_level, failure_reason, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_path) DO UPDATE SET
                    document_id = excluded.document_id,
                    filename = excluded.filename,
                    content_hash = excluded.content_hash,
                    status = excluded.status,
                    chunk_count = excluded.chunk_count,
                    risk_level = excluded.risk_level,
                    failure_reason = excluded.failure_reason,
                    updated_at = excluded.updated_at
                """,
                (
                    document_id,
                    resolved_source,
                    filename,
                    content_hash,
                    status,
                    chunk_count,
                    risk_level,
                    failure_reason,
                    created_at,
                    now,
                ),
            )
        document = self.get_knowledge_document_by_source(resolved_source)
        if document is None:
            raise RuntimeError("知识库文档状态写入失败")
        return document

    def delete_knowledge_document(self, document_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM knowledge_documents WHERE document_id = ?", (document_id,))

    def seed_business_data(self, csv_path: str | Path | None = None) -> None:
        """仅在数据库为空时导入非敏感演示用户与月度使用记录。"""
        seed_path = Path(csv_path or get_abs_path("data/external/records.csv"))
        if not seed_path.exists():
            raise FileNotFoundError(f"业务种子数据不存在：{seed_path}")

        with self._connect() as connection:
            existing_count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            if existing_count:
                return

            with seed_path.open("r", encoding="utf-8", newline="") as file:
                for row in csv.DictReader(file):
                    connection.execute(
                        "INSERT OR IGNORE INTO users(user_id, display_name, city) VALUES (?, ?, ?)",
                        (row["user_id"], row["display_name"], row["city"]),
                    )
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO devices(device_id, user_id, model, purchased_at, warranty_until)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            row["device_id"],
                            row["user_id"],
                            row["device_model"],
                            row["purchased_at"],
                            row["warranty_until"],
                        ),
                    )
                    connection.execute(
                        """
                        INSERT OR REPLACE INTO usage_records(
                            user_id, month, feature, efficiency, consumables, comparison
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            row["user_id"],
                            row["month"],
                            row["feature"],
                            row["efficiency"],
                            row["consumables"],
                            row["comparison"],
                        ),
                    )

    def list_users(self) -> list[SupportUser]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT user_id, display_name, city FROM users ORDER BY user_id"
            ).fetchall()
        return [SupportUser(**dict(row)) for row in rows]

    def get_user(self, user_id: str) -> SupportUser | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT user_id, display_name, city FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
        return SupportUser(**dict(row)) if row else None

    def get_device(self, user_id: str) -> dict[str, str] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT device_id, model, purchased_at, warranty_until
                FROM devices WHERE user_id = ? ORDER BY purchased_at DESC LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_usage_record(self, user_id: str, month: str) -> UsageRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT user_id, month, feature, efficiency, consumables, comparison
                FROM usage_records WHERE user_id = ? AND month = ?
                """,
                (user_id, month),
            ).fetchone()
        return UsageRecord(**dict(row)) if row else None

    @staticmethod
    def serialize_document(document: KnowledgeDocument) -> dict[str, object]:
        return asdict(document)

    @staticmethod
    def _row_to_document(row: sqlite3.Row | None) -> KnowledgeDocument | None:
        return KnowledgeDocument(**dict(row)) if row else None
