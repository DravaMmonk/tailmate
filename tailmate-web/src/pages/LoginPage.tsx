import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { Input } from "../components/ui/Input";
import { Button } from "../components/ui/Button";
import { resolveAuthActionError } from "../lib/authErrors";

export function LoginPage() {
  const { login, register, authEnabled, error, backendReady, status, token } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [redirectComplete, setRedirectComplete] = useState(false);
  const [registrationAvailable, setRegistrationAvailable] = useState(true);
  const navigate = useNavigate();
  const location = useLocation();
  const searchParams = new URLSearchParams(location.search);
  const nextParam = searchParams.get("next")?.trim() || "";
  const redirectTarget =
    nextParam.startsWith("/") ? nextParam : (location.state as { from?: string } | null)?.from || "/dashboard";

  useEffect(() => {
    if (status !== "signed-in" || !backendReady || !token || redirectComplete) {
      return;
    }
    setRedirectComplete(true);
    navigate(redirectTarget, { replace: true });
  }, [backendReady, navigate, redirectComplete, redirectTarget, status, token]);

  async function handleSubmit() {
    setPending(true);
    setFormError(null);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password);
      }
    } catch (caughtError: unknown) {
      const resolvedError = resolveAuthActionError(caughtError, mode);
      if (mode === "register" && resolvedError.disableRegistration) {
        setRegistrationAvailable(false);
        setMode("login");
      }
      setFormError(resolvedError.message);
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="organic-container grid min-h-screen w-[min(1180px,calc(100vw-24px))] items-center gap-6 px-0 py-8 lg:grid-cols-[minmax(0,1fr)_460px]">
      <motion.section
        initial={{ opacity: 0, x: -20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.5 }}
        className="organic-panel organic-panel-strong relative hidden min-h-[680px] overflow-hidden p-8 lg:block"
      >
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_20%,rgba(230,220,205,0.7),transparent_36%),radial-gradient(circle_at_80%_20%,rgba(193,140,93,0.16),transparent_32%),radial-gradient(circle_at_10%_80%,rgba(93,112,82,0.14),transparent_26%)]" />
        <div className="relative z-10 flex h-full flex-col justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--organic-secondary)]">
              Tailmate
            </p>
            <h1 className="font-heading mt-5 max-w-[9ch] text-6xl leading-[0.92] font-bold tracking-tight text-[var(--organic-foreground)]">
              Your dog deserves the best care.
            </h1>
            <p className="mt-6 max-w-[52ch] text-base leading-8 text-[var(--organic-muted-text)]">
              Sign in to access your dog&apos;s profile, chat history, and personalized advice —
              all waiting for you exactly as you left them.
            </p>
          </div>
          <div className="organic-panel organic-panel-soft max-w-[420px] p-6">
            <p className="text-sm text-[var(--organic-muted-text)]">
              Join thousands of dog owners who use Tailmate every day to keep their pups healthy,
              happy, and well cared for.
            </p>
          </div>
        </div>
      </motion.section>

      <motion.section
        initial={{ opacity: 0, x: 20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.5, delay: 0.06 }}
        className="organic-panel organic-panel-strong mx-auto w-full max-w-[460px] p-6 md:p-8"
      >
        <div className="mb-8">
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--organic-secondary)]">
            Welcome
          </p>
          <h2 className="font-heading mt-4 text-3xl font-bold text-[var(--organic-foreground)]">
            {mode === "login" ? "Welcome back" : "Create your account"}
          </h2>
          <p className="mt-3 text-sm leading-7 text-[var(--organic-muted-text)]">
            {mode === "login"
              ? "Sign in to pick up your chat history and dog profiles."
              : "Create a free account to start getting personalized advice for your dog."}
          </p>
        </div>

        {!authEnabled ? (
          <div className="rounded-[24px] border border-[rgba(168,84,72,0.2)] bg-[rgba(168,84,72,0.08)] p-4 text-sm text-[var(--organic-destructive)]">
            Sign-in is temporarily unavailable. Please try again shortly.
          </div>
        ) : null}

        <div className="mb-5 flex rounded-full border border-[rgba(222,216,207,0.72)] bg-[rgba(255,255,255,0.62)] p-1">
          {(["login", ...(registrationAvailable ? (["register"] as const) : [])] as const).map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => setMode(value)}
              className={`flex-1 rounded-full px-4 py-2 text-sm transition ${
                mode === value
                  ? "bg-[var(--organic-primary)] text-[#f3f4f1]"
                  : "text-[var(--organic-muted-text)]"
              }`}
            >
              {value === "login" ? "Login" : "Register"}
            </button>
          ))}
        </div>

        {!registrationAvailable ? (
          <div className="mb-5 rounded-[24px] border border-[rgba(168,84,72,0.2)] bg-[rgba(168,84,72,0.08)] p-4 text-sm text-[var(--organic-destructive)]">
            Self-service registration is unavailable for this deployment. Sign in with an
            existing account, or enable Email/Password sign-in in Firebase Authentication before
            trying again.
          </div>
        ) : null}

        <div className="space-y-4">
          <label className="block text-sm text-[var(--organic-muted-text)]">
            Email
            <Input
              className="mt-2"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <label className="block text-sm text-[var(--organic-muted-text)]">
            Password
            <Input
              className="mt-2"
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          <Button className="w-full" disabled={pending || !authEnabled} onClick={() => void handleSubmit()}>
            {pending ? "Working..." : mode === "login" ? "Login" : "Create account"}
          </Button>
        </div>

        {formError ? (
          <p className="mt-4 text-sm text-[var(--organic-destructive)]">{formError}</p>
        ) : null}
        {error ? <p className="mt-3 text-sm text-[var(--organic-secondary)]">{error}</p> : null}
        {status === "signed-in" && !backendReady ? (
          <p className="mt-3 text-sm text-[var(--organic-secondary)]">
            Signed in! Setting up your account — this only takes a moment.
          </p>
        ) : null}

        <p className="mt-8 text-sm text-[var(--organic-muted-text)]">
          By continuing you agree to Tailmate&apos;s terms of use.{" "}
          <Link
            className="text-[var(--organic-primary)] underline decoration-[rgba(93,112,82,0.25)] underline-offset-4"
            to="/"
          >
            Back to home
          </Link>
        </p>
      </motion.section>
    </main>
  );
}
