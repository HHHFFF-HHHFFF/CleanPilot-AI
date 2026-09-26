from langchain_core.documents import Document

from rag.retrieval import HybridRetriever
from storage.support_repository import SupportRepository


class FakeVectorStore:
    def __init__(self, documents):
        self.documents = documents

    def similarity_search(self, query, k):
        return self.documents[:k]


class ReverseReranker:
    def rerank(self, query, documents, top_n):
        return list(reversed(documents))[:top_n]


def seed_chunk(repository, tmp_path, document_id, filename, chunk_id, content, chunk_order=0):
    source = tmp_path / filename
    source.write_text(content, encoding="utf-8")
    repository.save_knowledge_document(
        document_id=document_id,
        source_path=source,
        filename=filename,
        content_hash=f"file-{document_id}",
        status="indexed",
        chunk_count=1,
    )
    repository.stage_document_chunks(
        document_id,
        [
            {
                "chunk_id": chunk_id,
                "content_hash": chunk_id,
                "content": content,
                "vector_id": f"vector-{chunk_id}",
                "embedding_model": "test-model",
                "chunk_order": chunk_order,
                "page": None,
                "source_path": str(source.resolve()),
                "source_name": filename,
            }
        ],
    )
    repository.mark_chunks_indexed([chunk_id])
    return source


def test_hybrid_retriever_fuses_vector_and_keyword_channels(tmp_path):
    repository = SupportRepository(tmp_path / "support.db")
    vector_source = seed_chunk(
        repository, tmp_path, "doc-vector", "维护.txt", "chunk-vector", "滤网定期维护"
    )
    seed_chunk(
        repository, tmp_path, "doc-keyword", "故障.txt", "chunk-keyword", "E3 主刷堵塞故障"
    )
    vector_store = FakeVectorStore(
        [
            Document(
                page_content="滤网定期维护",
                metadata={"chunk_id": "chunk-vector", "source": str(vector_source)},
            )
        ]
    )
    retriever = HybridRetriever(
        vector_store,
        repository,
        vector_k=5,
        keyword_k=5,
        fusion_k=5,
        final_k=2,
    )

    results = retriever.invoke("E3 主刷堵塞")

    assert {document.metadata["chunk_id"] for document in results} == {
        "chunk-vector",
        "chunk-keyword",
    }
    assert results[0].metadata["retrieval_channels"]


def test_hybrid_retriever_applies_reranker_after_fusion(tmp_path):
    repository = SupportRepository(tmp_path / "support.db")
    first_source = seed_chunk(repository, tmp_path, "doc-1", "一.txt", "chunk-1", "主刷维护")
    second_source = seed_chunk(repository, tmp_path, "doc-2", "二.txt", "chunk-2", "滤网维护")
    vector_store = FakeVectorStore(
        [
            Document(page_content="主刷维护", metadata={"chunk_id": "chunk-1", "source": str(first_source)}),
            Document(page_content="滤网维护", metadata={"chunk_id": "chunk-2", "source": str(second_source)}),
        ]
    )
    retriever = HybridRetriever(
        vector_store,
        repository,
        final_k=1,
        fusion_k=2,
        reranker=ReverseReranker(),
    )

    result = retriever.invoke("维护")

    assert len(result) == 1
    assert result[0].metadata["chunk_id"] == "chunk-2"
