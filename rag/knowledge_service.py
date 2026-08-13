"""Operational knowledge-base service with recoverable file-level ingestion."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from storage.support_repository import KnowledgeDocument, SupportRepository
from utils.config_handler import chroma_config
from utils.document_security import scan_text_for_prompt_injection
from utils.logger_handler import logger
from utils.path_tool import get_abs_path

if TYPE_CHECKING:
    from rag.vector_store import VectorStoreService


class KnowledgeBaseService:
    """Manage document status, safe ingestion, retry and index removal."""

    def __init__(self, vector_store: "VectorStoreService", repository: SupportRepository | None = None):
        self.vector_store = vector_store
        self.repository = repository or SupportRepository()
        self.data_path = Path(get_abs_path(chroma_config["data_path"])).resolve()
        self.upload_path = self.data_path / "uploads"
        self.allowed_extensions = {f".{suffix.lower().lstrip('.')}" for suffix in chroma_config["allow_knowledge_file_type"]}

    def list_documents(self) -> list[KnowledgeDocument]:
        return self.repository.list_knowledge_documents()

    def synchronize_existing_documents(self) -> list[KnowledgeDocument]:
        """Register existing Chroma data and index only files that are truly missing."""
        records: list[KnowledgeDocument] = []
        for source_path in self._knowledge_files():
            content_hash = self._file_hash(source_path)
            indexed_chunk_count = self.vector_store.get_source_chunk_count(source_path)
            document_id = self._document_id(source_path)
            existing = self.repository.get_knowledge_document_by_source(source_path)

            if indexed_chunk_count and (existing is None or existing.content_hash == content_hash):
                record = self.repository.save_knowledge_document(
                    document_id=document_id,
                    source_path=source_path,
                    filename=source_path.name,
                    content_hash=content_hash,
                    status="indexed",
                    chunk_count=indexed_chunk_count,
                )
            else:
                record = self.index_file(source_path)
            records.append(record)
        return records

    def index_file(self, source_path: str | Path) -> KnowledgeDocument:
        source = Path(source_path).resolve()
        self._validate_source(source)
        content_hash = self._file_hash(source)
        document_id = self._document_id(source)
        documents = self.vector_store.prepare_document_chunks(source, document_id)
        scan_result = scan_text_for_prompt_injection("\n".join(document.page_content for document in documents))

        if scan_result.is_blocked:
            return self.repository.save_knowledge_document(
                document_id=document_id,
                source_path=source,
                filename=source.name,
                content_hash=content_hash,
                status="blocked",
                risk_level=scan_result.risk_level,
                failure_reason=f"检测到疑似提示注入：{', '.join(scan_result.matched_patterns)}",
            )

        self.vector_store.delete_document(document_id=document_id, source_path=source)
        try:
            self.vector_store.add_documents_in_batches(documents)
        except Exception as error:
            self.vector_store.delete_document(document_id=document_id, source_path=source)
            logger.error("[knowledge base] %s 入库失败：%s", source.name, error, exc_info=True)
            return self.repository.save_knowledge_document(
                document_id=document_id,
                source_path=source,
                filename=source.name,
                content_hash=content_hash,
                status="failed",
                risk_level=scan_result.risk_level,
                failure_reason=str(error),
            )

        return self.repository.save_knowledge_document(
            document_id=document_id,
            source_path=source,
            filename=source.name,
            content_hash=content_hash,
            status="indexed",
            chunk_count=len(documents),
            risk_level=scan_result.risk_level,
        )

    def ingest_upload(self, filename: str, content: bytes) -> KnowledgeDocument:
        safe_name = self._safe_filename(filename)
        if not content:
            raise ValueError("上传文件不能为空")
        if len(content) > 10 * 1024 * 1024:
            raise ValueError("上传文件不能超过 10MB")

        self.upload_path.mkdir(parents=True, exist_ok=True)
        target_path = self.upload_path / f"{uuid4().hex}_{safe_name}"
        target_path.write_bytes(content)
        record = self.index_file(target_path)
        if record.status == "blocked":
            target_path.unlink(missing_ok=True)
        return record

    def remove_from_index(self, document_id: str) -> None:
        document = self.repository.get_knowledge_document(document_id)
        if document is None:
            raise ValueError("未找到要移除的知识库文档")
        self.vector_store.delete_document(document_id=document.document_id, source_path=document.source_path)
        self.repository.save_knowledge_document(
            document_id=document.document_id,
            source_path=document.source_path,
            filename=document.filename,
            content_hash=document.content_hash,
            status="removed",
            risk_level=document.risk_level,
        )

    def _knowledge_files(self) -> list[Path]:
        return sorted(
            path for path in self.data_path.rglob("*")
            if path.is_file() and path.suffix.lower() in self.allowed_extensions
        )

    def _validate_source(self, source: Path) -> None:
        if not source.is_file():
            raise FileNotFoundError(f"知识文件不存在：{source}")
        if source.suffix.lower() not in self.allowed_extensions:
            raise ValueError(f"不支持的知识文件类型：{source.suffix}")

    @staticmethod
    def _file_hash(source: Path) -> str:
        return hashlib.md5(source.read_bytes()).hexdigest()

    @staticmethod
    def _document_id(source: Path) -> str:
        return hashlib.sha256(str(source).encode("utf-8")).hexdigest()

    def _safe_filename(self, filename: str) -> str:
        safe_name = re.sub(r"[^\w.\-\u4e00-\u9fff]", "_", Path(filename).name)
        if not safe_name or Path(safe_name).suffix.lower() not in self.allowed_extensions:
            raise ValueError("仅支持 TXT 和 PDF 知识文件")
        return safe_name
