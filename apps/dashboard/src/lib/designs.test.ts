import { describe, expect, it } from "vitest";

import { KIND_LABEL, formatCost } from "./designs";

describe("designs helpers", () => {
  it("formats thousandths of a cent as dollars", () => {
    expect(formatCost(0)).toBe("$0.0000");
    expect(formatCost(68_000)).toBe("$0.6800");
  });
  it("labels every content kind", () => {
    expect(Object.keys(KIND_LABEL).sort()).toEqual(["assumption", "proposed_copy", "verified_fact"]);
  });
});
