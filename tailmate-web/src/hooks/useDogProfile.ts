import { startTransition, useEffect, useMemo, useState } from "react";
import { fetchExportSnapshot } from "../lib/api";
import { mapExportedTurnsToMessages } from "../lib/utils";
import { useAuth } from "./useAuth";
import type { ChatSessionState, ExportSnapshot } from "../types";

export function useDogProfile() {
  const { user, getToken } = useAuth();
  const [snapshot, setSnapshot] = useState<ExportSnapshot | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) {
      setSnapshot(null);
      setStatus("idle");
      setError(null);
      return;
    }

    let cancelled = false;
    setStatus("loading");
    void getToken()
      .then((token) => {
        if (!token) {
          throw new Error("You must sign in before loading your export snapshot.");
        }
        return fetchExportSnapshot(token, user.uid);
      })
      .then((nextSnapshot) => {
        if (cancelled) {
          return;
        }
        startTransition(() => {
          setSnapshot(nextSnapshot);
          setStatus("ready");
          setError(null);
        });
      })
      .catch((caughtError: unknown) => {
        if (cancelled) {
          return;
        }
        startTransition(() => {
          setStatus("error");
          setError(
            caughtError instanceof Error
              ? caughtError.message
              : "Failed to load your account export.",
          );
        });
      });

    return () => {
      cancelled = true;
    };
  }, [getToken, user]);

  const restoredSessions = useMemo<ChatSessionState[]>(() => {
    if (!snapshot) {
      return [];
    }
    return snapshot.conversation_sessions.map((session) => {
      const messages = mapExportedTurnsToMessages(session.turns);
      const dogId =
        typeof session.attributes?.dog_id === "string" ? session.attributes.dog_id : undefined;
      const matchedProfile = snapshot.dog_profiles.find((profile) => profile.id === dogId);
      return {
        sessionId: session.session_id.split("__").at(-1) ?? session.session_id,
        messages,
        isStreaming: false,
        summary: {
          sessionId: session.session_id.split("__").at(-1) ?? session.session_id,
          title: messages.find((message) => message.role === "user")?.content ?? "Past session",
          updatedAt: snapshot.exported_at,
          turnCount: messages.length,
          dogId,
          dogName: matchedProfile?.name ?? undefined,
        },
      };
    });
  }, [snapshot]);

  return {
    snapshot,
    dogProfiles: snapshot?.dog_profiles ?? [],
    exportedSessions: restoredSessions,
    status,
    error,
  };
}
