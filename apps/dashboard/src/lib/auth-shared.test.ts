import { describe, expect, it } from "vitest";

import { isApiErrorBody, pathForState, safeNext } from "./auth-shared";

describe("safeNext", () => {
  it.each([
    [undefined, "/"],
    ["/users", "/users"],
    ["/activity?x=1", "/activity?x=1"],
    ["https://evil.example", "/"],
    ["//evil.example", "/"],
    ["/\\evil.example", "/"],
    ["javascript:alert(1)", "/"],
    ["/login", "/"],
    ["/setup/mfa", "/"],
  ])("%s → %s", (input, expected) => {
    expect(safeNext(input)).toBe(expected);
  });
});

describe("pathForState", () => {
  it("routes each restricted state to its step", () => {
    expect(pathForState("mfa_pending")).toBe("/login/mfa");
    expect(pathForState("mfa_enrollment_required")).toBe("/setup/mfa");
    expect(pathForState("password_change_required")).toBe("/setup/password");
    expect(pathForState("active")).toBeNull();
  });
});

describe("isApiErrorBody", () => {
  it("recognises the API error envelope", () => {
    expect(isApiErrorBody({ code: "x", message: "y", correlation_id: null, field_errors: {} })).toBe(true);
    expect(isApiErrorBody({ detail: "nope" })).toBe(false);
    expect(isApiErrorBody(null)).toBe(false);
  });
});
