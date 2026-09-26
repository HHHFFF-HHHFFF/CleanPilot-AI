"""支持片段级去重、恢复和移除的知识库运营服务。"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from langchain_core.documents import Document

from storage.support_repository import KnowledgeDocument, SupportRepository
from utils.config_handler import chroma_config, rag_config
from utils.document_security import scan_text_for_prompt_injection
from utils.logger_handler import logger
from utils.path_tool import get_abs_path

if TYPE_CHECKING:
    from rag.vector_store import VectorStoreService


class KnowledgeBaseService:
    """管理文档状态、安全入库、重试与索引移除。"""

    def __init__(self, vector_store: "VectorStoreService", repository: SupportRepository | None = None):
        self.vector_store = vector_store
        self.repository = repository or SupportRepository()
        self.data_path = Path(get_abs_path(chroma_config["data_path"])).resolve()
        self.upload_path = self.data_path / "uploads"
        self.allowed_extensions = {f".{suffix.lower().lstrip('.')}" for suffix in chroma_config["allow_knowledge_file_type"]}

    def list_documents(self) -> list[KnowledgeDocument]:
        return self.repository.list_knowledge_documents()

    def list_document_chunks(self, document_id: str) -> list[dict[str, object]]:
        if self.repository.get_knowledge_document(document_id) is None:
            raise ValueError("未找到知识库文档")
        return self.repository.list_document_chunk_details(document_id)

    def retry_chunk(self, chunk_id: str) -> dict[str, object]:
        chunks = self.repository.get_chunks([chunk_id])
        chunk = chunks.get(chunk_id)
        if chunk is None:
            raise ValueError("未找到知识片段")
        sources = self.repository.get_chunk_sources(chunk_id)
        if not sources:
            raise ValueError("知识片段没有关联文档")
        primary_source = sources[0]
        document = Document(
            page_content=chunk.content,
            metadata={
                "chunk_id": chunk.chunk_id,
                "content_hash": chunk.content_hash,
                "vector_id": chunk.vector_id,
                "document_id": primary_source["document_id"],
                "source": primary_source["source_path"],
                "source_name": primary_source["source_name"],
                "chunk_order": primary_source["chunk_order"],
                "page": primary_source["page"],
            },
        )
        try:
            self.vector_store.add_document_batch([document])
            self.repository.mark_chunks_indexed([chunk_id])
        except Exception as error:
            self.repository.mark_chunks_failed([chunk_id], str(error))
            raise RuntimeError(f"知识片段重新入库失败：{error}") from error

        for source in sources:
            self._refresh_document_status(str(source["document_id"]))
        details = self.repository.list_document_chunk_details(str(primary_source["document_id"]))
        return next(detail for detail in details if detail["chunk_id"] == chunk_id)

    def synchronize_existing_documents(self) -> list[KnowledgeDocument]:
        """同步知识目录，并为旧索引补齐片段级状态和关键词索引。"""
        records: list[KnowledgeDocument] = []
        for source_path in self._knowledge_files():
            content_hash = self._file_hash(source_path)
            document_id = self._document_id(source_path)
            existing = self.repository.get_knowledge_document_by_source(source_path)
            managed_chunks = self.repository.list_document_chunks(document_id)
            if (
                existing is not None
                and existing.content_hash == content_hash
                and managed_chunks
                and all(chunk.status == "indexed" for chunk in managed_chunks)
            ):
                record = existing
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

        managed_chunks = self.repository.list_document_chunks(document_id)
        self.repository.save_knowledge_document(
            document_id=document_id,
            source_path=source,
            filename=source.name,
            content_hash=content_hash,
            status="indexing",
            chunk_count=len(documents),
            risk_level=scan_result.risk_level,
        )
        if not managed_chunks and self.vector_store.get_source_chunk_count(source):
            self.vector_store.delete_document(document_id=document_id, source_path=source)

        chunk_records = [self._chunk_record(document) for document in documents]
        orphan_vector_ids = self.repository.stage_document_chunks(document_id, chunk_records)
        self.vector_store.delete_vectors(orphan_vector_ids)
        stored_chunks = self.repository.get_chunks(
            [str(document.metadata["chunk_id"]) for document in documents]
        )
        pending_documents: dict[str, object] = {}
        for document in documents:
            chunk_id = str(document.metadata["chunk_id"])
            stored_chunk = stored_chunks.get(chunk_id)
            if stored_chunk is None or stored_chunk.status != "indexed":
                pending_documents[chunk_id] = document

        failed_chunks: list[str] = []
        failure_messages: list[str] = []
        batch_size = int(chroma_config.get("embedding_batch_size", 16))
        pending_values = list(pending_documents.values())
        for start_index in range(0, len(pending_values), batch_size):
            batch = pending_values[start_index : start_index + batch_size]
            batch_ids = [str(document.metadata["chunk_id"]) for document in batch]
            try:
                self.vector_store.add_document_batch(batch)
                self.repository.mark_chunks_indexed(batch_ids)
            except Exception as error:
                failed_chunks.extend(batch_ids)
                failure_messages.append(str(error))
                self.repository.mark_chunks_failed(batch_ids, str(error))
                logger.error(
                    "[knowledge base] %s 的片段批次入库失败：%s",
                    source.name,
                    error,
                    exc_info=True,
                )

        if failed_chunks:
            return self.repository.save_knowledge_document(
                document_id=document_id,
                source_path=source,
                filename=source.name,
                content_hash=content_hash,
                status="partial" if len(failed_chunks) < len(pending_documents) else "failed",
                chunk_count=len(documents) - len(failed_chunks),
                risk_level=scan_result.risk_level,
                failure_reason=(
                    f"{len(failed_chunks)} 个片段入库失败，可重新执行入库以重试；"
                    f"最后错误：{failure_messages[-1]}"
                ),
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
        orphan_vector_ids = self.repository.detach_document_chunks(document.document_id)
        self.vector_store.delete_vectors(orphan_vector_ids)
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
        return hashlib.sha256(source.read_bytes()).hexdigest()

    @staticmethod
    def _document_id(source: Path) -> str:
        return hashlib.sha256(str(source).encode("utf-8")).hexdigest()

    def _safe_filename(self, filename: str) -> str:
        safe_name = re.sub(r"[^\w.\-\u4e00-\u9fff]", "_", Path(filename).name)
        if not safe_name or Path(safe_name).suffix.lower() not in self.allowed_extensions:
            raise ValueError("仅支持 TXT 和 PDF 知识文件")
        return safe_name

    def _refresh_document_status(self, document_id: str) -> None:
        document = self.repository.get_knowledge_document(document_id)
        if document is None:
            return
        chunks = self.repository.list_document_chunks(document_id)
        indexed_count = sum(chunk.status == "indexed" for chunk in chunks)
        status = "indexed" if indexed_count == len(chunks) else "partial"
        self.repository.save_knowledge_document(
            document_id=document.document_id,
            source_path=document.source_path,
            filename=document.filename,
            content_hash=document.content_hash,
            status=status,
            chunk_count=indexed_count,
            risk_level=document.risk_level,
            failure_reason=None if status == "indexed" else document.failure_reason,
        )

    @staticmethod
    def _chunk_record(document) -> dict[str, object]:
        metadata = document.metadata
        return {
            "chunk_id": str(metadata["chunk_id"]),
            "content_hash": str(metadata["content_hash"]),
            "content": document.page_content,
            "vector_id": str(metadata["vector_id"]),
            "embedding_model": str(rag_config["embedding_model_name"]),
            "chunk_order": int(metadata["chunk_order"]),
            "page": metadata.get("page"),
            "source_path": str(metadata["source"]),
            "source_name": str(metadata["source_name"]),
        }
