from storage.support_repository import SupportRepository


def test_knowledge_document_state_is_upserted_by_source_path(tmp_path):
    repository = SupportRepository(tmp_path / "support.db")
    common_fields = {
        "document_id": "doc-1",
        "source_path": tmp_path / "data" / "指南.txt",
        "filename": "指南.txt",
        "content_hash": "hash-1",
    }

    repository.save_knowledge_document(status="failed", failure_reason="network", **common_fields)
    document = repository.save_knowledge_document(status="indexed", chunk_count=8, **common_fields)

    assert len(repository.list_knowledge_documents()) == 1
    assert document.status == "indexed"
    assert document.chunk_count == 8
    assert document.failure_reason is None
