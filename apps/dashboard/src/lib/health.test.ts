import { describe, expect, it, vi } from "vitest";

import { fetchApiHealth, parseReadiness } from "./health";

const ready = {
  status: "ready",
  checks: {
    postgres: { status: "ok", latency_ms: 1.2, error: null },
    redis: { status: "ok", latency_ms: 0.4, error: null },
  },
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

describe("parseReadiness", () => {
  it("accepts a ready payload", () => {
    expect(parseReadiness(ready)).toEqual({ kind: "ready", checks: ready.checks });
  });

  it("rejects unexpected shapes", () => {
    expect(parseReadiness(null)).toBeNull();
    expect(parseReadiness({ status: "great", checks: {} })).toBeNull();
    expect(parseReadiness({ status: "ready", checks: { db: { status: "maybe" } } })).toBeNull();
  });
});

describe("fetchApiHealth", () => {
  it("returns ready on HTTP 200", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(ready));
    const result = await fetchApiHealth("http://api.test", fetchImpl as unknown as typeof fetch);
    expect(result.kind).toBe("ready");
    expect(fetchImpl).toHaveBeenCalledWith(
      "http://api.test/health/ready",
      expect.objectContaining({ cache: "no-store" }),
    );
  });

  it("returns not_ready on HTTP 503", async () => {
    const body = {
      status: "not_ready",
      checks: { redis: { status: "fail", latency_ms: null, error: "ConnectionError" } },
    };
    const result = await fetchApiHealth("http://api.test", (async () =>
      jsonResponse(body, 503)) as unknown as typeof fetch);
    expect(result).toEqual({ kind: "not_ready", checks: body.checks });
  });

  it("returns unreachable on network failure without leaking the error message", async () => {
    const failing = (async () => {
      throw new TypeError("connect ECONNREFUSED 10.0.0.5:8000");
    }) as unknown as typeof fetch;
    const result = await fetchApiHealth("http://api.test", failing);
    expect(result).toEqual({ kind: "unreachable", reason: "Connection failed" });
  });

  it("returns unreachable on unexpected status or body", async () => {
    expect(
      (await fetchApiHealth("http://x", (async () => jsonResponse({}, 500)) as unknown as typeof fetch)).kind,
    ).toBe("unreachable");
    expect(
      (await fetchApiHealth("http://x", (async () => new Response("nope")) as unknown as typeof fetch)).kind,
    ).toBe("unreachable");
    expect(
      (
        await fetchApiHealth("http://x", (async () =>
          jsonResponse({ status: "ready" })) as unknown as typeof fetch)
      ).kind,
    ).toBe("unreachable");
  });
});
