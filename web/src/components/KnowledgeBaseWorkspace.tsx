import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  listKnowledgeDocuments,
  removeKnowledgeDocument,
  retryKnowledgeDocument,
  synchronizeKnowledgeDocuments,
  uploadKnowledgeDocument,
} from "../lib/api";
import type { CurrentUser, KnowledgeDocument } from "../types";
import {
  ArrowLeftIcon,
  DatabaseIcon,
  DeviceIcon,
  LogoutIcon,
  RefreshIcon,
  ShieldIcon,
  TrashIcon,
  UploadIcon,
} from "./Icons";

type KnowledgeBaseWorkspaceProps = {
  token: string;
  user: CurrentUser;
  onBack: () => void;
  onLogout: () => void;
};

const STATUS_LABELS: Record<string, string> = {
  indexed: "已入库",
  failed: "入库失败",
  blocked: "安全拦截",
  removed: "已移除",
};

function formatTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function KnowledgeBaseWorkspace({
  token,
  user,
  onBack,
  onLogout,
}: KnowledgeBaseWorkspaceProps) {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeAction, setActiveAction] = useState("");
  const [notice, setNotice] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleError = useCallback((error: unknown) => {
    if (error instanceof ApiError && error.status === 401) {
      onLogout();
      return;
    }
    setNotice({
      type: "error",
      text: error instanceof Error ? error.message : "操作失败，请稍后重试。",
    });
  }, [onLogout]);

  const loadDocuments = useCallback(async () => {
    try {
      setDocuments(await listKnowledgeDocuments(token));
    } catch (error) {
      handleError(error);
    } finally {
      setLoading(false);
    }
  }, [handleError, token]);

  useEffect(() => {
    void loadDocuments();
  }, [loadDocuments]);

  async function synchronize() {
    setActiveAction("sync");
    setNotice(null);
    try {
      const result = await synchronizeKnowledgeDocuments(token);
      setDocuments(result);
      setNotice({ type: "success", text: `同步完成，已接管 ${result.length} 个知识文件。` });
    } catch (error) {
      handleError(error);
    } finally {
      setActiveAction("");
    }
  }

  async function upload(file: File | undefined) {
    if (!file) return;
    setActiveAction("upload");
    setNotice(null);
    try {
      const result = await uploadKnowledgeDocument(token, file);
      await loadDocuments();
      setNotice({
        type: result.status === "indexed" ? "success" : "error",
        text: result.status === "indexed"
          ? `${result.filename} 已安全入库，共 ${result.chunk_count} 个片段。`
          : result.failure_reason || `${result.filename} 未能完成入库。`,
      });
    } catch (error) {
      handleError(error);
    } finally {
      setActiveAction("");
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function retry(document: KnowledgeDocument) {
    setActiveAction(`retry:${document.document_id}`);
    setNotice(null);
    try {
      const updated = await retryKnowledgeDocument(token, document.document_id);
      setDocuments((current) => current.map((item) => (
        item.document_id === updated.document_id ? updated : item
      )));
      setNotice({
        type: updated.status === "indexed" ? "success" : "error",
        text: updated.status === "indexed"
          ? `${updated.filename} 已重新入库。`
          : updated.failure_reason || "重新入库失败。",
      });
    } catch (error) {
      handleError(error);
    } finally {
      setActiveAction("");
    }
  }

  async function remove(document: KnowledgeDocument) {
    if (!window.confirm(`确认从向量索引移除“${document.filename}”吗？原始文件会保留。`)) return;
    setActiveAction(`remove:${document.document_id}`);
    setNotice(null);
    try {
      await removeKnowledgeDocument(token, document.document_id);
      await loadDocuments();
      setNotice({ type: "success", text: `${document.filename} 已从向量索引移除。` });
    } catch (error) {
      handleError(error);
    } finally {
      setActiveAction("");
    }
  }

  const indexedCount = documents.filter((document) => document.status === "indexed").length;
  const blockedCount = documents.filter((document) => document.status === "blocked").length;
  const chunkCount = documents.reduce((total, document) => total + document.chunk_count, 0);

  return (
    <main className="admin-workspace">
      <aside className="admin-sidebar">
        <div className="brand-lockup brand-lockup--light">
          <span className="brand-mark"><DeviceIcon /></span><span>CleanPilot AI</span>
        </div>
        <div className="admin-identity">
          <span className="user-avatar">{user.display_name.slice(0, 1)}</span>
          <div><strong>{user.display_name}</strong><small>系统管理员 · {user.user_id}</small></div>
        </div>
        <nav className="admin-navigation">
          <button type="button" onClick={onBack}><ArrowLeftIcon /> 返回智能客服</button>
          <button type="button" className="admin-navigation--active"><DatabaseIcon /> 知识库运营</button>
        </nav>
        <div className="admin-security-note">
          <ShieldIcon />
          <div><strong>管理员安全域</strong><span>所有写操作均由后端角色校验</span></div>
        </div>
        <button type="button" className="admin-logout" onClick={onLogout}><LogoutIcon /> 退出登录</button>
      </aside>

      <section className="admin-content">
        <header className="admin-header">
          <div><span>KNOWLEDGE OPERATIONS</span><h1>知识库运营中心</h1><p>管理资料安全扫描、向量索引与入库状态</p></div>
          <div className="admin-actions">
            <button type="button" className="secondary-action" onClick={() => void synchronize()} disabled={Boolean(activeAction)}>
              <RefreshIcon /> {activeAction === "sync" ? "正在同步" : "同步项目文件"}
            </button>
            <label className={`primary-action ${activeAction ? "primary-action--disabled" : ""}`}>
              <UploadIcon /> {activeAction === "upload" ? "正在入库" : "上传 TXT / PDF"}
              <input
                ref={fileInputRef}
                type="file"
                accept=".txt,.pdf"
                disabled={Boolean(activeAction)}
                onChange={(event) => void upload(event.target.files?.[0])}
              />
            </label>
          </div>
        </header>

        {notice && <div className={`admin-notice admin-notice--${notice.type}`}>{notice.text}</div>}

        <div className="knowledge-stats">
          <article><span>知识文件</span><strong>{documents.length}</strong><small>已登记资料总数</small></article>
          <article><span>正常索引</span><strong>{indexedCount}</strong><small>可参与 RAG 检索</small></article>
          <article><span>知识片段</span><strong>{chunkCount}</strong><small>当前有效切片数量</small></article>
          <article><span>安全拦截</span><strong>{blockedCount}</strong><small>疑似提示注入文件</small></article>
        </div>

        <section className="knowledge-panel">
          <div className="knowledge-panel-heading">
            <div><h2>文档状态</h2><p>上传内容限制为 TXT/PDF，单文件最大 10 MB。</p></div>
            <button type="button" className="icon-action" onClick={() => void loadDocuments()} disabled={loading || Boolean(activeAction)} aria-label="刷新列表"><RefreshIcon /></button>
          </div>

          {loading ? (
            <div className="knowledge-empty">正在读取知识库状态…</div>
          ) : !documents.length ? (
            <div className="knowledge-empty"><DatabaseIcon /><strong>尚未接管知识文件</strong><span>点击“同步项目文件”建立运营状态。</span></div>
          ) : (
            <div className="knowledge-table-wrap">
              <table className="knowledge-table">
                <thead><tr><th>文件</th><th>状态</th><th>片段</th><th>风险</th><th>更新时间</th><th>操作</th></tr></thead>
                <tbody>
                  {documents.map((document) => (
                    <tr key={document.document_id}>
                      <td><strong>{document.filename}</strong>{document.failure_reason && <small>{document.failure_reason}</small>}</td>
                      <td><span className={`document-status document-status--${document.status}`}>{STATUS_LABELS[document.status] || document.status}</span></td>
                      <td>{document.chunk_count}</td>
                      <td>{document.risk_level === "none" ? "正常" : document.risk_level}</td>
                      <td>{formatTime(document.updated_at)}</td>
                      <td>
                        <div className="document-actions">
                          <button type="button" onClick={() => void retry(document)} disabled={Boolean(activeAction)}><RefreshIcon /> {activeAction === `retry:${document.document_id}` ? "处理中" : "重新入库"}</button>
                          <button type="button" className="danger-action" onClick={() => void remove(document)} disabled={Boolean(activeAction) || document.status === "removed"}><TrashIcon /> 移除</button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </section>
    </main>
  );
}
