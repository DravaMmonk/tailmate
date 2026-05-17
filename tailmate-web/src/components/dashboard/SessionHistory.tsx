import { MessageSquareMore } from "lucide-react";
import { Link } from "react-router-dom";
import { formatRelativeTime } from "../../lib/utils";
import type { SessionSummary } from "../../types";

export function SessionHistory({ sessions }: { sessions: SessionSummary[] }) {
  return (
    <div className="organic-panel organic-panel-strong p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--organic-muted-text)]">
            History
          </p>
          <h3 className="font-heading mt-2 text-2xl font-bold text-[var(--organic-foreground)]">
            Recent sessions
          </h3>
        </div>
        <MessageSquareMore className="h-5 w-5 text-[var(--organic-secondary)]" />
      </div>
      <div className="mt-5 space-y-3">
        {sessions.length === 0 ? (
          <p className="text-sm text-[var(--organic-muted-text)]">
            Ask your first question to start building a conversation history.
          </p>
        ) : (
          sessions.map((session) => (
            <Link
              key={session.sessionId}
              to={`/chat/${session.sessionId}`}
              className="block rounded-[2rem] border border-[rgba(222,216,207,0.6)] bg-[rgba(255,255,255,0.7)] px-4 py-3 transition hover:-translate-y-0.5 hover:border-[var(--organic-primary)]"
            >
              <div className="flex items-center justify-between gap-4">
                <p className="truncate text-sm font-semibold text-[var(--organic-foreground)]">
                  {session.title}
                </p>
                <span className="text-xs uppercase tracking-[0.14em] text-[var(--organic-muted-text)]">
                  {formatRelativeTime(session.updatedAt)}
                </span>
              </div>
              <p className="mt-2 text-xs text-[var(--organic-muted-text)]">
                {session.turnCount} {session.turnCount === 1 ? "message" : "messages"}
                {session.dogName ? ` • ${session.dogName}` : ""}
              </p>
            </Link>
          ))
        )}
      </div>
    </div>
  );
}
