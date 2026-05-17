import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { motion } from "framer-motion";
import { cn, formatTimestamp } from "../../lib/utils";
import type { ChatMessage } from "../../types";
import { StreamingIndicator } from "./StreamingIndicator";

export function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <motion.article
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className={cn("flex", isUser ? "justify-end" : "justify-start")}
    >
      <div
        className={cn(
          "max-w-[88%] border px-4 py-3 shadow-[var(--shadow-card)]",
          isUser
            ? "rounded-[2rem_2rem_0.8rem_2rem] border-[rgba(93,112,82,0.16)] bg-[rgba(93,112,82,0.12)] text-[var(--organic-foreground)]"
            : message.status === "error"
              ? "rounded-[2rem_2rem_2rem_0.8rem] border-[rgba(168,84,72,0.2)] bg-[rgba(168,84,72,0.08)] text-[var(--organic-foreground)]"
              : "rounded-[2rem_2rem_2rem_0.8rem] border-[rgba(222,216,207,0.72)] bg-[rgba(254,254,250,0.92)] text-[var(--organic-foreground)]",
        )}
      >
        <div className="organic-prose max-w-none text-sm leading-7">
          {message.content ? (
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
          ) : message.status === "streaming" ? (
            <StreamingIndicator />
          ) : null}
        </div>
        <div className="mt-3 flex items-center justify-between gap-4 text-[11px] uppercase tracking-[0.18em] text-[var(--organic-muted-text)]">
          <span>{isUser ? "Owner" : "Tailmate"}</span>
          <span>{formatTimestamp(message.createdAt)}</span>
        </div>
      </div>
    </motion.article>
  );
}
