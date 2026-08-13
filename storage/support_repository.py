"""SQLite repository for knowledge-base operational state."""

from __future__ import annotations

import sqlite3
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


class SupportRepository:
    """Persist document ingestion state independently from Chroma metadata."""

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

    @staticmethod
    def serialize_document(document: KnowledgeDocument) -> dict[str, object]:
        return asdict(document)

    @staticmethod
    def _row_to_document(row: sqlite3.Row | None) -> KnowledgeDocument | None:
        return KnowledgeDocument(**dict(row)) if row else None
