from types import SimpleNamespace

import pytest

from evals.rag_retrieval import RetrievalCase, build_report, evaluate_retrieval, load_cases, source_name


class FakeRetriever:
    def __init__(self, documents_by_query):
        self.documents_by_query = documents_by_query

    def invoke(self, query):
        return self.documents_by_query[query]


def document(source):
    return SimpleNamespace(metadata={"source": source})


def test_load_cases_loads_the_project_dataset():
    cases = load_cases()

    assert len(cases) >= 15
    assert len({case.case_id for case in cases}) == len(cases)
    assert all(case.expected_sources for case in cases)


def test_load_cases_rejects_duplicate_ids(tmp_path):
    cases_path = tmp_path / "invalid_cases.json"
    cases_path.write_text(
        '[{"id":"duplicate","query":"a","expected_sources":["a.txt"]},'
        '{"id":"duplicate","query":"b","expected_sources":["b.txt"]}]',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="重复"):
        load_cases(cases_path)


def test_source_name_uses_only_the_file_name():
    assert source_name(document(r"F:\project\data\选购指南.txt")) == "选购指南.txt"


def test_evaluate_retrieval_calculates_recall_and_mrr():
    cases = [
        RetrievalCase("first", "q1", ("选购指南.txt",)),
        RetrievalCase("second", "q2", ("故障排除.txt",)),
        RetrievalCase("miss", "q3", ("维护保养.txt",)),
    ]
    retriever = FakeRetriever(
        {
            "q1": [document("data/选购指南.txt")],
            "q2": [document("data/无关资料.txt"), document("data/故障排除.txt")],
            "q3": [document("data/无关资料.txt")],
        }
    )

    report = build_report(evaluate_retrieval(cases, retriever), k=3)

    assert report["summary"] == {"case_count": 3, "recall_at_3": 0.6667, "mrr": 0.5, "hit_count": 2}
    assert [case["case_id"] for case in report["failed_cases"]] == ["miss"]
