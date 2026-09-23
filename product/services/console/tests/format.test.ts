import { describe, expect, it } from "vitest";

import {
  formatElapsed,
  formatLatency,
  formatNanoUsd,
  formatPercent,
  formatRatio,
  formatUsd,
} from "@/lib/format";

describe("formatUsd", () => {
  it.each([
    [0, "$0.00"],
    [12.5, "$12.50"],
    [1234.5, "$1,234.50"],
    [0.0123, "$0.0123"],
    [0.000032, "$0.0000320"],
    [-0.000032, "-$0.0000320"],
  ])("formats %d as %s", (value, expected) => {
    expect(formatUsd(value)).toBe(expected);
  });

  it("formats a non-finite value without throwing", () => {
    expect(formatUsd(Number.POSITIVE_INFINITY)).toBe("$∞");
  });
});

describe("formatNanoUsd", () => {
  it("formats bigint, string and number nano-USD identically", () => {
    expect(formatNanoUsd(1_500_000_000n)).toBe("$1.50");
    expect(formatNanoUsd("1500000000")).toBe("$1.50");
    expect(formatNanoUsd(1_500_000_000)).toBe("$1.50");
  });

  it("keeps significant digits below a cent", () => {
    expect(formatNanoUsd(32_000n)).toBe("$0.0000320");
  });
});

describe("formatLatency", () => {
  it.each([
    [850, "850 ms"],
    [1_500, "1.5 s"],
  ])("formats %d ms as %s", (ms, expected) => {
    expect(formatLatency(ms)).toBe(expected);
  });
});

describe("formatElapsed", () => {
  it.each([
    [0, "1s"],
    [59_000, "59s"],
    [90_000, "2 min"],
    [5_400_000, "1.5 h"],
  ])("formats %d ms as %s", (ms, expected) => {
    expect(formatElapsed(ms)).toBe(expected);
  });
});

describe("formatPercent", () => {
  it.each([
    [0, "0%"],
    [0.125, "13%"],
    [1, "100%"],
  ])("formats %d as %s", (fraction, expected) => {
    expect(formatPercent(fraction)).toBe(expected);
  });
});

describe("formatRatio", () => {
  it.each([
    [0, { tone: "neutral", label: "n/a" }],
    [-2, { tone: "neutral", label: "n/a" }],
    [Number.NaN, { tone: "neutral", label: "n/a" }],
    [Number.POSITIVE_INFINITY, { tone: "neutral", label: "n/a" }],
    [0.5, { tone: "bad", label: "2.0× slower" }],
    [0.05, { tone: "bad", label: "20× slower" }],
    [1, { tone: "good", label: "1.0× faster" }],
    [2.46, { tone: "good", label: "2.5× faster" }],
    [12.4, { tone: "good", label: "12× faster" }],
  ])("describes an advantage of %d", (advantage, expected) => {
    expect(formatRatio(advantage, "faster", "slower")).toEqual(expected);
  });

  it("treats a zero divisor as not comparable", () => {
    expect(formatRatio(50 / 0, "faster", "slower").label).toBe("n/a");
  });
});
