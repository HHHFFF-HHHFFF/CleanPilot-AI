import { useCallback, useEffect, useState } from "react";

import { ChatWorkspace } from "./components/ChatWorkspace";
import { KnowledgeBaseWorkspace } from "./components/KnowledgeBaseWorkspace";
import { LoginScreen } from "./components/LoginScreen";
import { ApiError, getCurrentUser, login } from "./lib/api";
import type { CurrentUser } from "./types";

const TOKEN_KEY = "cleaning_support_access_token";

export default function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem(TOKEN_KEY) || "");
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [booting, setBooting] = useState(Boolean(token));
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginError, setLoginError] = useState("");
  const [workspace, setWorkspace] = useState<"chat" | "knowledge">("chat");

  const logout = useCallback(() => {
    sessionStorage.removeItem(TOKEN_KEY);
    setToken("");
    setUser(null);
    setBooting(false);
    setWorkspace("chat");
  }, []);

  useEffect(() => {
    if (!token) return;
    let active = true;
    getCurrentUser(token)
      .then((profile) => {
        if (active) setUser(profile);
      })
      .catch(() => {
        if (active) logout();
      })
      .finally(() => {
        if (active) setBooting(false);
      });
    return () => {
      active = false;
    };
  }, [logout, token]);

  async function handleLogin(userId: string, password: string) {
    setLoginLoading(true);
    setLoginError("");
    try {
      const result = await login(userId, password);
      const profile = await getCurrentUser(result.access_token);
      sessionStorage.setItem(TOKEN_KEY, result.access_token);
      setToken(result.access_token);
      setUser(profile);
    } catch (error) {
      setLoginError(
        error instanceof ApiError ? error.message : "无法连接服务，请确认后端已经启动。",
      );
    } finally {
      setLoginLoading(false);
    }
  }

  if (booting) {
    return (
      <main className="app-loading">
        <span className="app-loader" />
        <p>正在恢复安全会话…</p>
      </main>
    );
  }

  if (!token || !user) {
    return <LoginScreen loading={loginLoading} error={loginError} onLogin={handleLogin} />;
  }

  if (user.role === "admin" && workspace === "knowledge") {
    return (
      <KnowledgeBaseWorkspace
        token={token}
        user={user}
        onBack={() => setWorkspace("chat")}
        onLogout={logout}
      />
    );
  }

  return (
    <ChatWorkspace
      token={token}
      user={user}
      onLogout={logout}
      onOpenKnowledgeBase={user.role === "admin" ? () => setWorkspace("knowledge") : undefined}
    />
  );
}
