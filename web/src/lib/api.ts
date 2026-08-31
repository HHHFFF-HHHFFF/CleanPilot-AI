import type {
  AgentEvent,
  ConversationDetail,
  ConversationSummary,
  CurrentUser,
  KnowledgeDocument,
  LocationProfile,
  TokenResponse,
} from "../types";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(
  /\/$/,
  "",
);

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function readError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail || "请求失败，请稍后重试";
  } catch {
    return "请求失败，请稍后重试";
  }
}

async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) {
    throw new ApiError(await readError(response), response.status);
  }
  return (await response.json()) as T;
}

function authHeaders(token: string): HeadersInit {
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
}

export function login(userId: string, password: string): Promise<TokenResponse> {
  return requestJson<TokenResponse>("/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, password }),
  });
}

export function getCurrentUser(token: string): Promise<CurrentUser> {
  return requestJson<CurrentUser>("/api/v1/users/me", {
    headers: authHeaders(token),
  });
}

export function getLocationWeather(
  token: string,
  latitude: number,
  longitude: number,
): Promise<LocationProfile> {
  return requestJson<LocationProfile>("/api/v1/context/location-weather", {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ latitude, longitude }),
  });
}

export function getCityWeather(token: string, city: string): Promise<LocationProfile> {
  return requestJson<LocationProfile>("/api/v1/context/city-weather", {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ city }),
  });
}

export function listConversations(token: string): Promise<ConversationSummary[]> {
  return requestJson<ConversationSummary[]>("/api/v1/conversations", {
    headers: authHeaders(token),
  });
}

export function createConversation(token: string, title: string): Promise<ConversationSummary> {
  return requestJson<ConversationSummary>("/api/v1/conversations", {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ title }),
  });
}

export function getConversation(token: string, conversationId: string): Promise<ConversationDetail> {
  return requestJson<ConversationDetail>(`/api/v1/conversations/${conversationId}`, {
    headers: authHeaders(token),
  });
}

export async function deleteConversation(token: string, conversationId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/conversations/${conversationId}`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
  if (!response.ok) {
    throw new ApiError(await readError(response), response.status);
  }
}

export function listKnowledgeDocuments(token: string): Promise<KnowledgeDocument[]> {
  return requestJson<KnowledgeDocument[]>("/api/v1/admin/knowledge/documents", {
    headers: authHeaders(token),
  });
}

export function synchronizeKnowledgeDocuments(token: string): Promise<KnowledgeDocument[]> {
  return requestJson<KnowledgeDocument[]>("/api/v1/admin/knowledge/synchronize", {
    method: "POST",
    headers: authHeaders(token),
  });
}

function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      const content = result.split(",", 2)[1];
      if (!content) reject(new Error("无法读取上传文件"));
      else resolve(content);
    };
    reader.onerror = () => reject(new Error("无法读取上传文件"));
    reader.readAsDataURL(file);
  });
}

export async function uploadKnowledgeDocument(
  token: string,
  file: File,
): Promise<KnowledgeDocument> {
  const contentBase64 = await readFileAsBase64(file);
  return requestJson<KnowledgeDocument>("/api/v1/admin/knowledge/upload", {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ filename: file.name, content_base64: contentBase64 }),
  });
}

export function retryKnowledgeDocument(
  token: string,
  documentId: string,
): Promise<KnowledgeDocument> {
  return requestJson<KnowledgeDocument>(
    `/api/v1/admin/knowledge/documents/${documentId}/retry`,
    { method: "POST", headers: authHeaders(token) },
  );
}

export async function removeKnowledgeDocument(token: string, documentId: string): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/admin/knowledge/documents/${documentId}`,
    { method: "DELETE", headers: authHeaders(token) },
  );
  if (!response.ok) {
    throw new ApiError(await readError(response), response.status);
  }
}

export async function streamChat(options: {
  token: string;
  query: string;
  conversationId: string;
  locationProfile: LocationProfile | null;
  signal: AbortSignal;
  onEvent: (event: AgentEvent) => void;
}): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/chat/stream`, {
    method: "POST",
    headers: authHeaders(options.token),
    body: JSON.stringify({
      query: options.query,
      conversation_id: options.conversationId,
      location_profile: options.locationProfile,
    }),
    signal: options.signal,
  });
  if (!response.ok) {
    throw new ApiError(await readError(response), response.status);
  }
  if (!response.body) {
    throw new ApiError("浏览器不支持流式响应", 500);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let bufferedText = "";

  while (true) {
    const { done, value } = await reader.read();
    bufferedText += decoder.decode(value, { stream: !done });
    const lines = bufferedText.split("\n");
    bufferedText = lines.pop() || "";
    for (const line of lines) {
      if (line.trim()) {
        options.onEvent(JSON.parse(line) as AgentEvent);
      }
    }
    if (done) {
      break;
    }
  }

  if (bufferedText.trim()) {
    options.onEvent(JSON.parse(bufferedText) as AgentEvent);
  }
}
