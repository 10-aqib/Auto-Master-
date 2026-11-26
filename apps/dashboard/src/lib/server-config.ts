/**
 * Server-side configuration for the dashboard. Never import from client components:
 * nothing here is prefixed NEXT_PUBLIC_, so values stay on the server.
 */

export class DashboardConfigError extends Error {}

export interface ServerConfig {
  apiInternalUrl: string;
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
  return { apiInternalUrl: url.origin + url.pathname.replace(/\/+$/, "") };
}

export function getServerConfig(): ServerConfig {
  return parseServerConfig(process.env);
}
