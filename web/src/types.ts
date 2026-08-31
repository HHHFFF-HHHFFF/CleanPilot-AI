export type Device = {
  device_id: string;
  model: string;
  purchased_at: string;
  warranty_until: string;
};

export type CurrentUser = {
  user_id: string;
  display_name: string;
  city: string;
  role: string;
  device: Device | null;
};

export type TokenResponse = {
  access_token: string;
  token_type: string;
  expires_in: number;
};

export type LocationProfile = {
  city: string;
  latitude: number;
  longitude: number;
  condition: string;
  temperature: number | null;
  apparent_temperature: number | null;
  humidity: number | null;
  wind_speed: number | null;
  observed_at: string | null;
};

export type AgentEvent = {
  type: "conversation" | "trace" | "answer" | "error";
  agent?: string;
  conversation_id?: string;
  content: string;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  traces?: string[];
  agent?: string;
  pending?: boolean;
  error?: boolean;
};

export type ConversationSummary = {
  conversation_id: string;
  title: string;
  preview: string;
  created_at: string;
  updated_at: string;
};

export type ConversationDetail = {
  conversation: ConversationSummary;
  messages: Array<{
    message_id: string;
    role: "user" | "assistant";
    content: string;
    traces: string[];
    agent: string | null;
    created_at: string;
  }>;
};
