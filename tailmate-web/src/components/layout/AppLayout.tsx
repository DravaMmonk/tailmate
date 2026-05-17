import type { PropsWithChildren } from "react";
import { Sidebar } from "./Sidebar";
import { useAuth } from "../../hooks/useAuth";
import { Button } from "../ui/Button";

export function AppLayout({ children }: PropsWithChildren) {
  const { user, logout } = useAuth();

  return (
    <div className="organic-container flex flex-col gap-5 px-0 py-6 lg:flex-row">
      <Sidebar />
      <div className="min-w-0 flex-1">
        <header className="organic-pill-nav mb-5 flex flex-wrap items-center justify-between gap-4 px-5 py-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-[var(--organic-muted-text)]">
              Signed in
            </p>
            <h1 className="font-heading text-2xl font-bold text-[var(--organic-foreground)]">
              {user?.email ?? "Tailmate account"}
            </h1>
          </div>
          <Button variant="ghost" onClick={() => void logout()}>
            Sign out
          </Button>
        </header>
        {children}
      </div>
    </div>
  );
}
