import { describe, expect, it } from "vitest";

import { DashboardConfigError, parseServerConfig } from "./server-config";

describe("parseServerConfig", () => {
  it("defaults to the local API", () => {
    expect(parseServerConfig({})).toEqual({
      apiInternalUrl: "http://localhost:8000",
      trustForwardedFor: false,
    });
  });

  it("normalises trailing slashes", () => {
    expect(parseServerConfig({ API_INTERNAL_URL: "http://api:8000/" }).apiInternalUrl).toBe(
      "http://api:8000",
    );
  });

  it("parses DASHBOARD_TRUST_FORWARDED_FOR strictly", () => {
    expect(parseServerConfig({ DASHBOARD_TRUST_FORWARDED_FOR: "true" }).trustForwardedFor).toBe(true);
    expect(() => parseServerConfig({ DASHBOARD_TRUST_FORWARDED_FOR: "yes" })).toThrow(DashboardConfigError);
  });

  it.each(["not a url", "ftp://api:21", "http://user:pass@api:8000"])("rejects %s", (value) => {
    expect(() => parseServerConfig({ API_INTERNAL_URL: value })).toThrow(DashboardConfigError);
  });
});
