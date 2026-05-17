import type { ChatSessionState, StoredChatState } from "../types";

const STORAGE_PREFIX = "tailmate-web:sessions:";

export function loadStoredChatState(userId: string): StoredChatState {
  const rawValue = localStorage.getItem(`${STORAGE_PREFIX}${userId}`);
  if (!rawValue) {
    return { sessions: [] };
  }
  try {
    const parsed = JSON.parse(rawValue) as StoredChatState;
    return parsed.sessions ? parsed : { sessions: [] };
  } catch {
    return { sessions: [] };
  }
}

export function persistStoredChatState(userId: string, sessions: ChatSessionState[]): void {
  localStorage.setItem(`${STORAGE_PREFIX}${userId}`, JSON.stringify({ sessions }));
}
