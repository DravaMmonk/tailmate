import { API_BASE_URL } from "./constants";
import { createSseParser } from "./sse";
import { fileToBase64, inferResourceKind } from "./utils";
import type {
  ExportSnapshot,
  PlatformConnection,
  UserAccount,
} from "../types";
import type { StreamEvent } from "./sse";

interface ApiOptions extends RequestInit {
  token?: string;
}

export class ApiError extends Error {
  status: number;
  detail?: unknown;

  constructor(message: string, status = 500, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

interface RegistrationResponse {
  user: UserAccount;
  connection: PlatformConnection;
}

interface PlatformConnectionResponse {
  connection: PlatformConnection;
}

interface ActivationResponse {
  user: UserAccount;
}

interface StreamRequestInput {
  token: string;
  message: string;
  sessionId?: string;
  dogId?: string;
  file?: File | null;
}

async function parseJsonResponse(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

async function apiFetch(path: string, options: ApiOptions = {}): Promise<Response> {
  const headers = new Headers(options.headers);
  if (options.token) {
    headers.set("Authorization", `Bearer ${options.token}`);
  }
  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });
  if (!response.ok) {
    const payload = await parseJsonResponse(response);
    const message =
      typeof payload === "object" &&
      payload !== null &&
      "error" in payload &&
      typeof payload.error === "string"
        ? payload.error
        : response.statusText || "Request failed.";
    throw new ApiError(message, response.status, payload);
  }
  return response;
}

export async function ensureUserRegistered(token: string): Promise<RegistrationResponse> {
  const response = await apiFetch("/v1/users/register", {
    method: "POST",
    token,
  });
  return (await response.json()) as RegistrationResponse;
}

export async function activateUser(token: string): Promise<ActivationResponse> {
  const response = await apiFetch("/v1/users/activate", {
    method: "POST",
    token,
  });
  return (await response.json()) as ActivationResponse;
}

export async function createPlatformConnection(
  token: string,
  platform: string,
  platformUserId: string,
  status = "active",
): Promise<PlatformConnectionResponse> {
  const response = await apiFetch(`/v1/users/connections/${platform}`, {
    method: "POST",
    token,
    body: JSON.stringify({
      platform_user_id: platformUserId,
      status,
    }),
  });
  return (await response.json()) as PlatformConnectionResponse;
}

export async function fetchExportSnapshot(
  token: string,
  userId: string,
): Promise<ExportSnapshot> {
  const response = await apiFetch(`/v1/users/${userId}/export`, {
    method: "GET",
    token,
  });
  return (await response.json()) as ExportSnapshot;
}

export async function deleteUserAccount(token: string, userId: string): Promise<unknown> {
  const response = await apiFetch(`/v1/users/${userId}`, {
    method: "DELETE",
    token,
  });
  return response.json();
}

async function createStripMetadataRequest(
  file: File,
  dogId: string,
  sessionId: string,
): Promise<Record<string, string>> {
  const payloadBase64 = await fileToBase64(file);
  return {
    dog_id: dogId,
    resource_kind: inferResourceKind(file.type || "application/octet-stream"),
    filename: file.name,
    content_type: file.type || "application/octet-stream",
    payload_base64: payloadBase64,
    session_id: sessionId,
  };
}

export async function streamAgentQuery(
  input: StreamRequestInput,
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  const body: Record<string, unknown> = {
    message: input.message,
  };
  const sessionId = input.sessionId;
  if (sessionId) {
    body.session_id = sessionId;
  }
  if (input.dogId) {
    body.dog_id = input.dogId;
  }
  if (input.file) {
    if (!input.dogId) {
      throw new ApiError("Select a dog profile before uploading media.", 400);
    }
    body.strip_metadata_request = await createStripMetadataRequest(
      input.file,
      input.dogId,
      sessionId ?? "",
    );
  }

  const response = await fetch(`${API_BASE_URL}/v1/agent/query`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      Authorization: `Bearer ${input.token}`,
    },
    body: JSON.stringify(body),
  });

  const contentType = response.headers.get("content-type") || "";
  if (!response.ok || !contentType.includes("text/event-stream")) {
    const payload = await parseJsonResponse(response);
    const message =
      typeof payload === "object" &&
      payload !== null &&
      "error" in payload &&
      typeof payload.error === "string"
        ? payload.error
        : "The request failed.";
    throw new ApiError(message, response.status, payload);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new ApiError("Streaming is not available in this browser.", 500);
  }

  const decoder = new TextDecoder();
  const parser = createSseParser(onEvent);

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    parser.push(decoder.decode(value, { stream: true }));
  }
  parser.push(decoder.decode());
  parser.finish();
}
