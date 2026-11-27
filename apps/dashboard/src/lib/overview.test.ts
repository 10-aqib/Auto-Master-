import { describe, expect, it } from "vitest";

import { QUEUE_LABEL, formatAge } from "./overview";

describe("overview helpers", () => {
  it("formats queue ages", () => {
    expect(formatAge(30)).toBe("30s");
    expect(formatAge(600)).toBe("10m");
    expect(formatAge(7200)).toBe("2h");
    expect(formatAge(259200)).toBe("3d");
  });
  it("labels every review queue", () => {
    expect(Object.keys(QUEUE_LABEL)).toHaveLength(7);
  });
});
