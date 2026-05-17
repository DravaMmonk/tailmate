import type { TextareaHTMLAttributes } from "react";
import { cn } from "../../lib/utils";

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "w-full rounded-[1.6rem] border border-[color:var(--organic-border)] bg-white/80 px-4 py-3 text-sm text-[var(--organic-foreground)] outline-none transition focus:border-[var(--organic-primary)] focus:ring-4 focus:ring-[rgba(93,112,82,0.12)]",
        className,
      )}
      {...props}
    />
  );
}
