import { describe, expect, it } from "vitest";

import { buildForwardHeaders, copyResponseHeaders, isSafePath } from "./api-proxy";

const config = { apiInternalUrl: "http://api:8000", trustForwardedFor: false };

describe("isSafePath", () => {
  it.each([[["auth", "me"]], [["users", "3f2c0b8e-1d2a-4b9b-9c1e-2a7d5e0f1a2b", "reset-mfa"]]])(
    "allows %j",
    (p) => {
      expect(isSafePath(p)).toBe(true);
    },
  );
  it.each([[[]], [[".."]], [["auth", ".."]], [["a/b"]], [["%2e%2e"]], [["x y"]], [Array(9).fill("a")]])(
    "rejects %j",
    (p) => {
      expect(isSafePath(p)).toBe(false);
    },
  );
});

describe("buildForwardHeaders", () => {
  const incoming = new Headers({
    cookie: "wf_at=abc",
    "x-csrf-token": "t",
    origin: "http://localhost:3000",
    "x-forwarded-for": "6.6.6.6",
    host: "dashboard",
    authorization: "Bearer should-not-pass",
    "x-internal": "nope",
  });

  it("forwards only allow-listed headers", () => {
    const out = buildForwardHeaders(incoming, config);
    expect(out.get("cookie")).toBe("wf_at=abc");
    expect(out.get("x-csrf-token")).toBe("t");
    expect(out.get("origin")).toBe("http://localhost:3000");
    expect(out.get("host")).toBeNull();
    expect(out.get("authorization")).toBeNull();
    expect(out.get("x-internal")).toBeNull();
  });

  it("drops client-supplied X-Forwarded-For unless explicitly trusted", () => {
    expect(buildForwardHeaders(incoming, config).get("x-forwarded-for")).toBeNull();
    expect(buildForwardHeaders(incoming, { ...config, trustForwardedFor: true }).get("x-forwarded-for")).toBe(
      "6.6.6.6",
    );
  });
});

describe("copyResponseHeaders", () => {
  it("keeps every Set-Cookie header and drops others", () => {
    const from = new Headers();
    from.append("set-cookie", "wf_at=1; Path=/; HttpOnly");
    from.append("set-cookie", "wf_rt=2; Path=/; HttpOnly");
    from.set("content-type", "application/json");
    from.set("server", "uvicorn");
    const to = new Headers();
    copyResponseHeaders(from, to);
    expect(to.getSetCookie()).toHaveLength(2);
    expect(to.get("content-type")).toBe("application/json");
    expect(to.get("server")).toBeNull();
  });
});
