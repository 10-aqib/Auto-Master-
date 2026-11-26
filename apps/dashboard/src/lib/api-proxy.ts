/** Server-only: forward requests from the dashboard origin to the internal API. */

import type { ServerConfig } from "@/lib/server-config";

const FORWARD_REQUEST_HEADERS = [
  "accept",
  "content-type",
  "cookie",
  "origin",
  "user-agent",
  "x-csrf-token",
  "x-request-id",
];
const FORWARD_RESPONSE_HEADERS = ["content-type", "retry-after", "x-request-id", "cache-control"];
export const MAX_BODY_BYTES = 1_000_000;
const SAFE_SEGMENT = /^[A-Za-z0-9._~-]+$/;

export function isSafePath(segments: string[]): boolean {
  return (
    segments.length > 0 &&
    segments.length <= 8 &&
    segments.every((s) => SAFE_SEGMENT.test(s) && s !== "." && s !== "..")
  );
}

export function buildForwardHeaders(incoming: Headers, config: ServerConfig): Headers {
  const out = new Headers();
  for (const name of FORWARD_REQUEST_HEADERS) {
    const value = incoming.get(name);
    if (value !== null) out.set(name, value);
  }
  const xff = incoming.get("x-forwarded-for");
  if (config.trustForwardedFor && xff) out.set("x-forwarded-for", xff);
  return out;
}

export function copyResponseHeaders(from: Headers, to: Headers): void {
  for (const name of FORWARD_RESPONSE_HEADERS) {
    const value = from.get(name);
    if (value !== null) to.set(name, value);
  }
  for (const cookie of from.getSetCookie()) to.append("set-cookie", cookie);
}

/** Exchange the refresh cookie for new tokens. Returns Set-Cookie values, or null. */
export async function refreshTokens(cookieHeader: string, incoming: Headers, config: ServerConfig) {
  const headers = buildForwardHeaders(incoming, config);
  headers.set("cookie", cookieHeader);
  headers.delete("origin");
  headers.delete("content-type");
  try {
    const response = await fetch(`${config.apiInternalUrl}/api/v1/auth/refresh`, {
      method: "POST",
      headers,
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) return null;
    return response.headers.getSetCookie();
  } catch {
    return null;
  }
}
