import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  type ReactNode,
} from "react";
import { loadStoredChatState, persistStoredChatState } from "../lib/storage";
import { buildSessionSummary } from "../lib/utils";
import { useAuth } from "../hooks/useAuth";
import type { ChatMessage, ChatSessionState } from "../types";

interface ChatState {
  sessions: Record<string, ChatSessionState>;
  orderedSessionIds: string[];
}

type ChatAction =
  | { type: "hydrate"; sessions: ChatSessionState[] }
  | { type: "ensureSession"; sessionId: string; dogId?: string; dogName?: string }
  | { type: "addMessage"; sessionId: string; message: ChatMessage; dogId?: string; dogName?: string }
  | { type: "appendAssistantDelta"; sessionId: string; messageId: string; delta: string }
  | {
      type: "completeAssistant";
      sessionId: string;
      messageId: string;
      content: string;
      metadata?: Record<string, unknown>;
      dogId?: string;
      dogName?: string;
    }
  | { type: "failAssistant"; sessionId: string; messageId: string; message: string }
  | { type: "hydrateSession"; session: ChatSessionState };

const initialState: ChatState = {
  sessions: {},
  orderedSessionIds: [],
};

function upsertSession(
  state: ChatState,
  sessionId: string,
  update: (session: ChatSessionState) => ChatSessionState,
): ChatState {
  const existing =
    state.sessions[sessionId] ??
    ({
      sessionId,
      messages: [],
      isStreaming: false,
      summary: {
        sessionId,
        title: "New conversation",
        updatedAt: new Date().toISOString(),
        turnCount: 0,
      },
    } satisfies ChatSessionState);

  const nextSession = update(existing);
  const orderedSessionIds = state.orderedSessionIds.includes(sessionId)
    ? [sessionId, ...state.orderedSessionIds.filter((value) => value !== sessionId)]
    : [sessionId, ...state.orderedSessionIds];

  return {
    sessions: {
      ...state.sessions,
      [sessionId]: nextSession,
    },
    orderedSessionIds,
  };
}

function reducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "hydrate": {
      const sessions = action.sessions.reduce<Record<string, ChatSessionState>>(
        (collection, session) => {
          collection[session.sessionId] = session;
          return collection;
        },
        {},
      );
      return {
        sessions,
        orderedSessionIds: action.sessions.map((session) => session.sessionId),
      };
    }
    case "ensureSession":
      return upsertSession(state, action.sessionId, (session) => ({
        ...session,
        summary: {
          ...session.summary,
          dogId: action.dogId ?? session.summary.dogId,
          dogName: action.dogName ?? session.summary.dogName,
        },
      }));
    case "hydrateSession":
      return upsertSession(state, action.session.sessionId, () => action.session);
    case "addMessage":
      return upsertSession(state, action.sessionId, (session) => {
        const messages = [...session.messages, action.message];
        return {
          ...session,
          isStreaming:
            action.message.role === "assistant" && action.message.status === "streaming",
          messages,
          summary: buildSessionSummary(
            action.sessionId,
            messages,
            action.dogId ?? session.summary.dogId,
            action.dogName ?? session.summary.dogName,
          ),
        };
      });
    case "appendAssistantDelta":
      return upsertSession(state, action.sessionId, (session) => {
        const messages = session.messages.map((message) =>
          message.id === action.messageId
            ? { ...message, content: `${message.content}${action.delta}`, status: "streaming" as const }
            : message,
        );
        return {
          ...session,
          isStreaming: true,
          messages,
          summary: buildSessionSummary(
            action.sessionId,
            messages,
            session.summary.dogId,
            session.summary.dogName,
          ),
        };
      });
    case "completeAssistant":
      return upsertSession(state, action.sessionId, (session) => {
        const messages = session.messages.map((message) =>
          message.id === action.messageId
            ? {
                ...message,
                content: action.content || message.content,
                status: "complete" as const,
                metadata: action.metadata ?? message.metadata,
              }
            : message,
        );
        return {
          ...session,
          isStreaming: false,
          messages,
          summary: buildSessionSummary(
            action.sessionId,
            messages,
            action.dogId ?? session.summary.dogId,
            action.dogName ?? session.summary.dogName,
          ),
        };
      });
    case "failAssistant":
      return upsertSession(state, action.sessionId, (session) => ({
        ...session,
        isStreaming: false,
        messages: session.messages.map((message) =>
          message.id === action.messageId
            ? { ...message, content: action.message, status: "error" as const }
            : message,
        ),
      }));
    default:
      return state;
  }
}

interface ChatContextValue {
  state: ChatState;
  dispatch: React.Dispatch<ChatAction>;
}

const ChatContext = createContext<ChatContextValue | null>(null);

export function ChatProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [state, dispatch] = useReducer(reducer, initialState);

  useEffect(() => {
    if (!user) {
      dispatch({ type: "hydrate", sessions: [] });
      return;
    }
    const stored = loadStoredChatState(user.uid);
    dispatch({ type: "hydrate", sessions: stored.sessions });
  }, [user]);

  useEffect(() => {
    if (!user) {
      return;
    }
    const sessions = state.orderedSessionIds
      .map((sessionId) => state.sessions[sessionId])
      .filter(Boolean);
    persistStoredChatState(user.uid, sessions);
  }, [state, user]);

  const value = useMemo(() => ({ state, dispatch }), [state]);
  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

export function useChatStore(): ChatContextValue {
  const context = useContext(ChatContext);
  if (!context) {
    throw new Error("useChatStore must be used inside ChatProvider.");
  }
  return context;
}
