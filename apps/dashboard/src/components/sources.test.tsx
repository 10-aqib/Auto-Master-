import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { PlacesAttribution } from "./attribution";
import { UsageMeter } from "./usage-meter";
import { VerificationResult } from "./verification-result";
import { formatMinor, reasonText } from "@/lib/sources";

afterEach(cleanup);

describe("PlacesAttribution", () => {
  it("renders Google Maps attribution per Google's text rules", () => {
    render(<PlacesAttribution text="Google Maps" isMock={false} />);
    const el = screen.getByTestId("attribution");
    expect(el.textContent).toBe("Google Maps");
    expect(el.getAttribute("translate")).toBe("no");
    expect(el.className).toContain("whitespace-nowrap");
    expect(el.style.fontFamily).toContain("Roboto");
  });

  it("labels mock data clearly", () => {
    render(<PlacesAttribution text="Mock data - not Google Maps" isMock />);
    expect(screen.getByTestId("attribution").textContent).toBe("Mock data - not Google Maps");
  });
});

describe("UsageMeter", () => {
  const base = {
    provider: "google_places",
    currency: "USD",
    today: { requests: 9, cost_minor: 29 },
    month: { requests: 40, cost_minor: 128 },
    daily_budget_minor: 100,
    daily_request_cap: 10,
    budget_ratio: 0.29,
    cap_ratio: 0.9,
    warning: true,
    exhausted: false,
  };

  it("shows spend and request meters with an 80% warning", () => {
    render(<UsageMeter usage={base} />);
    expect(screen.getByText("$0.29 of $1.00")).toBeTruthy();
    expect(screen.getByText("9 of 10")).toBeTruthy();
    expect(screen.getByRole("meter", { name: "Requests today" }).getAttribute("aria-valuenow")).toBe("90");
    expect(screen.getByText(/Over 80%/)).toBeTruthy();
  });

  it("states when limits block new requests", () => {
    render(<UsageMeter usage={{ ...base, exhausted: true, cap_ratio: 1 }} />);
    expect(screen.getByText(/new requests are blocked/)).toBeTruthy();
  });
});

describe("VerificationResult", () => {
  it("explains held results in plain language", () => {
    render(
      <VerificationResult
        prospectId={null}
        v={{
          id: "1",
          status: "HOLD",
          method: "m",
          reason_codes: ["robots_disallowed"],
          confidence: null,
          candidate_url: "https://x.example/",
          final_url: null,
          domain: null,
          candidate_origin: "owner",
          evidence: {},
          checked_at: "2026-11-26T00:00:00Z",
          prospect_id: null,
          place_identifier_id: null,
        }}
      />,
    );
    expect(screen.getByText(/On hold/)).toBeTruthy();
    expect(screen.getByText(/robots.txt asks automated visitors/)).toBeTruthy();
  });
});

describe("helpers", () => {
  it("formats minor units and reason codes", () => {
    expect(formatMinor(320, "USD")).toBe("$3.20");
    expect(reasonText("http_503")).toBe("The website answered with HTTP 503.");
    expect(reasonText("unreachable_timeout")).toBe("The website could not be reached.");
    expect(reasonText("custom_code")).toBe("custom_code");
  });
});
