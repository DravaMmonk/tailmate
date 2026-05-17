import type { StreamEventPayload } from "../types";

export interface StreamEvent {
  name: string;
  payload: StreamEventPayload;
}

export interface SseParser {
  push(chunk: string): void;
  finish(): void;
}

function createInvalidPayloadError(rawPayload: string, cause: unknown): Error {
  const error = new Error("The chat stream returned an invalid event payload.", {
    cause,
  }) as Error & { rawPayload?: string };
  error.rawPayload = rawPayload;
  return error;
}

export function createSseParser(onEvent: (event: StreamEvent) => void): SseParser {
  let buffer = "";
  let eventName = "message";
  let dataLines: string[] = [];
  let hasExplicitEventName = false;

  const resetFrameState = () => {
    eventName = "message";
    dataLines = [];
    hasExplicitEventName = false;
  };

  const dispatchEvent = () => {
    if (dataLines.length === 0) {
      resetFrameState();
      return;
    }

    const rawPayload = dataLines.join("\n");
    let payload: StreamEventPayload;
    try {
      payload = JSON.parse(rawPayload) as StreamEventPayload;
    } catch (error: unknown) {
      throw createInvalidPayloadError(rawPayload, error);
    }

    onEvent({
      name: eventName,
      payload,
    });
    resetFrameState();
  };

  const processLine = (line: string) => {
    const normalizedLine = line.endsWith("\r") ? line.slice(0, -1) : line;

    if (!normalizedLine) {
      dispatchEvent();
      return;
    }

    if (normalizedLine.startsWith(":")) {
      return;
    }

    if (normalizedLine.startsWith("event:")) {
      if (dataLines.length > 0 && hasExplicitEventName) {
        // Some upstream deployments emit a new event header without the required
        // blank-line separator. Flush the previous frame so streaming still works.
        dispatchEvent();
      }
      eventName = normalizedLine.slice(6).trim();
      hasExplicitEventName = true;
      return;
    }

    if (normalizedLine.startsWith("data:")) {
      dataLines.push(normalizedLine.slice(5).trimStart());
    }
  };

  return {
    push(chunk: string) {
      buffer += chunk;

      let newlineIndex = buffer.indexOf("\n");
      while (newlineIndex !== -1) {
        const line = buffer.slice(0, newlineIndex);
        buffer = buffer.slice(newlineIndex + 1);
        processLine(line);
        newlineIndex = buffer.indexOf("\n");
      }
    },
    finish() {
      if (buffer.length > 0) {
        processLine(buffer);
        buffer = "";
      }
      dispatchEvent();
    },
  };
}

export function parseSseEvents(chunks: Iterable<string>): StreamEvent[] {
  const events: StreamEvent[] = [];
  const parser = createSseParser((event) => {
    events.push(event);
  });

  for (const chunk of chunks) {
    parser.push(chunk);
  }

  parser.finish();
  return events;
}
