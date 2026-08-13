"""Knowledge-base operations view for Streamlit."""

from __future__ import annotations

import streamlit as st

from rag.knowledge_service import KnowledgeBaseService
from rag.vector_store import VectorStoreService
from storage.support_repository import SupportRepository


def render_knowledge_base_page() -> None:
    repository = SupportRepository()
    service = KnowledgeBaseService(VectorStoreService(), repository)

    st.header("知识库运营")
    st.caption("上传文件会先进行提示注入扫描；仅成功完成全部向量写入后才会标记为已入库。")

    action_columns = st.columns(2)
    if action_columns[0].button("同步项目知识文件", use_container_width=True):
        with st.spinner("正在校验并同步知识库..."):
            records = service.synchronize_existing_documents()
        indexed_count = sum(record.status == "indexed" for record in records)
        st.success(f"同步完成：{indexed_count}/{len(records)} 个文件处于已入库状态。")

    uploaded_file = st.file_uploader("上传 TXT 或 PDF 知识文件", type=["txt", "pdf"])
    if uploaded_file and action_columns[1].button("安全上传并入库", use_container_width=True):
        with st.spinner("正在扫描并写入向量库..."):
            try:
                record = service.ingest_upload(uploaded_file.name, uploaded_file.getvalue())
            except (OSError, ValueError) as error:
                st.error(f"上传失败：{error}")
            else:
                if record.status == "indexed":
                    st.success(f"{record.filename} 已入库，共 {record.chunk_count} 个片段。")
                elif record.status == "blocked":
                    st.warning(record.failure_reason)
                else:
                    st.error(f"入库失败：{record.failure_reason}")

    documents = service.list_documents()
    if not documents:
        st.info("尚未记录知识文件状态，点击“同步项目知识文件”开始接管现有索引。")
        return

    display_rows = [
        {
            "文件名": document.filename,
            "状态": document.status,
            "片段数": document.chunk_count,
            "风险": document.risk_level,
            "失败原因": document.failure_reason or "-",
            "更新时间": document.updated_at,
        }
        for document in documents
    ]
    st.dataframe(display_rows, use_container_width=True, hide_index=True)

    available_documents = {f"{document.filename} · {document.status}": document for document in documents}
    selected_label = st.selectbox("选择要维护的文件", available_documents)
    selected_document = available_documents[selected_label]
    maintenance_columns = st.columns(2)

    if maintenance_columns[0].button("重新入库所选文件", use_container_width=True):
        with st.spinner("正在重新写入所选文件..."):
            record = service.index_file(selected_document.source_path)
        if record.status == "indexed":
            st.success(f"重新入库成功：{record.chunk_count} 个片段。")
        else:
            st.error(record.failure_reason or "重新入库失败")

    if maintenance_columns[1].button("从索引移除所选文件", use_container_width=True):
        service.remove_from_index(selected_document.document_id)
        st.success("已从 Chroma 索引移除；原始文件未被删除。")
