import { describe, expect, it } from "vitest";

import { parseUsdToNanoUsd } from "@/lib/money";

describe("parseUsdToNanoUsd", () => {
  it.each([
    ["50", 50_000_000_000n],
    ["10.5", 10_500_000_000n],
    ["10.05", 10_050_000_000n],
    ["0.01", 10_000_000n],
    ["0", 0n],
  ])("parses %s exactly", (input, expected) => {
    expect(parseUsdToNanoUsd(input)).toBe(expected);
  });

  it.each(["", "1.234", "-1", "1.", ".5", " 5", "1e3", "$5"])(
    "rejects %j",
    (input) => {
      expect(() => parseUsdToNanoUsd(input)).toThrow(RangeError);
    },
  );
});
