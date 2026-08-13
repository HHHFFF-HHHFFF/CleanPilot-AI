from __future__ import annotations

from pathlib import Path
from typing import Sequence

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from model.factory import embed_model
from utils.config_handler import chroma_config
from utils.file_handler import pdf_loader, txt_loader
from utils.path_tool import get_abs_path


class VectorStoreService:
    """Chroma access and document chunk operations used by the knowledge service."""

    def __init__(self):
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

    def get_retriever(self):
        return self.vector_store.as_retriever(search_kwargs={"k": chroma_config["k"]})

    def prepare_document_chunks(self, source_path: str | Path, document_id: str) -> list[Document]:
        source = Path(source_path).resolve()
        documents = self._load_documents(source)
        if not documents:
            raise ValueError(f"知识文件没有可用文本：{source.name}")

        chunks = self.splitter.split_documents(documents)
        if not chunks:
            raise ValueError(f"知识文件切分后没有可用片段：{source.name}")

        for chunk in chunks:
            chunk.metadata.update(
                {
                    "document_id": document_id,
                    "source": str(source),
                    "source_name": source.name,
                }
            )
        return chunks

    def add_documents_in_batches(self, documents: Sequence[Document], batch_size: int = 16) -> None:
        for start_index in range(0, len(documents), batch_size):
            self.vector_store.add_documents(list(documents[start_index : start_index + batch_size]))

    def get_source_chunk_count(self, source_path: str | Path) -> int:
        source = str(Path(source_path).resolve())
        result = self.vector_store.get(where={"source": source}, include=[])
        return len(result.get("ids", []))

    def delete_document(self, *, document_id: str, source_path: str | Path) -> None:
        self.vector_store.delete(where={"document_id": document_id})
        self.vector_store.delete(where={"source": str(Path(source_path).resolve())})

    def load_document(self):
        """Backward-compatible command-line entry point for knowledge synchronization."""
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
