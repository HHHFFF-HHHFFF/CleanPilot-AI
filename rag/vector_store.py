from __future__ import annotations

from pathlib import Path
import hashlib
from typing import Sequence

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from model.factory import embed_model
from rag.retrieval import DashScopeReranker, HybridRetriever, KeywordRetriever, VectorRetriever
from storage.support_repository import SupportRepository
from utils.config_handler import chroma_config, rag_config
from utils.file_handler import pdf_loader, txt_loader
from utils.path_tool import get_abs_path


class VectorStoreService:
    """为知识库服务提供 Chroma 访问与文档切片操作。"""

    def __init__(self, repository: SupportRepository | None = None):
        self.vector_store = Chroma(
            collection_name=chroma_config["collection_name"],
            embedding_function=embed_model,
            persist_directory=get_abs_path(chroma_config["persist_directory"]),
        )
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chroma_config["chunk_size"],
            chunk_overlap=chroma_config["chunk_overlap"],
            separators=chroma_config["separators"],
            length_function=len,
        )
        self.repository = repository or SupportRepository()

    def get_retriever(self, *, mode: str = "hybrid_rerank", top_k: int | None = None):
        final_k = top_k or chroma_config["k"]
        if mode == "vector":
            return VectorRetriever(self.vector_store, final_k)
        if mode == "keyword":
            return KeywordRetriever(self.repository, final_k)
        reranker = None
        if mode == "hybrid_rerank" and chroma_config.get("rerank_enabled", True):
            reranker = DashScopeReranker(chroma_config.get("rerank_model", "qwen3-rerank"))
        return HybridRetriever(
            self.vector_store,
            self.repository,
            vector_k=max(final_k, chroma_config.get("vector_k", 20)),
            keyword_k=max(final_k, chroma_config.get("keyword_k", 20)),
            fusion_k=max(final_k, chroma_config.get("fusion_k", 10)),
            final_k=final_k,
            rrf_constant=chroma_config.get("rrf_constant", 60),
            reranker=reranker,
        )

    def prepare_document_chunks(self, source_path: str | Path, document_id: str) -> list[Document]:
        source = Path(source_path).resolve()
        documents = self._load_documents(source)
        if not documents:
            raise ValueError(f"知识文件没有可用文本：{source.name}")

        chunks = self.splitter.split_documents(documents)
        if not chunks:
            raise ValueError(f"知识文件切分后没有可用片段：{source.name}")

        for chunk_order, chunk in enumerate(chunks):
            normalized_content = " ".join(chunk.page_content.split())
            content_hash = hashlib.sha256(normalized_content.encode("utf-8")).hexdigest()
            vector_id = hashlib.sha256(
                f"{content_hash}:{rag_config['embedding_model_name']}".encode("utf-8")
            ).hexdigest()
            chunk.metadata.update(
                {
                    "document_id": document_id,
                    "source": str(source),
                    "source_name": source.name,
                    "chunk_id": content_hash,
                    "content_hash": content_hash,
                    "vector_id": vector_id,
                    "chunk_order": chunk_order,
                }
            )
        return chunks

    def add_documents_in_batches(self, documents: Sequence[Document], batch_size: int = 16) -> None:
        for start_index in range(0, len(documents), batch_size):
            batch = list(documents[start_index : start_index + batch_size])
            self.vector_store.add_documents(
                batch,
                ids=[str(document.metadata["vector_id"]) for document in batch],
            )

    def add_document_batch(self, documents: Sequence[Document]) -> None:
        batch = list(documents)
        if not batch:
            return
        self.vector_store.add_documents(
            batch,
            ids=[str(document.metadata["vector_id"]) for document in batch],
        )

    def delete_vectors(self, vector_ids: Sequence[str]) -> None:
        if vector_ids:
            self.vector_store.delete(ids=list(vector_ids))

    def get_source_chunk_count(self, source_path: str | Path) -> int:
        source = str(Path(source_path).resolve())
        result = self.vector_store.get(where={"source": source}, include=[])
        return len(result.get("ids", []))

    def delete_document(self, *, document_id: str, source_path: str | Path) -> None:
        self.vector_store.delete(where={"document_id": document_id})
        self.vector_store.delete(where={"source": str(Path(source_path).resolve())})

    def load_document(self):
        """兼容旧版调用方式的知识库同步命令行入口。"""
        from rag.knowledge_service import KnowledgeBaseService

        return KnowledgeBaseService(self).synchronize_existing_documents()

    @staticmethod
    def _load_documents(source: Path) -> list[Document]:
        if source.suffix.lower() == ".txt":
            return txt_loader(str(source))
        if source.suffix.lower() == ".pdf":
            return pdf_loader(str(source))
        raise ValueError(f"不支持的知识文件类型：{source.suffix}")


if __name__ == "__main__":
    records = VectorStoreService().load_document()
    for record in records:
        print(f"{record.filename}: {record.status} ({record.chunk_count} 个片段)")
