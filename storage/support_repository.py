"""用于保存知识库运营状态和客服业务数据的 SQLite 仓储。"""

from __future__ import annotations

import sqlite3
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from utils.path_tool import get_abs_path
from utils.text_tokenizer import build_fts_query, tokenize_search_text


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
class KnowledgeChunk:
    chunk_id: str
    content_hash: str
    content: str
    vector_id: str
    embedding_model: str
    status: str
    failure_reason: str | None
    retry_count: int
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class KeywordChunkHit:
    chunk_id: str
    content: str
    source_path: str
    source_name: str
    document_id: str
    chunk_order: int
    page: int | None
    score: float


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
                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL,
                    content TEXT NOT NULL,
                    vector_id TEXT NOT NULL UNIQUE,
                    embedding_model TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    failure_reason TEXT,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS document_chunk_links (
                    document_id TEXT NOT NULL,
                    chunk_id TEXT NOT NULL,
                    chunk_order INTEGER NOT NULL,
                    page INTEGER,
                    source_path TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    PRIMARY KEY(document_id, chunk_order),
                    FOREIGN KEY(document_id) REFERENCES knowledge_documents(document_id),
                    FOREIGN KEY(chunk_id) REFERENCES knowledge_chunks(chunk_id)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_document_chunk_links_chunk
                ON document_chunk_links(chunk_id)
                """
            )
            connection.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts USING fts5(
                    chunk_id UNINDEXED,
                    tokens,
                    content,
                    tokenize = 'unicode61'
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

    def list_document_chunks(self, document_id: str) -> list[KnowledgeChunk]:
        """按原文顺序返回文档关联的知识片段。"""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT c.* FROM knowledge_chunks AS c
                JOIN document_chunk_links AS l ON l.chunk_id = c.chunk_id
                WHERE l.document_id = ? ORDER BY l.chunk_order
                """,
                (document_id,),
            ).fetchall()
        return [KnowledgeChunk(**dict(row)) for row in rows]

    def list_document_chunk_details(self, document_id: str) -> list[dict[str, object]]:
        """返回运营页面所需的片段状态、顺序和来源信息。"""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT c.chunk_id, c.content_hash, c.content, c.vector_id,
                       c.embedding_model, c.status, c.failure_reason,
                       c.retry_count, c.created_at, c.updated_at,
                       l.chunk_order, l.page, l.source_name
                FROM knowledge_chunks AS c
                JOIN document_chunk_links AS l ON l.chunk_id = c.chunk_id
                WHERE l.document_id = ? ORDER BY l.chunk_order
                """,
                (document_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_chunks(self, chunk_ids: list[str]) -> dict[str, KnowledgeChunk]:
        """批量读取片段状态，避免入库时逐片查询。"""
        if not chunk_ids:
            return {}
        placeholders = ",".join("?" for _ in chunk_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM knowledge_chunks WHERE chunk_id IN ({placeholders})",
                chunk_ids,
            ).fetchall()
        return {row["chunk_id"]: KnowledgeChunk(**dict(row)) for row in rows}

    def stage_document_chunks(
        self,
        document_id: str,
        chunks: list[dict[str, object]],
    ) -> list[str]:
        """写入片段及文档关联，并返回因失去引用而需要清理的向量 ID。"""
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            old_chunk_ids = {
                row["chunk_id"]
                for row in connection.execute(
                    "SELECT chunk_id FROM document_chunk_links WHERE document_id = ?",
                    (document_id,),
                ).fetchall()
            }
            connection.execute(
                "DELETE FROM document_chunk_links WHERE document_id = ?",
                (document_id,),
            )
            for chunk in chunks:
                existing = connection.execute(
                    "SELECT rowid, status, embedding_model FROM knowledge_chunks WHERE chunk_id = ?",
                    (chunk["chunk_id"],),
                ).fetchone()
                status = (
                    existing["status"]
                    if existing and existing["embedding_model"] == chunk["embedding_model"]
                    else "pending"
                )
                connection.execute(
                    """
                    INSERT INTO knowledge_chunks(
                        chunk_id, content_hash, content, vector_id, embedding_model,
                        status, failure_reason, retry_count, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, NULL, 0, ?, ?)
                    ON CONFLICT(chunk_id) DO UPDATE SET
                        content_hash = excluded.content_hash,
                        content = excluded.content,
                        vector_id = excluded.vector_id,
                        embedding_model = excluded.embedding_model,
                        status = ?,
                        failure_reason = CASE WHEN ? = 'pending' THEN NULL ELSE failure_reason END,
                        updated_at = excluded.updated_at
                    """,
                    (
                        chunk["chunk_id"],
                        chunk["content_hash"],
                        chunk["content"],
                        chunk["vector_id"],
                        chunk["embedding_model"],
                        status,
                        now,
                        now,
                        status,
                        status,
                    ),
                )
                row = connection.execute(
                    "SELECT rowid FROM knowledge_chunks WHERE chunk_id = ?",
                    (chunk["chunk_id"],),
                ).fetchone()
                connection.execute("DELETE FROM knowledge_chunks_fts WHERE rowid = ?", (row["rowid"],))
                tokens = " ".join(tokenize_search_text(str(chunk["content"])))
                connection.execute(
                    "INSERT INTO knowledge_chunks_fts(rowid, chunk_id, tokens, content) VALUES (?, ?, ?, ?)",
                    (row["rowid"], chunk["chunk_id"], tokens, chunk["content"]),
                )
                connection.execute(
                    """
                    INSERT INTO document_chunk_links(
                        document_id, chunk_id, chunk_order, page, source_path, source_name
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        document_id,
                        chunk["chunk_id"],
                        chunk["chunk_order"],
                        chunk.get("page"),
                        chunk["source_path"],
                        chunk["source_name"],
                    ),
                )

            new_chunk_ids = {str(chunk["chunk_id"]) for chunk in chunks}
            candidate_orphans = old_chunk_ids - new_chunk_ids
            orphan_vector_ids: list[str] = []
            for chunk_id in candidate_orphans:
                reference_count = connection.execute(
                    "SELECT COUNT(*) FROM document_chunk_links WHERE chunk_id = ?",
                    (chunk_id,),
                ).fetchone()[0]
                if reference_count:
                    continue
                row = connection.execute(
                    "SELECT rowid, vector_id FROM knowledge_chunks WHERE chunk_id = ?",
                    (chunk_id,),
                ).fetchone()
                if row:
                    orphan_vector_ids.append(row["vector_id"])
                    connection.execute("DELETE FROM knowledge_chunks_fts WHERE rowid = ?", (row["rowid"],))
                    connection.execute("DELETE FROM knowledge_chunks WHERE chunk_id = ?", (chunk_id,))
        return orphan_vector_ids

    def mark_chunks_indexed(self, chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.executemany(
                """
                UPDATE knowledge_chunks SET status = 'indexed', failure_reason = NULL,
                    updated_at = ? WHERE chunk_id = ?
                """,
                [(now, chunk_id) for chunk_id in chunk_ids],
            )

    def mark_chunks_failed(self, chunk_ids: list[str], reason: str) -> None:
        if not chunk_ids:
            return
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.executemany(
                """
                UPDATE knowledge_chunks SET status = 'failed', failure_reason = ?,
                    retry_count = retry_count + 1, updated_at = ? WHERE chunk_id = ?
                """,
                [(reason, now, chunk_id) for chunk_id in chunk_ids],
            )

    def detach_document_chunks(self, document_id: str) -> list[str]:
        """解除文档关联并删除不再被任何文档引用的片段记录。"""
        with self._connect() as connection:
            chunk_ids = [
                row["chunk_id"]
                for row in connection.execute(
                    "SELECT chunk_id FROM document_chunk_links WHERE document_id = ?",
                    (document_id,),
                ).fetchall()
            ]
            connection.execute("DELETE FROM document_chunk_links WHERE document_id = ?", (document_id,))
            vector_ids: list[str] = []
            for chunk_id in chunk_ids:
                if connection.execute(
                    "SELECT COUNT(*) FROM document_chunk_links WHERE chunk_id = ?",
                    (chunk_id,),
                ).fetchone()[0]:
                    continue
                row = connection.execute(
                    "SELECT rowid, vector_id FROM knowledge_chunks WHERE chunk_id = ?",
                    (chunk_id,),
                ).fetchone()
                if row:
                    vector_ids.append(row["vector_id"])
                    connection.execute("DELETE FROM knowledge_chunks_fts WHERE rowid = ?", (row["rowid"],))
                    connection.execute("DELETE FROM knowledge_chunks WHERE chunk_id = ?", (chunk_id,))
        return vector_ids

    def search_knowledge_chunks(self, query: str, limit: int = 20) -> list[KeywordChunkHit]:
        """使用 FTS5 BM25 对已完成向量化的片段执行关键词召回。"""
        fts_query = build_fts_query(query)
        if not fts_query:
            return []
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT c.chunk_id, c.content, l.source_path, l.source_name,
                       l.document_id, l.chunk_order, l.page,
                       -bm25(knowledge_chunks_fts, 0.0, 1.0, 0.2) AS score
                FROM knowledge_chunks_fts
                JOIN knowledge_chunks AS c ON c.rowid = knowledge_chunks_fts.rowid
                JOIN document_chunk_links AS l ON l.chunk_id = c.chunk_id
                WHERE knowledge_chunks_fts MATCH ? AND c.status = 'indexed'
                ORDER BY bm25(knowledge_chunks_fts, 0.0, 1.0, 0.2)
                LIMIT ?
                """,
                (fts_query, max(0, limit)),
            ).fetchall()
        return [KeywordChunkHit(**dict(row)) for row in rows]

    def get_chunk_sources(self, chunk_id: str) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT document_id, source_path, source_name, chunk_order, page
                FROM document_chunk_links WHERE chunk_id = ? ORDER BY source_name, chunk_order
                """,
                (chunk_id,),
            ).fetchall()
        return [dict(row) for row in rows]

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
