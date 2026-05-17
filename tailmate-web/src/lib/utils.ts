import type {
  ChatMessage,
  DogProfile,
  ExportedConversationSession,
  SessionSummary,
} from "../types";

export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function createClientId(prefix: string): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

export function createExternalSessionId(): string {
  return createClientId("session");
}

export function formatTimestamp(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
    month: "short",
    day: "numeric",
  }).format(new Date(value));
}

export function formatRelativeTime(value: string): string {
  const diffMs = new Date(value).getTime() - Date.now();
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  const steps: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ["day", 1000 * 60 * 60 * 24],
    ["hour", 1000 * 60 * 60],
    ["minute", 1000 * 60],
  ];
  for (const [unit, factor] of steps) {
    if (Math.abs(diffMs) >= factor || unit === "minute") {
      return formatter.format(Math.round(diffMs / factor), unit);
    }
  }
  return "just now";
}

export async function fileToBase64(file: File): Promise<string> {
  const buffer = await file.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let index = 0; index < bytes.byteLength; index += 1) {
    binary += String.fromCharCode(bytes[index]);
  }
  return btoa(binary);
}

export function inferResourceKind(contentType: string): "images" | "videos" | "audio" {
  if (contentType.startsWith("audio/")) {
    return "audio";
  }
  return contentType.startsWith("video/") ? "videos" : "images";
}

export function downloadJson(filename: string, payload: unknown): void {
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function buildSessionSummary(
  sessionId: string,
  messages: ChatMessage[],
  dogId?: string,
  dogName?: string,
): SessionSummary {
  const userMessage = messages.find((message) => message.role === "user");
  return {
    sessionId,
    title: userMessage?.content.slice(0, 72) || "New conversation",
    updatedAt: messages.at(-1)?.createdAt ?? new Date().toISOString(),
    turnCount: messages.length,
    dogId,
    dogName,
  };
}

export function formatDogMeta(profile: DogProfile): string {
  const details = [
    profile.breed,
    profile.age_months ? `${Math.round(profile.age_months / 12)}y` : null,
    profile.weight_kg ? `${profile.weight_kg}kg` : null,
  ].filter(Boolean);
  return details.join(" • ") || "Profile details will appear after enrichment";
}

export function mapExportedTurnsToMessages(
  turns: ExportedConversationSession["turns"],
): ChatMessage[] {
  return turns.flatMap((turn, index) => {
    const messageText =
      typeof turn.message === "string"
        ? turn.message
        : typeof turn.response === "string"
          ? turn.response
          : null;
    if (!messageText) {
      return [];
    }
    const role = turn.role === "assistant" ? "assistant" : "user";
    return [
      {
        id: createClientId(`restored-${index}`),
        role,
        content: messageText,
        createdAt: new Date().toISOString(),
        status: "complete",
        metadata: turn,
      },
    ];
  });
}
