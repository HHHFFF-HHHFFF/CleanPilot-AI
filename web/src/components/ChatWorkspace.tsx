import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import ReactMarkdown from "react-markdown";

import { ApiError, streamChat } from "../lib/api";
import type { AgentEvent, ChatMessage, CurrentUser, LocationProfile } from "../types";
import { useLocationWeather, type LocationStatus } from "../hooks/useLocationWeather";
import {
  ChevronIcon,
  DeviceIcon,
  LocationIcon,
  LogoutIcon,
  SendIcon,
  ShieldIcon,
  SparklesIcon,
  StopIcon,
  WeatherIcon,
} from "./Icons";

type ChatWorkspaceProps = {
  token: string;
  user: CurrentUser;
  onLogout: () => void;
};

const QUICK_PROMPTS = [
  "我的设备本月清洁表现怎么样？",
  "扫地机器人回充失败怎么排查？",
  "家里有宠物，应该如何维护主刷？",
];

const AGENT_LABELS: Record<string, string> = {
  router_agent: "智能调度",
  knowledge_agent: "知识顾问",
  diagnosis_agent: "诊断专家",
  customer_agent: "用户运营",
};

function createId(): string {
  return crypto.randomUUID();
}

function formatDate(value?: string): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "short", day: "numeric" }).format(
    new Date(`${value}T00:00:00`),
  );
}

function TracePanel({ traces, pending }: { traces: string[]; pending: boolean }) {
  const [expanded, setExpanded] = useState(pending);

  useEffect(() => {
    setExpanded(pending);
  }, [pending]);

  if (!traces.length) return null;
  return (
    <div className={`trace-panel ${expanded ? "trace-panel--open" : ""}`}>
      <button type="button" className="trace-toggle" onClick={() => setExpanded((value) => !value)}>
        <span><SparklesIcon /> {pending ? "正在协同处理" : "查看处理摘要"}</span>
        <ChevronIcon />
      </button>
      {expanded && (
        <ol className="trace-list">
          {traces.map((trace, index) => <li key={`${trace}-${index}`}>{trace}</li>)}
        </ol>
      )}
    </div>
  );
}

function LocationCard({
  profile,
  status,
  onRefresh,
}: {
  profile: LocationProfile | null;
  status: LocationStatus;
  onRefresh: () => void;
}) {
  if ((status === "ready" || status === "fallback") && profile) {
    return (
      <div className="context-card context-card--weather">
        <div className="context-card-icon"><WeatherIcon /></div>
        <div>
          <span>{profile.city} · {profile.condition}</span>
          <strong>{profile.temperature ?? "—"}°</strong>
          <small>{status === "fallback" ? "账户城市" : "当前位置"} · 湿度 {profile.humidity ?? "—"}%</small>
        </div>
        <button type="button" className="text-button" onClick={onRefresh}>刷新</button>
      </div>
    );
  }

  const statusText = {
    requesting: "正在请求位置权限",
    loading: "正在读取本地天气",
    error: "定位天气暂不可用",
    fallback: "已使用账户城市天气",
    ready: "已获取本地天气",
  }[status];
  return (
    <div className="context-card">
      <div className="context-card-icon"><LocationIcon /></div>
      <div><span>环境上下文</span><small>{statusText}</small></div>
      {status === "error" && (
        <button type="button" className="text-button" onClick={onRefresh}>重试</button>
      )}
    </div>
  );
}

export function ChatWorkspace({ token, user, onLogout }: ChatWorkspaceProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: createId(),
      role: "assistant",
      content: `你好，${user.display_name}。我是智扫通智能服务助手。你可以咨询产品使用、故障排查，也可以让我生成设备使用报告。`,
      agent: "router_agent",
    },
  ]);
  const [input, setInput] = useState("");
  const [streamController, setStreamController] = useState<AbortController | null>(null);
  const messageEndRef = useRef<HTMLDivElement>(null);
  const { profile, status, refresh } = useLocationWeather(token, user.city, onLogout);
  const isStreaming = streamController !== null;

  useEffect(() => {
    messageEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function updateAssistant(messageId: string, event: AgentEvent) {
    setMessages((current) => current.map((message) => {
      if (message.id !== messageId) return message;
      if (event.type === "trace") {
        return { ...message, traces: [...(message.traces || []), event.content], agent: event.agent };
      }
      if (event.type === "answer") {
        return {
          ...message,
          content: `${message.content}${message.content ? "\n\n" : ""}${event.content}`,
          agent: event.agent,
        };
      }
      return { ...message, content: event.content, error: true };
    }));
  }

  async function sendMessage(preset?: string) {
    const query = (preset ?? input).trim();
    if (!query || isStreaming) return;
    const assistantId = createId();
    const controller = new AbortController();
    setInput("");
    setStreamController(controller);
    setMessages((current) => [
      ...current,
      { id: createId(), role: "user", content: query },
      { id: assistantId, role: "assistant", content: "", traces: [], pending: true },
    ]);

    try {
      await streamChat({
        token,
        query,
        locationProfile: profile,
        signal: controller.signal,
        onEvent: (event) => updateAssistant(assistantId, event),
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        updateAssistant(assistantId, { type: "error", content: "已停止本次回答。" });
      } else if (error instanceof ApiError && error.status === 401) {
        onLogout();
        return;
      } else {
        updateAssistant(assistantId, {
          type: "error",
          content: error instanceof Error ? error.message : "服务暂时不可用，请稍后重试。",
        });
      }
    } finally {
      setMessages((current) => current.map((message) => (
        message.id === assistantId ? { ...message, pending: false } : message
      )));
      setStreamController(null);
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void sendMessage();
    }
  }

  return (
    <main className="workspace">
      <aside className="sidebar">
        <div className="brand-lockup brand-lockup--light sidebar-brand">
          <span className="brand-mark"><DeviceIcon /></span><span>智扫通</span>
        </div>
        <nav className="sidebar-nav" aria-label="主要导航">
          <button type="button" className="nav-item nav-item--active"><SparklesIcon /> 智能服务</button>
          <button type="button" className="nav-item" disabled><DeviceIcon /> 我的设备 <small>即将开放</small></button>
        </nav>
        <div className="sidebar-spacer" />
        <div className="privacy-card">
          <ShieldIcon />
          <div><strong>隐私保护已开启</strong><span>身份与设备数据按账户隔离</span></div>
        </div>
        <button type="button" className="user-menu" onClick={onLogout} title="退出登录">
          <span className="user-avatar">{user.display_name.slice(0, 1)}</span>
          <span><strong>{user.display_name}</strong><small>ID {user.user_id}</small></span>
          <LogoutIcon />
        </button>
      </aside>

      <section className="service-shell">
        <header className="workspace-header">
          <div>
            <span className="mobile-wordmark">智扫通</span>
            <h1>智能服务中心</h1>
            <p><span className="online-dot" /> 4 位专业 Agent 在线协作</p>
          </div>
          <button type="button" className="mobile-logout" onClick={onLogout}><LogoutIcon /></button>
        </header>

        <div className="service-grid">
          <section className="chat-panel" aria-label="智能客服对话">
            <div className="message-list">
              {messages.map((message) => (
                <article key={message.id} className={`message-row message-row--${message.role}`}>
                  {message.role === "assistant" && <span className="assistant-avatar"><SparklesIcon /></span>}
                  <div className={`message-content ${message.error ? "message-content--error" : ""}`}>
                    {message.role === "assistant" && (
                      <span className="message-agent">
                        {AGENT_LABELS[message.agent || "router_agent"] || "智能服务"}
                      </span>
                    )}
                    {message.traces && <TracePanel traces={message.traces} pending={Boolean(message.pending)} />}
                    {message.content ? (
                      <div className="markdown-content"><ReactMarkdown>{message.content}</ReactMarkdown></div>
                    ) : message.pending ? (
                      <div className="typing-indicator"><i /><i /><i /></div>
                    ) : null}
                  </div>
                </article>
              ))}
              <div ref={messageEndRef} />
            </div>

            <div className="composer-area">
              {messages.length <= 1 && (
                <div className="quick-prompts">
                  {QUICK_PROMPTS.map((prompt) => (
                    <button type="button" key={prompt} onClick={() => void sendMessage(prompt)}>{prompt}</button>
                  ))}
                </div>
              )}
              <div className="composer">
                <textarea
                  aria-label="输入问题"
                  placeholder="描述你的问题，或让我生成本月使用报告…"
                  rows={1}
                  maxLength={4000}
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={handleKeyDown}
                  disabled={isStreaming}
                />
                {isStreaming ? (
                  <button type="button" className="send-button send-button--stop" onClick={() => streamController?.abort()} aria-label="停止回答">
                    <StopIcon />
                  </button>
                ) : (
                  <button type="button" className="send-button" onClick={() => void sendMessage()} disabled={!input.trim()} aria-label="发送消息">
                    <SendIcon />
                  </button>
                )}
              </div>
              <small className="composer-note">AI 生成内容仅供参考，重要故障请联系官方售后。</small>
            </div>
          </section>

          <aside className="context-rail">
            <section className="rail-section">
              <div className="rail-heading"><span>设备概览</span><i className="status-pill">在线</i></div>
              <div className="device-card">
                <div className="device-visual"><DeviceIcon /></div>
                <span>{user.device?.model || "尚未绑定设备"}</span>
                {user.device && <small>设备编号 {user.device.device_id}</small>}
              </div>
              {user.device && (
                <div className="device-facts">
                  <div><span>购买日期</span><strong>{formatDate(user.device.purchased_at)}</strong></div>
                  <div><span>保修截止</span><strong>{formatDate(user.device.warranty_until)}</strong></div>
                </div>
              )}
            </section>

            <section className="rail-section">
              <div className="rail-heading"><span>实时上下文</span></div>
              <LocationCard profile={profile} status={status} onRefresh={refresh} />
              <p className="location-note"><ShieldIcon /> 位置仅用于本次会话的天气建议，不写入知识库。</p>
            </section>

            <section className="rail-section agent-team">
              <div className="rail-heading"><span>Agent 团队</span></div>
              {[
                ["调", "智能调度", "识别任务并分派专家"],
                ["知", "知识顾问", "产品知识与使用建议"],
                ["诊", "诊断专家", "故障排查与安全升级"],
                ["运", "用户运营", "设备数据与使用报告"],
              ].map(([avatar, name, description]) => (
                <div className="agent-member" key={name}>
                  <span>{avatar}</span><div><strong>{name}</strong><small>{description}</small></div><i />
                </div>
              ))}
            </section>
          </aside>
        </div>
      </section>
    </main>
  );
}
