export type CheckStatus = "ok" | "fail";

export interface DependencyCheck {
  status: CheckStatus;
  latency_ms: number | null;
  error: string | null;
}

export type ApiHealth =
  | { kind: "ready"; checks: Record<string, DependencyCheck> }
  | { kind: "not_ready"; checks: Record<string, DependencyCheck> }
  | { kind: "unreachable"; reason: string };

function isCheck(value: unknown): value is DependencyCheck {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    (v.status === "ok" || v.status === "fail") &&
    (v.latency_ms === null || v.latency_ms === undefined || typeof v.latency_ms === "number") &&
    (v.error === null || v.error === undefined || typeof v.error === "string")
  );
}

/** Validates the API's /health/ready payload; returns null when the shape is unexpected. */
export function parseReadiness(body: unknown): Exclude<ApiHealth, { kind: "unreachable" }> | null {
  if (typeof body !== "object" || body === null) return null;
  const b = body as Record<string, unknown>;
  if (b.status !== "ready" && b.status !== "not_ready") return null;
  if (typeof b.checks !== "object" || b.checks === null) return null;

  const checks: Record<string, DependencyCheck> = {};
  for (const [name, raw] of Object.entries(b.checks as Record<string, unknown>)) {
    if (!isCheck(raw)) return null;
    checks[name] = { status: raw.status, latency_ms: raw.latency_ms ?? null, error: raw.error ?? null };
  }
  return { kind: b.status, checks };
}

export async function fetchApiHealth(
  apiBaseUrl: string,
  fetchImpl: typeof fetch = fetch,
  timeoutMs = 3000,
): Promise<ApiHealth> {
  let response: Response;
  try {
    response = await fetchImpl(`${apiBaseUrl}/health/ready`, {
      cache: "no-store",
      headers: { accept: "application/json" },
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (error) {
    const name = error instanceof Error ? error.name : "Error";
    return {
      kind: "unreachable",
      reason: name === "TimeoutError" ? "Request timed out" : "Connection failed",
    };
  }

  if (response.status !== 200 && response.status !== 503) {
    return { kind: "unreachable", reason: `Unexpected HTTP ${response.status}` };
  }
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    return { kind: "unreachable", reason: "Invalid JSON response" };
  }
  return parseReadiness(body) ?? { kind: "unreachable", reason: "Unexpected response shape" };
}
