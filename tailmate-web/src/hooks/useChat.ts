import { useMemo, useState } from "react";
import { ApiError, streamAgentQuery } from "../lib/api";
import { createClientId, createExternalSessionId } from "../lib/utils";
import { useAuth } from "./useAuth";
import { useChatStore } from "../contexts/ChatContext";
import type { ChatMessage, ChatSessionState } from "../types";

interface SendMessageInput {
  text: string;
  dogId?: string;
  dogName?: string;
  file?: File | null;
}

function createMessage(
  role: "user" | "assistant",
  content: string,
  status: ChatMessage["status"],
): ChatMessage {
  return {
    id: createClientId(role),
    role,
    content,
    createdAt: new Date().toISOString(),
    status,
  };
}

export function useChat(sessionId?: string) {
  const { getToken } = useAuth();
  const { state, dispatch } = useChatStore();
  const [error, setError] = useState<string | null>(null);

  const session = useMemo<ChatSessionState | undefined>(() => {
    if (!sessionId) {
      return undefined;
    }
    return state.sessions[sessionId];
  }, [sessionId, state.sessions]);

  async function sendMessage(input: SendMessageInput): Promise<string> {
    const token = await getToken();
    if (!token) {
      throw new Error("You must sign in before sending a message.");
    }
    const resolvedSessionId = sessionId ?? createExternalSessionId();
    const userMessage = createMessage("user", input.text, "complete");
    const assistantMessage = createMessage("assistant", "", "streaming");

    setError(null);
    dispatch({
      type: "ensureSession",
      sessionId: resolvedSessionId,
      dogId: input.dogId,
      dogName: input.dogName,
    });
    dispatch({
      type: "addMessage",
      sessionId: resolvedSessionId,
      message: userMessage,
      dogId: input.dogId,
      dogName: input.dogName,
    });
    dispatch({
      type: "addMessage",
      sessionId: resolvedSessionId,
      message: assistantMessage,
      dogId: input.dogId,
      dogName: input.dogName,
    });

    void streamAgentQuery(
      {
        token,
        message: input.text,
        sessionId: resolvedSessionId,
        dogId: input.dogId,
        file: input.file,
      },
      (event) => {
        if (event.name === "query.delta") {
          dispatch({
            type: "appendAssistantDelta",
            sessionId: resolvedSessionId,
            messageId: assistantMessage.id,
            delta: event.payload.delta ?? "",
          });
          return;
        }

        if (event.name === "query.completed") {
          const output = event.payload.output;
          const assistantText = output?.response ?? assistantMessage.content;
          const eventError = output?.error;
          if (eventError) {
            const message = eventError.message || "The request failed.";
            dispatch({
              type: "failAssistant",
              sessionId: resolvedSessionId,
              messageId: assistantMessage.id,
              message,
            });
            setError(message);
            return;
          }
          dispatch({
            type: "completeAssistant",
            sessionId: resolvedSessionId,
            messageId: assistantMessage.id,
            content: assistantText,
            metadata: output?.metadata,
            dogId: input.dogId,
            dogName: input.dogName,
          });
        }
      },
    ).catch((caughtError: unknown) => {
      const message =
        caughtError instanceof ApiError || caughtError instanceof Error
          ? caughtError.message
          : "The message could not be sent.";
      dispatch({
        type: "failAssistant",
        sessionId: resolvedSessionId,
        messageId: assistantMessage.id,
        message,
      });
      setError(message);
    });

    return resolvedSessionId;
  }

  function hydrateExportSession(nextSession: ChatSessionState): void {
    dispatch({ type: "hydrateSession", session: nextSession });
  }

  return {
    session,
    messages: session?.messages ?? [],
    isStreaming: session?.isStreaming ?? false,
    error,
    sendMessage,
    hydrateExportSession,
  };
}
