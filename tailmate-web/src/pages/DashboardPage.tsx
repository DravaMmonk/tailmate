import { startTransition, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { MessageCircle, PawPrint, Settings2 } from "lucide-react";
import { useDogProfile } from "../hooks/useDogProfile";
import { useChatStore } from "../contexts/ChatContext";
import { DogProfileCard } from "../components/dashboard/DogProfileCard";
import { SessionHistory } from "../components/dashboard/SessionHistory";

export function DashboardPage() {
  const { dogProfiles, exportedSessions, status, error } = useDogProfile();
  const { state, dispatch } = useChatStore();
  const navigate = useNavigate();

  useEffect(() => {
    if (exportedSessions.length === 0) {
      return;
    }
    startTransition(() => {
      for (const session of exportedSessions) {
        if (!state.sessions[session.sessionId]) {
          dispatch({ type: "hydrateSession", session });
        }
      }
    });
  }, [dispatch, exportedSessions, state.sessions]);

  const sessionSummaries = useMemo(
    () =>
      state.orderedSessionIds
        .map((sessionId) => state.sessions[sessionId]?.summary)
        .filter(Boolean)
        .slice(0, 6),
    [state.orderedSessionIds, state.sessions],
  );

  const quickActions = [
    {
      label: "New chat",
      icon: MessageCircle,
      onClick: () => navigate("/chat"),
    },
    {
      label: "Settings",
      icon: Settings2,
      onClick: () => navigate("/settings"),
    },
  ];

  return (
    <div className="space-y-5">
      <section className="grid gap-5 xl:grid-cols-[minmax(0,1.1fr)_380px]">
        <div className="organic-panel organic-panel-strong p-6 md:p-8">
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--organic-secondary)]">
            Dashboard
          </p>
          <h2 className="organic-section-title mt-4 max-w-[12ch] text-4xl font-bold">
            Welcome back. Your dogs are waiting.
          </h2>
          <p className="mt-4 max-w-[58ch] text-sm leading-7 text-[var(--organic-muted-text)]">
            Pick up any conversation, check your dog&apos;s profile, or jump straight into a new
            question — everything is right here.
          </p>

          <div className="mt-8 flex flex-wrap gap-3">
            {quickActions.map((action) => {
              const Icon = action.icon;
              return (
                <button
                  key={action.label}
                  type="button"
                  onClick={action.onClick}
                  className="rounded-full border border-[color:var(--organic-border)] bg-[rgba(255,255,255,0.72)] px-4 py-3 text-sm font-bold text-[var(--organic-foreground)] transition hover:-translate-y-0.5 hover:border-[var(--organic-primary)]"
                >
                  <span className="flex items-center gap-2">
                    <Icon className="h-4 w-4 text-[var(--organic-secondary)]" />
                    {action.label}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <div className="organic-panel organic-panel-soft p-6">
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--organic-muted-text)]">
            Status
          </p>
          <div className="mt-5 space-y-4">
            <div className="organic-metric-card p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-[var(--organic-muted-text)]">
                Profiles
              </p>
              <p className="font-heading mt-3 text-3xl font-bold text-[var(--organic-foreground)]">
                {dogProfiles.length}
              </p>
            </div>
            <div className="organic-metric-card p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-[var(--organic-muted-text)]">
                Sessions
              </p>
              <p className="font-heading mt-3 text-3xl font-bold text-[var(--organic-foreground)]">
                {sessionSummaries.length}
              </p>
            </div>
            <div className="organic-metric-card p-4 text-sm text-[var(--organic-muted-text)]">
              {status === "loading"
                ? "Loading your dog profiles..."
                : error || "Everything is up to date."}
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="grid gap-4 md:grid-cols-2">
          {dogProfiles.length === 0 ? (
            <div className="organic-panel organic-panel-soft col-span-full p-6">
              <div className="flex items-center gap-3">
                <div className="flex h-12 w-12 items-center justify-center rounded-[40%_60%_50%_40%] bg-[var(--organic-muted)] text-[var(--organic-primary)]">
                  <PawPrint className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="font-heading text-xl font-bold text-[var(--organic-foreground)]">
                    No dog profiles yet
                  </h3>
                  <p className="mt-2 text-sm text-[var(--organic-muted-text)]">
                    Start a conversation with Tailmate and your dog&apos;s profile will appear here
                    automatically.
                  </p>
                </div>
              </div>
            </div>
          ) : (
            dogProfiles.map((profile) => (
              <DogProfileCard
                key={profile.id}
                profile={profile}
                onOpenChat={(dogId) => navigate("/chat", { state: { dogId } })}
              />
            ))
          )}
        </div>
        <SessionHistory sessions={sessionSummaries} />
      </section>
    </div>
  );
}
