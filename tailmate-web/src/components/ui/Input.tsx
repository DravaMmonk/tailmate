import { clsx } from "clsx";
import type { InputHTMLAttributes, TextareaHTMLAttributes } from "react";

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={clsx(
        "w-full rounded-[1.4rem] border border-[color:var(--organic-border)] bg-white/80 px-4 py-3 text-sm text-[var(--organic-foreground)] outline-none transition focus:border-[var(--organic-primary)] focus:ring-4 focus:ring-[rgba(93,112,82,0.12)]",
        props.className,
      )}
    />
  );
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={clsx(
        "w-full resize-none rounded-[1.6rem] border border-[color:var(--organic-border)] bg-white/80 px-4 py-3 text-sm text-[var(--organic-foreground)] outline-none transition focus:border-[var(--organic-primary)] focus:ring-4 focus:ring-[rgba(93,112,82,0.12)]",
        props.className,
      )}
    />
  );
}
