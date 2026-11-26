/**
 * Server-side configuration for the dashboard. Never import from client components:
 * nothing here is prefixed NEXT_PUBLIC_, so values stay on the server.
 */

export class DashboardConfigError extends Error {}

export interface ServerConfig {
  apiInternalUrl: string;
  /** Forward the incoming X-Forwarded-For to the API. Enable only behind a trusted proxy (Caddy). */
  trustForwardedFor: boolean;
}

export function parseServerConfig(env: Record<string, string | undefined>): ServerConfig {
  const raw = env.API_INTERNAL_URL?.trim() || "http://localhost:8000";
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new DashboardConfigError("API_INTERNAL_URL must be an absolute URL");
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new DashboardConfigError("API_INTERNAL_URL must use http or https");
  }
  if (url.username || url.password) {
    throw new DashboardConfigError("API_INTERNAL_URL must not contain credentials");
  }
  const trust = (env.DASHBOARD_TRUST_FORWARDED_FOR ?? "false").trim().toLowerCase();
  if (trust !== "true" && trust !== "false") {
    throw new DashboardConfigError("DASHBOARD_TRUST_FORWARDED_FOR must be true or false");
  }
  return {
    apiInternalUrl: url.origin + url.pathname.replace(/\/+$/, ""),
    trustForwardedFor: trust === "true",
  };
}

export function getServerConfig(): ServerConfig {
  return parseServerConfig(process.env);
}
