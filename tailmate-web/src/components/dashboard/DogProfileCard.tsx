import { PawPrint } from "lucide-react";
import { formatDogMeta } from "../../lib/utils";
import type { DogProfile } from "../../types";

export function DogProfileCard({
  profile,
  onOpenChat,
}: {
  profile: DogProfile;
  onOpenChat?: (dogId: string, dogName?: string | null) => void;
}) {
  return (
    <article className="organic-panel organic-panel-strong p-5 transition-transform duration-500 hover:-translate-y-1">
      <div className="flex items-center justify-between gap-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-[40%_60%_50%_40%] bg-[var(--organic-muted)] text-[var(--organic-primary)]">
          <PawPrint className="h-5 w-5" />
        </div>
        {onOpenChat ? (
          <button
            type="button"
            className="rounded-full border border-[color:var(--organic-border)] bg-[rgba(254,254,250,0.75)] px-3 py-1.5 text-xs font-bold text-[var(--organic-muted-text)] transition hover:-translate-y-0.5 hover:text-[var(--organic-foreground)]"
            onClick={() => onOpenChat(profile.id, profile.name)}
          >
            Open chat
          </button>
        ) : null}
      </div>
      <h3 className="font-heading mt-5 text-2xl font-bold text-[var(--organic-foreground)]">
        {profile.name ?? "Unnamed dog"}
      </h3>
      <p className="mt-2 text-sm text-[var(--organic-muted-text)]">{formatDogMeta(profile)}</p>
      <p className="mt-4 text-sm leading-7 text-[var(--organic-muted-text)]">
        {profile.raw_notes ||
          profile.medical_history ||
          "Profile details become richer as the conversation continues."}
      </p>
    </article>
  );
}
