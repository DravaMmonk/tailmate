import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { MessageSquareHeart } from "lucide-react";
import { useChat } from "../hooks/useChat";
import { useDogProfile } from "../hooks/useDogProfile";
import { useAuth } from "../hooks/useAuth";
import { ChatInput } from "../components/chat/ChatInput";
import { MessageBubble } from "../components/chat/MessageBubble";
import { mapExportedTurnsToMessages } from "../lib/utils";

export function ChatPage() {
  const { sessionId } = useParams();
  const { messages, isStreaming, error, sendMessage, session, hydrateExportSession } = useChat(
    sessionId,
  );
  const { dogProfiles, snapshot } = useDogProfile();
  const { backendReady, error: authError } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [selectedDogId, setSelectedDogId] = useState<string>(
    (location.state as { dogId?: string } | null)?.dogId ?? "",
  );

  useEffect(() => {
    if (!selectedDogId && dogProfiles[0]?.id) {
      setSelectedDogId(dogProfiles[0].id);
    }
  }, [dogProfiles, selectedDogId]);

  useEffect(() => {
    if (!sessionId || session || !snapshot) {
      return;
    }
    const matchingSession = snapshot.conversation_sessions.find(
      (candidate) => candidate.session_id.split("__").at(-1) === sessionId,
    );
    if (!matchingSession) {
      return;
    }
    const dogId =
      typeof matchingSession.attributes?.dog_id === "string"
        ? matchingSession.attributes.dog_id
        : undefined;
    const dogName = dogProfiles.find((profile) => profile.id === dogId)?.name ?? undefined;
    const restoredMessages = mapExportedTurnsToMessages(matchingSession.turns);
    hydrateExportSession({
      sessionId,
      messages: restoredMessages,
      isStreaming: false,
      summary: {
        sessionId,
        title:
          restoredMessages.find((message) => message.role === "user")?.content ??
          "Recovered session",
        updatedAt: snapshot.exported_at,
        turnCount: restoredMessages.length,
        dogId,
        dogName,
      },
    });
  }, [dogProfiles, hydrateExportSession, session, sessionId, snapshot]);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, isStreaming]);

  async function handleSubmit(input: { text: string; file: File | null }) {
    const selectedDog = dogProfiles.find((profile) => profile.id === selectedDogId);
    const nextSessionId = await sendMessage({
      text: input.text,
      dogId: selectedDog?.id,
      dogName: selectedDog?.name ?? undefined,
      file: input.file,
    });
    if (!sessionId) {
      navigate(`/chat/${nextSessionId}`, { replace: true });
    }
  }

  return (
    <div className="grid gap-5 xl:grid-cols-[320px_minmax(0,1fr)]">
      <section className="organic-panel organic-panel-soft p-5">
        <p className="text-xs uppercase tracking-[0.24em] text-[var(--organic-muted-text)]">
          Session
        </p>
        <h2 className="font-heading mt-3 text-2xl font-bold text-[var(--organic-foreground)]">
          {session?.summary.dogName ? `Chatting about ${session.summary.dogName}` : "New conversation"}
        </h2>
        <p className="mt-3 text-sm leading-7 text-[var(--organic-muted-text)]">
          Ask anything about your dog&apos;s health, behavior, diet, or daily routine.
        </p>
        <label className="mt-6 block text-sm text-[var(--organic-muted-text)]">
          Which dog is this about?
          <select
            className="mt-2 w-full rounded-[1.4rem] border border-[color:var(--organic-border)] bg-white/80 px-4 py-3 text-sm text-[var(--organic-foreground)] outline-none transition focus:border-[var(--organic-primary)] focus:ring-4 focus:ring-[rgba(93,112,82,0.12)]"
            value={selectedDogId}
            onChange={(event) => setSelectedDogId(event.target.value)}
          >
            <option value="">No dog selected</option>
            {dogProfiles.map((profile) => (
              <option key={profile.id} value={profile.id}>
                {profile.name ?? profile.id}
              </option>
            ))}
          </select>
        </label>
        <div className="mt-5 rounded-[2rem] border border-[rgba(222,216,207,0.6)] bg-[rgba(255,255,255,0.68)] p-4 text-sm text-[var(--organic-muted-text)]">
          {selectedDogId
            ? "You can attach photos or files to this conversation."
            : "Select a dog above to attach photos or files."}
        </div>
        {authError ? <p className="mt-4 text-sm text-[var(--organic-secondary)]">{authError}</p> : null}
        {error ? <p className="mt-3 text-sm text-[var(--organic-destructive)]">{error}</p> : null}
      </section>

      <section className="space-y-4">
        <div className="organic-panel organic-panel-strong p-5">
          <div className="flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-[40%_60%_50%_40%] bg-[var(--organic-muted)] text-[var(--organic-secondary)]">
              <MessageSquareHeart className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--organic-muted-text)]">
                Live chat
              </p>
              <h3 className="font-heading mt-1 text-xl font-bold text-[var(--organic-foreground)]">
                Conversation stream
              </h3>
            </div>
          </div>
          <div
            ref={scrollRef}
            className="mt-5 h-[56vh] min-h-[420px] space-y-4 overflow-y-auto rounded-[2rem] border border-[rgba(222,216,207,0.72)] bg-[rgba(255,255,255,0.58)] p-4"
          >
            {messages.length === 0 ? (
              <div className="flex h-full items-center justify-center">
                <p className="max-w-[36ch] text-center text-sm leading-7 text-[var(--organic-muted-text)]">
                  Ask a question, describe a symptom, or upload a photo — Tailmate will reply in
                  seconds.
                </p>
              </div>
            ) : (
              messages.map((message) => <MessageBubble key={message.id} message={message} />)
            )}
          </div>
        </div>

        <ChatInput disabled={!backendReady || isStreaming} onSubmit={handleSubmit} />
      </section>
    </div>
  );
}
