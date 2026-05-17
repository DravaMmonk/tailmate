import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

export function ProtectedRoute() {
  const { status, authEnabled } = useAuth();
  const location = useLocation();

  if (!authEnabled) {
    return (
      <main className="organic-container flex min-h-screen items-center justify-center px-6">
        <div className="organic-panel organic-panel-strong w-full max-w-3xl p-8 text-center">
          <p className="text-sm uppercase tracking-[0.24em] text-[var(--organic-muted-text)]">
            Configuration
          </p>
          <h1 className="organic-section-title mt-4 text-3xl font-bold">
            Firebase is not configured.
          </h1>
          <p className="mt-3 text-sm leading-7 text-[var(--organic-muted-text)]">
            Add the Vite Firebase environment variables before using protected routes.
          </p>
        </div>
      </main>
    );
  }

  if (status === "loading") {
    return (
      <main className="organic-container flex min-h-screen items-center justify-center px-6">
        <div className="organic-panel organic-panel-soft w-full max-w-3xl p-8 text-center text-[var(--organic-muted-text)]">
          Restoring your Tailmate account...
        </div>
      </main>
    );
  }

  if (status !== "signed-in") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <Outlet />;
}
