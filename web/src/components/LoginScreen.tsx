import { useState, type FormEvent } from "react";

import { DeviceIcon, ShieldIcon, SparklesIcon } from "./Icons";

type LoginScreenProps = {
  loading: boolean;
  error: string;
  onLogin: (userId: string, password: string) => Promise<void>;
};

export function LoginScreen({ loading, error, onLogin }: LoginScreenProps) {
  const [userId, setUserId] = useState("");
  const [password, setPassword] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onLogin(userId.trim(), password);
  }

  return (
    <main className="login-page">
      <section className="login-showcase" aria-label="产品介绍">
        <div className="brand-lockup brand-lockup--light">
          <span className="brand-mark"><DeviceIcon /></span>
          <span>CleanPilot AI</span>
        </div>
        <div className="showcase-content">
          <span className="eyebrow eyebrow--dark"><SparklesIcon /> 多 Agent 服务中枢</span>
          <h1>让每一次清洁，<br />都有专业判断。</h1>
          <p>从产品咨询、故障诊断到个性化使用报告，专业 Agent 团队为你的设备持续服务。</p>
          <div className="capability-list">
            <div><span>01</span><p><strong>智能分诊</strong>精准识别问题并交给对应专家</p></div>
            <div><span>02</span><p><strong>知识增强</strong>基于产品资料提供有依据的建议</p></div>
            <div><span>03</span><p><strong>账户隔离</strong>仅查询当前登录用户的设备数据</p></div>
          </div>
        </div>
        <p className="showcase-footnote">Autonomous Cleaning Intelligence · 2026</p>
      </section>

      <section className="login-panel">
        <div className="login-card">
          <div className="mobile-brand brand-lockup">
            <span className="brand-mark"><DeviceIcon /></span>
            <span>CleanPilot AI</span>
          </div>
          <span className="eyebrow"><ShieldIcon /> 安全服务入口</span>
          <h2>欢迎回来</h2>
          <p className="login-subtitle">登录后查看你的设备状态并开始智能服务。</p>

          <form onSubmit={handleSubmit}>
            <label htmlFor="user-id">用户 ID</label>
            <input
              id="user-id"
              autoComplete="username"
              inputMode="text"
              placeholder="请输入用户 ID"
              value={userId}
              onChange={(event) => setUserId(event.target.value)}
              disabled={loading}
              required
            />
            <label htmlFor="password">密码</label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              placeholder="请输入登录密码"
              minLength={8}
              maxLength={128}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              disabled={loading}
              required
            />
            {error && <div className="form-error" role="alert">{error}</div>}
            <button className="primary-button" type="submit" disabled={loading || !userId || !password}>
              {loading ? <span className="button-loader" /> : "进入服务中心"}
            </button>
          </form>

          <div className="login-security-note">
            <ShieldIcon />
            <span>密码经安全哈希校验，登录状态仅保留在当前浏览器标签页。</span>
          </div>
        </div>
      </section>
    </main>
  );
}
