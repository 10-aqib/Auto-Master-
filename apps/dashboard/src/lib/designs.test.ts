import { describe, expect, it } from "vitest";

import { CONCEPT_CSP, KIND_LABEL, PAGE_SLUGS, formatCost } from "./designs";

describe("designs helpers", () => {
  it("formats thousandths of a cent as dollars", () => {
    expect(formatCost(0)).toBe("$0.0000");
    expect(formatCost(68_000)).toBe("$0.6800");
  });
  it("labels every content kind", () => {
    expect(Object.keys(KIND_LABEL).sort()).toEqual(["assumption", "proposed_copy", "verified_fact"]);
  });
});

describe("concept preview security headers", () => {
  it("next.config applies the concept CSP only to concept routes", async () => {
    const { default: config } = await import("../../next.config");
    const rules = (await config.headers?.()) ?? [];
    const concept = rules.find((r) => r.source === "/api/concepts/:path*");
    const csp = concept?.headers.find((h) => h.key === "Content-Security-Policy")?.value;
    expect(csp).toBe(CONCEPT_CSP);
    expect(CONCEPT_CSP.startsWith("sandbox allow-same-origin;")).toBe(true);
    expect(CONCEPT_CSP).not.toMatch(/allow-(scripts|forms|popups|top-navigation)/);
    expect(CONCEPT_CSP).toContain("default-src 'none'");
    expect(CONCEPT_CSP).toContain("form-action 'none'");
    const app = rules.find((r) => r.source !== "/api/concepts/:path*");
    expect(app?.headers.find((h) => h.key === "X-Frame-Options")?.value).toBe("DENY");
  });
  it("lists the six page slugs in order", () => {
    expect(PAGE_SLUGS).toEqual(["home", "services", "about", "trust", "inquiry", "contact"]);
  });
});
