export type AuthStatus = "loading" | "signed-out" | "signed-in";

export type ChatRole = "user" | "assistant";

export type MessageStatus = "pending" | "streaming" | "complete" | "error";

export interface ChatAttachment {
  name: string;
  contentType: string;
  size: number;
}

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  createdAt: string;
  status: MessageStatus;
  metadata?: Record<string, unknown>;
  attachments?: ChatAttachment[];
}

export interface SessionSummary {
  sessionId: string;
  title: string;
  updatedAt: string;
  turnCount: number;
  dogId?: string;
  dogName?: string;
}

export interface ChatSessionState {
  sessionId: string;
  messages: ChatMessage[];
  summary: SessionSummary;
  isStreaming: boolean;
}

export interface StoredChatState {
  sessions: ChatSessionState[];
}

export interface UserAccount {
  user_id: string;
  status: string;
  role: string;
  created_at: string | null;
}

export interface PlatformConnection {
  user_id: string;
  status: string;
  role: string;
  platform: string;
  platform_user_id: string;
  connection_status: string;
  user_created_at: string | null;
  connected_at: string | null;
  disconnected_at: string | null;
}

export interface DogProfile {
  id: string;
  user_id: string;
  name: string | null;
  breed: string | null;
  age_months: number | null;
  weight_kg: number | null;
  sex: string | null;
  neutered: boolean | null;
  medical_history: string | null;
  allergies: string | null;
  current_medications: string | null;
  temperament: string | null;
  activity_level: string | null;
  diet: string | null;
  raw_notes: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ExportedConversationSession {
  session_id: string;
  turns: Array<Record<string, unknown>>;
  attributes: Record<string, unknown>;
}

export interface ExportSnapshot {
  format_version: string;
  exported_at: string;
  user: UserAccount;
  platform_connections: PlatformConnection[];
  dog_profiles: DogProfile[];
  conversation_sessions: ExportedConversationSession[];
  media_assets: Array<Record<string, unknown>>;
}

export interface ApiErrorDetail {
  code: number;
  type: string;
  message: string;
}

export interface AgentQueryOutput {
  session_id: string;
  response: string;
  metadata: Record<string, unknown>;
  error: ApiErrorDetail | null;
}

export interface StreamEventPayload {
  event?: string;
  session_id?: string;
  delta?: string;
  output?: AgentQueryOutput;
  [key: string]: unknown;
}
