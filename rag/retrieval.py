"""组合向量、关键词与精排模型的知识检索链路。"""

from __future__ import annotations

from collections.abc import Sequence
import time
from typing import Any, Protocol

import dashscope
from langchain_core.documents import Document

from storage.support_repository import SupportRepository
from utils.logger_handler import logger


class Reranker(Protocol):
    def rerank(self, query: str, documents: Sequence[Document], top_n: int) -> list[Document]:
        """按查询相关性返回重新排序后的文档。"""


class DashScopeReranker:
    """调用通义千问文本精排服务，并在外部服务异常时保持原融合顺序。"""

    def __init__(self, model: str = "qwen3-rerank"):
        self.model = model

    def rerank(self, query: str, documents: Sequence[Document], top_n: int) -> list[Document]:
        candidates = list(documents)
        if len(candidates) <= 1:
            return candidates[:top_n]
        try:
            response = None
            last_error: Exception | None = None
            for attempt in range(3):
                try:
                    response = dashscope.TextReRank.call(
                        model=self.model,
                        query=query,
                        documents=[document.page_content for document in candidates],
                        top_n=min(top_n, len(candidates)),
                        return_documents=False,
                    )
                    break
                except Exception as error:
                    last_error = error
                    if attempt < 2:
                        time.sleep(2 ** attempt)
            if response is None:
                raise RuntimeError(str(last_error))
            status_code = getattr(response, "status_code", 200)
            if status_code != 200:
                raise RuntimeError(getattr(response, "message", f"HTTP {status_code}"))
            output = getattr(response, "output", None)
            results = getattr(output, "results", None) if output is not None else None
            if results is None:
                results = getattr(response, "results", None)
            if results is None and isinstance(response, dict):
                results = response.get("output", {}).get("results") or response.get("results")
            if not results:
                raise RuntimeError("精排服务未返回排序结果")

            reranked: list[Document] = []
            for result in results:
                index = result.get("index") if isinstance(result, dict) else getattr(result, "index", None)
                score = (
                    result.get("relevance_score")
                    if isinstance(result, dict)
                    else getattr(result, "relevance_score", None)
                )
                if not isinstance(index, int) or index < 0 or index >= len(candidates):
                    continue
                document = candidates[index]
                metadata = dict(document.metadata)
                metadata["rerank_score"] = score
                reranked.append(Document(page_content=document.page_content, metadata=metadata))
            return reranked or candidates[:top_n]
        except Exception as error:
            logger.warning("精排服务不可用，保留融合排序结果：%s", error)
            fallback: list[Document] = []
            for document in candidates[:top_n]:
                metadata = dict(document.metadata)
                metadata["rerank_fallback"] = True
                fallback.append(Document(page_content=document.page_content, metadata=metadata))
            return fallback


class KeywordRetriever:
    """将 SQLite FTS5 的 BM25 结果转换为 LangChain 文档。"""

    def __init__(self, repository: SupportRepository, top_k: int = 3):
        self.repository = repository
        self.top_k = top_k

    def invoke(self, query: str) -> list[Document]:
        return [
            Document(
                page_content=hit.content,
                metadata={
                    "chunk_id": hit.chunk_id,
                    "document_id": hit.document_id,
                    "source": hit.source_path,
                    "source_name": hit.source_name,
                    "chunk_order": hit.chunk_order,
                    "page": hit.page,
                    "keyword_score": hit.score,
                },
            )
            for hit in self.repository.search_knowledge_chunks(query, self.top_k)
        ]


class VectorRetriever:
    """提供与其他召回器一致的轻量调用接口。"""

    def __init__(self, vector_store: Any, top_k: int = 3):
        self.vector_store = vector_store
        self.top_k = top_k

    def invoke(self, query: str) -> list[Document]:
        return self.vector_store.similarity_search(query, k=self.top_k)


class HybridRetriever:
    """使用 RRF 融合向量检索与 FTS5 BM25 关键词检索。"""

    def __init__(
        self,
        vector_store: Any,
        repository: SupportRepository,
        *,
        vector_k: int = 20,
        keyword_k: int = 20,
        fusion_k: int = 10,
        final_k: int = 3,
        rrf_constant: int = 60,
        reranker: Reranker | None = None,
    ):
        self.vector_store = vector_store
        self.repository = repository
        self.vector_k = vector_k
        self.keyword_k = keyword_k
        self.fusion_k = fusion_k
        self.final_k = final_k
        self.rrf_constant = rrf_constant
        self.reranker = reranker

    def invoke(self, query: str) -> list[Document]:
        vector_documents = self.vector_store.similarity_search(query, k=self.vector_k)
        keyword_documents = [
            Document(
                page_content=hit.content,
                metadata={
                    "chunk_id": hit.chunk_id,
                    "document_id": hit.document_id,
                    "source": hit.source_path,
                    "source_name": hit.source_name,
                    "chunk_order": hit.chunk_order,
                    "page": hit.page,
                    "keyword_score": hit.score,
                },
            )
            for hit in self.repository.search_knowledge_chunks(query, self.keyword_k)
        ]
        fused = self._reciprocal_rank_fusion(vector_documents, keyword_documents)
        candidates = fused[: max(self.fusion_k, self.final_k)]
        if self.reranker is not None:
            return self.reranker.rerank(query, candidates, self.final_k)
        return candidates[: self.final_k]

    def _reciprocal_rank_fusion(
        self,
        vector_documents: Sequence[Document],
        keyword_documents: Sequence[Document],
    ) -> list[Document]:
        scores: dict[str, float] = {}
        documents: dict[str, Document] = {}
        channels: dict[str, set[str]] = {}
        for channel, ranked_documents in (
            ("vector", vector_documents),
            ("keyword", keyword_documents),
        ):
            seen: set[str] = set()
            for rank, document in enumerate(ranked_documents, start=1):
                key = self._document_key(document)
                if key in seen:
                    continue
                seen.add(key)
                scores[key] = scores.get(key, 0.0) + 1 / (self.rrf_constant + rank)
                channels.setdefault(key, set()).add(channel)
                if key not in documents or channel == "keyword":
                    documents[key] = self._enrich_document(document)

        ordered_keys = sorted(scores, key=lambda key: scores[key], reverse=True)
        results: list[Document] = []
        for key in ordered_keys:
            document = documents[key]
            metadata = dict(document.metadata)
            metadata["fusion_score"] = scores[key]
            metadata["retrieval_channels"] = sorted(channels[key])
            results.append(Document(page_content=document.page_content, metadata=metadata))
        return results

    def _enrich_document(self, document: Document) -> Document:
        metadata = dict(document.metadata)
        chunk_id = str(metadata.get("chunk_id", ""))
        if chunk_id:
            sources = self.repository.get_chunk_sources(chunk_id)
            if sources:
                metadata.update(sources[0])
                metadata["source_names"] = sorted({str(source["source_name"]) for source in sources})
        return Document(page_content=document.page_content, metadata=metadata)

    @staticmethod
    def _document_key(document: Document) -> str:
        chunk_id = document.metadata.get("chunk_id")
        return str(chunk_id) if chunk_id else document.page_content.strip()
