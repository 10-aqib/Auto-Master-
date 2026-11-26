import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { StatusPanel } from "./status-panel";

afterEach(cleanup);

describe("StatusPanel", () => {
  it("shows each dependency with its status", () => {
    render(
      <StatusPanel
        health={{
          kind: "not_ready",
          checks: {
            postgres: { status: "ok", latency_ms: 2.5, error: null },
            redis: { status: "fail", latency_ms: null, error: "ConnectionError" },
          },
        }}
      />,
    );
    expect(screen.getByText("Degraded")).toBeTruthy();
    expect(screen.getByText("2.5 ms")).toBeTruthy();
    expect(screen.getByText("Failed (ConnectionError)")).toBeTruthy();
  });

  it("explains when the API is unreachable", () => {
    render(<StatusPanel health={{ kind: "unreachable", reason: "Request timed out" }} />);
    expect(screen.getByText("Unreachable")).toBeTruthy();
    expect(screen.getByText(/Request timed out/)).toBeTruthy();
  });
});
