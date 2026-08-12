"""使用标注的源级别数据集对 RAG 检索器进行评估。"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES_PATH = Path(__file__).with_name("rag_cases.json")
DEFAULT_REPORT_PATH = PROJECT_ROOT / "evals" / "reports" / "retrieval_report.json"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class Retriever(Protocol):
    def invoke(self, query: str) -> Sequence[Any]:
        """返回查询文件结果。"""


@dataclass(frozen=True)
class RetrievalCase:
    case_id: str
    query: str
    expected_sources: tuple[str, ...]


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    query: str
    expected_sources: tuple[str, ...]
    retrieved_sources: tuple[str, ...]
    hit: bool
    reciprocal_rank: float


def load_cases(path: str | Path = DEFAULT_CASES_PATH) -> list[RetrievalCase]:
    """
    加载并验证源代码级检索评估案例
    """
    with Path(path).open("r", encoding="utf-8") as file:
        raw_cases = json.load(file)

    if not isinstance(raw_cases, list):
        raise ValueError("评测集必须是 JSON 数组")

    cases: list[RetrievalCase] = []
    case_ids: set[str] = set()
    for index, raw_case in enumerate(raw_cases, start=1):
        if not isinstance(raw_case, dict):
            raise ValueError(f"第 {index} 条评测用例不是对象")

        case_id = raw_case.get("id")
        query = raw_case.get("query")
        expected_sources = raw_case.get("expected_sources")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"第 {index} 条评测用例缺少 id")
        if case_id in case_ids:
            raise ValueError(f"评测用例 id 重复：{case_id}")
        if not isinstance(query, str) or not query.strip():
            raise ValueError(f"评测用例 {case_id} 缺少 query")
        if not isinstance(expected_sources, list) or not expected_sources:
            raise ValueError(f"评测用例 {case_id} 缺少 expected_sources")
        if not all(isinstance(source, str) and source.strip() for source in expected_sources):
            raise ValueError(f"评测用例 {case_id} 的 expected_sources 格式无效")

        case_ids.add(case_id)
        cases.append(
            RetrievalCase(
                case_id=case_id,
                query=query,
                expected_sources=tuple(expected_sources),
            )
        )
    return cases


def source_name(document: Any) -> str:
    """将LangChain文档源规范化为其文件名。"""
    metadata = getattr(document, "metadata", {})
    if not isinstance(metadata, dict):
        return ""
    source = metadata.get("source", "")
    return Path(str(source)).name if source else ""


def evaluate_retrieval(cases: Sequence[RetrievalCase], retriever: Retriever) -> list[CaseResult]:
    """计算每个案例的源级命中结果和互逆排名。"""
    results: list[CaseResult] = []
    for case in cases:
        retrieved_sources = tuple(
            source for source in (source_name(document) for document in retriever.invoke(case.query)) if source
        )
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
                retrieved_sources=retrieved_sources,
                hit=first_rank is not None,
                reciprocal_rank=0.0 if first_rank is None else 1 / first_rank,
            )
        )
    return results


def summarize_results(results: Sequence[CaseResult], k: int) -> dict[str, float | int]:
    """返回所评估案例的Recall@K和MRR值。"""
    if not results:
        raise ValueError("评测结果为空")

    hit_count = sum(result.hit for result in results)
    return {
        "case_count": len(results),
        f"recall_at_{k}": round(hit_count / len(results), 4),
        "mrr": round(sum(result.reciprocal_rank for result in results) / len(results), 4),
        "hit_count": hit_count,
    }


def build_report(results: Sequence[CaseResult], k: int) -> dict[str, Any]:
    """首先构建一份包含失败用例的可序列化评估报告。"""
    return {
        "summary": summarize_results(results, k),
        "failed_cases": [asdict(result) for result in results if not result.hit],
        "results": [asdict(result) for result in results],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="运行 Chroma RAG 检索评测")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH, help="评测集 JSON 路径")
    parser.add_argument("--k", type=int, default=None, help="检索 Top-K；默认使用 Chroma 配置")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH, help="报告输出路径")
    args = parser.parse_args()

    from rag.vector_store import VectorStoreService

    vector_store = VectorStoreService()
    retriever = vector_store.vector_store.as_retriever(search_kwargs={"k": args.k}) if args.k else vector_store.get_retriever()
    try:
        results = evaluate_retrieval(load_cases(args.cases), retriever)
    except Exception as error:
        raise SystemExit(
            "真实检索评测未完成：无法调用当前 Embedding 服务。"
            "请检查 DASHSCOPE_API_KEY、网络连接和服务可用性后重试。"
            f"原始错误：{error}"
        ) from error
    report = build_report(results, args.k or 3)

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = report["summary"]
    print(f"评测样本：{summary['case_count']}")
    print(f"Recall@{args.k or 3}：{summary[f'recall_at_{args.k or 3}']:.2%}")
    print(f"MRR：{summary['mrr']:.4f}")
    print(f"失败样本：{len(report['failed_cases'])}")
    print(f"报告已写入：{args.report}")


if __name__ == "__main__":
    main()
