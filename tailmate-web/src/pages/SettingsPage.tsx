import { useNavigate } from "react-router-dom";
import { deleteUserAccount } from "../lib/api";
import { downloadJson } from "../lib/utils";
import { useAuth } from "../hooks/useAuth";
import { useDogProfile } from "../hooks/useDogProfile";
import { Button } from "../components/ui/Button";

export function SettingsPage() {
  const { user, getToken, logout } = useAuth();
  const { snapshot, dogProfiles, status } = useDogProfile();
  const navigate = useNavigate();

  async function handleDeleteAccount() {
    if (!user) {
      return;
    }
    const token = await getToken();
    if (!token) {
      return;
    }
    const confirmed = window.confirm(
      "Are you sure? This will permanently delete your account, all dog profiles, and chat history.",
    );
    if (!confirmed) {
      return;
    }
    await deleteUserAccount(token, user.uid);
    await logout();
    navigate("/", { replace: true });
  }

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
      <section className="space-y-5">
        <div className="organic-panel organic-panel-strong p-6">
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--organic-secondary)]">
            Settings
          </p>
          <h2 className="organic-section-title mt-4 text-4xl font-bold">
            Your account settings
          </h2>
          <p className="mt-4 max-w-[56ch] text-sm leading-7 text-[var(--organic-muted-text)]">
            Manage your account, download your data, and set your preferences.
          </p>
        </div>

        <div className="organic-panel organic-panel-soft p-6">
          <h3 className="font-heading text-xl font-bold text-[var(--organic-foreground)]">
            User account
          </h3>
          <dl className="mt-5 grid gap-4 md:grid-cols-2">
            <div>
              <dt className="text-xs uppercase tracking-[0.18em] text-[var(--organic-muted-text)]">
                Email
              </dt>
              <dd className="mt-2 text-sm text-[var(--organic-foreground)]">
                {user?.email ?? "Unavailable"}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-[0.18em] text-[var(--organic-muted-text)]">
                User id
              </dt>
              <dd className="mt-2 break-all text-sm text-[var(--organic-foreground)]">
                {user?.uid ?? "Unavailable"}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-[0.18em] text-[var(--organic-muted-text)]">
                Profiles
              </dt>
              <dd className="mt-2 text-sm text-[var(--organic-foreground)]">{dogProfiles.length}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-[0.18em] text-[var(--organic-muted-text)]">
                Export
              </dt>
              <dd className="mt-2 text-sm text-[var(--organic-foreground)]">
                {status === "ready" ? "Ready" : status}
              </dd>
            </div>
          </dl>
        </div>
      </section>

      <aside className="space-y-5">
        <div className="organic-panel organic-panel-soft p-5">
          <h3 className="font-heading text-xl font-bold text-[var(--organic-foreground)]">
            Data portability
          </h3>
          <p className="mt-3 text-sm leading-7 text-[var(--organic-muted-text)]">
            Download a copy of all your data — dog profiles, chat history, and account info — as a
            JSON file.
          </p>
          <Button
            className="mt-5 w-full"
            variant="secondary"
            onClick={() => snapshot && downloadJson(`tailmate-export-${user?.uid}.json`, snapshot)}
            disabled={!snapshot}
          >
            Download export
          </Button>
        </div>

        <div className="organic-panel organic-panel-soft p-5">
          <h3 className="font-heading text-xl font-bold text-[var(--organic-foreground)]">
            Language preference
          </h3>
          <p className="mt-3 text-sm leading-7 text-[var(--organic-muted-text)]">
            Choose the language you prefer for Tailmate&apos;s replies. More languages are coming
            soon.
          </p>
          <div className="mt-5 rounded-[2rem] border border-[rgba(222,216,207,0.72)] bg-[rgba(255,255,255,0.68)] px-4 py-3 text-sm text-[var(--organic-muted-text)]">
            Coming soon: English, Chinese, Arabic, Vietnamese, Cantonese, Hindi.
          </div>
        </div>

        <div className="organic-panel rounded-[3rem_2rem_3rem_2rem] border border-[rgba(168,84,72,0.18)] p-5">
          <h3 className="font-heading text-xl font-bold text-[var(--organic-foreground)]">
            Danger zone
          </h3>
          <p className="mt-3 text-sm leading-7 text-[var(--organic-muted-text)]">
            Permanently delete your Tailmate account, including all dog profiles, chat history, and
            uploaded media. This cannot be undone.
          </p>
          <Button variant="danger" className="mt-5 w-full" onClick={() => void handleDeleteAccount()}>
            Delete account
          </Button>
        </div>
      </aside>
    </div>
  );
}
