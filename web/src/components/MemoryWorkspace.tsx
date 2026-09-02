import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiError, deleteMemory, listMemories, updateMemory } from "../lib/api";
import type { CurrentUser, MemoryItem } from "../types";
import {
  ArrowLeftIcon,
  DeviceIcon,
  EditIcon,
  LogoutIcon,
  MemoryIcon,
  ShieldIcon,
  TrashIcon,
} from "./Icons";

type MemoryWorkspaceProps = {
  token: string;
  user: CurrentUser;
  onBack: () => void;
  onLogout: () => void;
};

type MemoryFilter = "all" | "profile" | "episodic";

const TYPE_LABELS: Record<string, string> = {
  profile: "用户画像",
  episodic: "服务事件",
};

function formatTime(value: string | null): string {
  if (!value) return "长期保留";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(value));
}

export function MemoryWorkspace({ token, user, onBack, onLogout }: MemoryWorkspaceProps) {
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [filter, setFilter] = useState<MemoryFilter>("all");
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState("");
  const [draft, setDraft] = useState("");
  const [activeAction, setActiveAction] = useState("");
  const [notice, setNotice] = useState<{ type: "success" | "error"; text: string } | null>(null);

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

  const loadMemories = useCallback(async () => {
    try {
      setMemories(await listMemories(token));
    } catch (error) {
      handleError(error);
    } finally {
      setLoading(false);
    }
  }, [handleError, token]);

  useEffect(() => {
    void loadMemories();
  }, [loadMemories]);

  const visibleMemories = useMemo(
    () => memories.filter((memory) => filter === "all" || memory.memory_type === filter),
    [filter, memories],
  );

  function beginEdit(memory: MemoryItem) {
    setEditingId(memory.memory_id);
    setDraft(memory.content);
    setNotice(null);
  }

  async function save(memory: MemoryItem) {
    if (!draft.trim()) return;
    setActiveAction(`save:${memory.memory_id}`);
    try {
      const updated = await updateMemory(token, memory.memory_id, draft.trim());
      setMemories((current) => current.map((item) => (
        item.memory_id === updated.memory_id ? updated : item
      )));
      setEditingId("");
      setNotice({ type: "success", text: "记忆已更新，新版本将在后续对话中生效。" });
    } catch (error) {
      handleError(error);
    } finally {
      setActiveAction("");
    }
  }

  async function remove(memory: MemoryItem) {
    if (!window.confirm("确认让 CleanPilot AI 遗忘这条内容吗？")) return;
    setActiveAction(`delete:${memory.memory_id}`);
    try {
      await deleteMemory(token, memory.memory_id);
      setMemories((current) => current.filter((item) => item.memory_id !== memory.memory_id));
      setNotice({ type: "success", text: "该条记忆已删除，后续对话不会再调用。" });
    } catch (error) {
      handleError(error);
    } finally {
      setActiveAction("");
    }
  }

  const profileCount = memories.filter((memory) => memory.memory_type === "profile").length;
  const episodeCount = memories.filter((memory) => memory.memory_type === "episodic").length;

  return (
    <main className="admin-workspace">
      <aside className="admin-sidebar">
        <div className="brand-lockup brand-lockup--light">
          <span className="brand-mark"><DeviceIcon /></span><span>CleanPilot AI</span>
        </div>
        <div className="admin-identity">
          <span className="user-avatar">{user.display_name.slice(0, 1)}</span>
          <div><strong>{user.display_name}</strong><small>记忆所有者 · {user.user_id}</small></div>
        </div>
        <nav className="admin-navigation">
          <button type="button" onClick={onBack}><ArrowLeftIcon /> 返回智能客服</button>
          <button type="button" className="admin-navigation--active"><MemoryIcon /> 我的记忆</button>
        </nav>
        <div className="admin-security-note">
          <ShieldIcon />
          <div><strong>账户隔离</strong><span>只能查看和管理当前账户的记忆</span></div>
        </div>
        <button type="button" className="admin-logout" onClick={onLogout}><LogoutIcon /> 退出登录</button>
      </aside>

      <section className="admin-content">
        <header className="admin-header">
          <div><span>MEMORY CONTROL</span><h1>我的记忆</h1><p>查看、修正或删除 AI 在服务过程中保留的信息</p></div>
        </header>

        {notice && <div className={`admin-notice admin-notice--${notice.type}`}>{notice.text}</div>}

        <div className="memory-stats">
          <article><span>有效记忆</span><strong>{memories.length}</strong><small>当前可被 Agent 召回</small></article>
          <article><span>用户画像</span><strong>{profileCount}</strong><small>明确表达的偏好与环境</small></article>
          <article><span>服务事件</span><strong>{episodeCount}</strong><small>同设备历史故障处理</small></article>
        </div>

        <section className="knowledge-panel">
          <div className="memory-toolbar">
            <div><h2>记忆清单</h2><p>画像长期保留；故障事件默认 180 天后自动过期。</p></div>
            <div className="memory-filters">
              {(["all", "profile", "episodic"] as MemoryFilter[]).map((item) => (
                <button
                  type="button"
                  className={filter === item ? "memory-filter--active" : ""}
                  key={item}
                  onClick={() => setFilter(item)}
                >
                  {item === "all" ? "全部" : TYPE_LABELS[item]}
                </button>
              ))}
            </div>
          </div>

          {loading ? (
            <div className="knowledge-empty">正在读取账户记忆…</div>
          ) : !visibleMemories.length ? (
            <div className="knowledge-empty"><MemoryIcon /><strong>暂无相关记忆</strong><span>在对话中明确描述家庭环境、清洁偏好或故障情况后，这里会出现可管理记录。</span></div>
          ) : (
            <div className="memory-grid">
              {visibleMemories.map((memory) => (
                <article className="memory-card" key={memory.memory_id}>
                  <div className="memory-card-heading">
                    <span className={`memory-type memory-type--${memory.memory_type}`}>{TYPE_LABELS[memory.memory_type] || memory.memory_type}</span>
                    <small>版本 {memory.version}</small>
                  </div>
                  {editingId === memory.memory_id ? (
                    <textarea value={draft} maxLength={2000} onChange={(event) => setDraft(event.target.value)} />
                  ) : (
                    <p>{memory.content}</p>
                  )}
                  <div className="memory-meta">
                    <span>{memory.device_id ? `设备 ${memory.device_id}` : "账户级"}</span>
                    <span>{memory.expires_at ? `有效至 ${formatTime(memory.expires_at)}` : "长期保留"}</span>
                  </div>
                  <div className="memory-actions">
                    {editingId === memory.memory_id ? (
                      <>
                        <button type="button" onClick={() => setEditingId("")}>取消</button>
                        <button type="button" className="memory-save" disabled={Boolean(activeAction) || !draft.trim()} onClick={() => void save(memory)}>
                          {activeAction === `save:${memory.memory_id}` ? "保存中" : "保存修改"}
                        </button>
                      </>
                    ) : (
                      <>
                        <button type="button" onClick={() => beginEdit(memory)}><EditIcon /> 修改</button>
                        <button type="button" className="danger-action" disabled={Boolean(activeAction)} onClick={() => void remove(memory)}><TrashIcon /> 遗忘</button>
                      </>
                    )}
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </section>
    </main>
  );
}
