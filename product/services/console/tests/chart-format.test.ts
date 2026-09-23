import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { compactNumber, utcDayLabel } from "@/pages/chart-format";

const zone = process.env.TZ;

beforeAll(() => {
  process.env.TZ = "America/Los_Angeles";
});

afterAll(() => {
  process.env.TZ = zone;
});

describe("utcDayLabel", () => {
  it("labels a UTC calendar day as that day west of UTC", () => {
    const label = utcDayLabel("2026-09-01");

    expect(label).toMatch(/\b1\b/);
    expect(label).not.toMatch(/31/);
  });
});

describe("compactNumber", () => {
  it("accepts the decimal strings the usage API returns", () => {
    expect(compactNumber("1250000")).toBe(compactNumber(1_250_000));
  });
});
