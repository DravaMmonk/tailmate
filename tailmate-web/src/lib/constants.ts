const LOCAL_API_BASE_URL = "http://localhost:8080";
const PRODUCTION_API_BASE_URL =
  import.meta.env.VITE_PRODUCTION_API_BASE_URL ?? "";
const PRODUCTION_HOSTS = new Set(
  (import.meta.env.VITE_PRODUCTION_HOSTS ?? "")
    .split(",")
    .map((host: string) => host.trim().toLowerCase())
    .filter((host: string) => host.length > 0),
);

function normalizeBaseUrl(rawValue: string | undefined): string | null {
  const normalized = rawValue?.trim().replace(/\/$/, "");
  return normalized ? normalized : null;
}

function resolveRuntimeHostname(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.location.hostname.toLowerCase();
}

function resolveDefaultApiBaseUrl(): string {
  const runtimeHostname = resolveRuntimeHostname();
  if (
    runtimeHostname &&
    PRODUCTION_API_BASE_URL &&
    PRODUCTION_HOSTS.has(runtimeHostname)
  ) {
    return PRODUCTION_API_BASE_URL;
  }
  return LOCAL_API_BASE_URL;
}

export const API_BASE_URL =
  normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL) ?? resolveDefaultApiBaseUrl();

export const LANDING_SECTIONS = [
  { label: "Features", href: "#features" },
  { label: "How It Works", href: "#how-it-works" },
];
