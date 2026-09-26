"""对向量、关键词、混合召回和精排链路执行可复现的离线评测。"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence

from langchain_core.documents import Document


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES_PATH = Path(__file__).with_name("rag_cases.json")
DEFAULT_REPORT_PATH = PROJECT_ROOT / "evals" / "reports" / "retrieval_report.json"
DEFAULT_K_VALUES = (3, 5, 10, 20)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class Retriever(Protocol):
    def invoke(self, query: str) -> Sequence[Any]:
        """返回按相关性排序的检索结果。"""


class CachedVectorStore:
    """在一次消融评测中复用同一问题的向量召回，减少外部 API 调用。"""

    def __init__(self, vector_store: Any, cache_path: Path):
        self.vector_store = vector_store
        self.cache_path = cache_path
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache: dict[str, list[dict[str, Any]]] = {}
        if self.cache_path.exists():
            try:
                self.cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self.cache = {}

    def similarity_search(self, query: str, k: int):
        key = f"{k}:{query}"
        if key not in self.cache:
            last_error: Exception | None = None
            documents = None
            for attempt in range(3):
                try:
                    documents = self.vector_store.similarity_search(query, k=k)
                    break
                except Exception as error:
                    last_error = error
                    if attempt < 2:
                        time.sleep(2 ** attempt)
            if documents is None:
                raise RuntimeError(str(last_error))
            self.cache[key] = [
                {"page_content": document.page_content, "metadata": document.metadata}
                for document in documents
            ]
            temporary_path = self.cache_path.with_suffix(".tmp")
            temporary_path.write_text(
                json.dumps(self.cache, ensure_ascii=False),
                encoding="utf-8",
            )
            for attempt in range(5):
                try:
                    temporary_path.replace(self.cache_path)
                    break
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.2 * (attempt + 1))
        return [
            Document(page_content=item["page_content"], metadata=item["metadata"])
            for item in self.cache[key]
        ]


class CachedRetriever:
    """为高成本精排请求保存可恢复检查点，并跳过降级结果。"""

    def __init__(self, retriever: Retriever, cache_path: Path):
        self.retriever = retriever
        self.cache_path = cache_path
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.cache: dict[str, list[dict[str, Any]]] = {}
        if self.cache_path.exists():
            try:
                self.cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self.cache = {}

    def invoke(self, query: str) -> list[Document]:
        with self.lock:
            cached = self.cache.get(query)
        if cached is not None:
            return [
                Document(page_content=item["page_content"], metadata=item["metadata"])
                for item in cached
            ]
        documents = list(self.retriever.invoke(query))
        if any(document.metadata.get("rerank_fallback") for document in documents):
            return documents
        serialized = [
            {"page_content": document.page_content, "metadata": document.metadata}
            for document in documents
        ]
        with self.lock:
            self.cache[query] = serialized
            self.cache_path.write_text(
                json.dumps(self.cache, ensure_ascii=False),
                encoding="utf-8",
            )
        return documents


@dataclass(frozen=True)
class RetrievalCase:
    case_id: str
    query: str
    expected_sources: tuple[str, ...]
    category: str = "general"
    split: str = "dev"


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    query: str
    expected_sources: tuple[str, ...]
    retrieved_sources: tuple[str, ...]
    category: str
    split: str
    first_relevant_rank: int | None
    rerank_fallback: bool = False

    @property
    def hit(self) -> bool:
        return self.first_relevant_rank is not None

    @property
    def reciprocal_rank(self) -> float:
        return 0.0 if self.first_relevant_rank is None else 1 / self.first_relevant_rank


def load_cases(path: str | Path = DEFAULT_CASES_PATH) -> list[RetrievalCase]:
    """加载普通列表或按查询组组织的评测集，并验证 ID 唯一性。"""
    with Path(path).open("r", encoding="utf-8") as file:
        raw_cases = json.load(file)
    if not isinstance(raw_cases, list):
        raise ValueError("评测集必须是 JSON 数组")

    cases: list[RetrievalCase] = []
    case_ids: set[str] = set()
    for index, raw_case in enumerate(raw_cases, start=1):
        if not isinstance(raw_case, dict):
            raise ValueError(f"第 {index} 条评测用例不是对象")
        queries = raw_case.get("queries")
        if queries is None:
            queries = [raw_case.get("query")]
        if not isinstance(queries, list) or not queries:
            raise ValueError(f"第 {index} 条评测用例缺少 query 或 queries")

        base_id = raw_case.get("id") or raw_case.get("id_prefix")
        expected_sources = raw_case.get("expected_sources")
        if not isinstance(base_id, str) or not base_id.strip():
            raise ValueError(f"第 {index} 条评测用例缺少 id")
        if not isinstance(expected_sources, list) or not expected_sources:
            raise ValueError(f"评测用例 {base_id} 缺少 expected_sources")
        if not all(isinstance(source, str) and source.strip() for source in expected_sources):
            raise ValueError(f"评测用例 {base_id} 的 expected_sources 格式无效")

        for query_index, query in enumerate(queries, start=1):
            case_id = base_id if len(queries) == 1 else f"{base_id}-{query_index:02d}"
            if case_id in case_ids:
                raise ValueError(f"评测用例 id 重复：{case_id}")
            if not isinstance(query, str) or not query.strip():
                raise ValueError(f"评测用例 {case_id} 缺少 query")
            case_ids.add(case_id)
            cases.append(
                RetrievalCase(
                    case_id=case_id,
                    query=query,
                    expected_sources=tuple(expected_sources),
                    category=str(raw_case.get("category", "general")),
                    split=str(raw_case.get("split", "dev")),
                )
            )
    return cases


def source_names(document: Any) -> tuple[str, ...]:
    """从单来源或多来源元数据中提取不重复的文件名。"""
    metadata = getattr(document, "metadata", {})
    if not isinstance(metadata, dict):
        return ()
    names = metadata.get("source_names")
    if isinstance(names, list):
        return tuple(dict.fromkeys(Path(str(name)).name for name in names if name))
    source = metadata.get("source_name") or metadata.get("source", "")
    return (Path(str(source)).name,) if source else ()


def source_name(document: Any) -> str:
    """兼容旧调用：返回检索结果的第一个来源文件名。"""
    names = source_names(document)
    return names[0] if names else ""


def evaluate_retrieval(cases: Sequence[RetrievalCase], retriever: Retriever) -> list[CaseResult]:
    """记录首个相关来源的排名，并对同一来源的多个片段去重。"""
    results: list[CaseResult] = []
    for case in cases:
        retrieved_sources: list[str] = []
        documents = list(retriever.invoke(case.query))
        for document in documents:
            for source in source_names(document):
                if source not in retrieved_sources:
                    retrieved_sources.append(source)
        expected_sources = set(case.expected_sources)
        first_rank = next(
            (rank for rank, source in enumerate(retrieved_sources, start=1) if source in expected_sources),
            None,
        )
        results.append(
            CaseResult(
                case_id=case.case_id,
                query=case.query,
                expected_sources=case.expected_sources,
                retrieved_sources=tuple(retrieved_sources),
                category=case.category,
                split=case.split,
                first_relevant_rank=first_rank,
                rerank_fallback=any(
                    bool(getattr(document, "metadata", {}).get("rerank_fallback"))
                    for document in documents
                ),
            )
        )
    return results


def _ndcg_at_k(result: CaseResult, k: int) -> float:
    expected = set(result.expected_sources)
    gains = [1.0 if source in expected else 0.0 for source in result.retrieved_sources[:k]]
    dcg = sum(gain / math.log2(rank + 1) for rank, gain in enumerate(gains, start=1))
    ideal_count = min(len(expected), k)
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
    return 0.0 if ideal == 0 else dcg / ideal


def summarize_results(results: Sequence[CaseResult], k: int) -> dict[str, float | int]:
    """保留原有 Recall@K 与 MRR 摘要接口。"""
    if not results:
        raise ValueError("评测结果为空")
    hit_count = sum(
        result.first_relevant_rank is not None and result.first_relevant_rank <= k
        for result in results
    )
    return {
        "case_count": len(results),
        f"recall_at_{k}": round(hit_count / len(results), 4),
        "mrr": round(
            sum(
                0.0
                if result.first_relevant_rank is None or result.first_relevant_rank > k
                else 1 / result.first_relevant_rank
                for result in results
            ) / len(results),
            4,
        ),
        "hit_count": hit_count,
    }


def metric_summary(results: Sequence[CaseResult], k_values: Sequence[int]) -> dict[str, float | int]:
    """计算多组 Recall、MRR 与 nDCG，便于比较召回参数。"""
    if not results:
        raise ValueError("评测结果为空")
    summary: dict[str, float | int] = {"case_count": len(results)}
    summary["rerank_fallback_count"] = sum(result.rerank_fallback for result in results)
    for k in k_values:
        hits = sum(
            result.first_relevant_rank is not None and result.first_relevant_rank <= k
            for result in results
        )
        summary[f"recall_at_{k}"] = round(hits / len(results), 4)
        summary[f"mrr_at_{k}"] = round(
            sum(
                0.0
                if result.first_relevant_rank is None or result.first_relevant_rank > k
                else 1 / result.first_relevant_rank
                for result in results
            ) / len(results),
            4,
        )
        summary[f"ndcg_at_{k}"] = round(
            sum(_ndcg_at_k(result, k) for result in results) / len(results),
            4,
        )
    return summary


def build_report(
    results: Sequence[CaseResult],
    k: int = 3,
    *,
    k_values: Sequence[int] | None = None,
) -> dict[str, Any]:
    """构建包含总体、数据切分、类别及失败案例的报告。"""
    if k_values is None:
        return {
            "summary": summarize_results(results, k),
            "failed_cases": [asdict(result) for result in results if not result.hit],
            "results": [asdict(result) for result in results],
        }
    by_split = {
        split: metric_summary([result for result in results if result.split == split], k_values)
        for split in sorted({result.split for result in results})
    }
    by_category = {
        category: metric_summary([result for result in results if result.category == category], k_values)
        for category in sorted({result.category for result in results})
    }
    return {
        "summary": metric_summary(results, k_values),
        "by_split": by_split,
        "by_category": by_category,
        "failed_cases": [
            asdict(result)
            for result in results
            if result.first_relevant_rank is None or result.first_relevant_rank > min(k_values)
        ],
        "results": [asdict(result) for result in results],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="运行 RAG 混合检索与精排消融评测")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH, help="评测集 JSON 路径")
    parser.add_argument("--split", choices=["all", "dev", "test"], default="all")
    parser.add_argument(
        "--mode",
        choices=["all", "vector", "keyword", "hybrid", "hybrid_rerank"],
        default="all",
    )
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH, help="报告输出路径")
    parser.add_argument("--workers", type=int, default=4, help="精排评测并发数")
    args = parser.parse_args()

    from rag.vector_store import VectorStoreService

    cases = load_cases(args.cases)
    if args.split != "all":
        cases = [case for case in cases if case.split == args.split]
    modes = ["vector", "keyword", "hybrid", "hybrid_rerank"] if args.mode == "all" else [args.mode]
    vector_store = VectorStoreService()
    vector_store.vector_store = CachedVectorStore(
        vector_store.vector_store,
        PROJECT_ROOT / "evals" / "reports" / "vector_query_cache.json",
    )
    reports: dict[str, Any] = {}
    for mode in modes:
        retriever = vector_store.get_retriever(mode=mode, top_k=max(DEFAULT_K_VALUES))
        if mode == "hybrid_rerank":
            retriever = CachedRetriever(
                retriever,
                PROJECT_ROOT / "evals" / "reports" / "rerank_query_cache.json",
            )
        try:
            if mode == "hybrid_rerank" and args.workers > 1:
                with ThreadPoolExecutor(max_workers=args.workers) as executor:
                    results = list(
                        executor.map(
                            lambda case: evaluate_retrieval([case], retriever)[0],
                            cases,
                        )
                    )
            else:
                results = evaluate_retrieval(cases, retriever)
        except Exception as error:
            raise SystemExit(
                f"{mode} 检索评测未完成，请检查知识索引、DASHSCOPE_API_KEY 和网络连接。"
                f"原始错误：{error}"
            ) from error
        reports[mode] = build_report(results, k_values=DEFAULT_K_VALUES)
        summary = reports[mode]["summary"]
        print(
            f"{mode}: 样本 {summary['case_count']}，"
            f"Recall@3 {summary['recall_at_3']:.2%}，"
            f"Recall@10 {summary['recall_at_10']:.2%}，"
            f"MRR@3 {summary['mrr_at_3']:.4f}，"
            f"精排降级 {summary['rerank_fallback_count']}"
            , flush=True
        )

    report = {
        "dataset": {
            "case_count": len(cases),
            "split": args.split,
            "k_values": list(DEFAULT_K_VALUES),
        },
        "strategies": reports,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告已写入：{args.report}")


if __name__ == "__main__":
    main()
