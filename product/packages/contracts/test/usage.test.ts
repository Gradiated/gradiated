import { describe, expect, it } from "vitest";

import { GenerationListQuerySchema, UsageQuerySchema } from "../src/index.js";

const from = "2026-01-01T00:00:00.000Z";
const ninetyThreeDaysLater = new Date(
  Date.parse(from) + 93 * 24 * 60 * 60 * 1_000,
);

describe("UsageQuerySchema", () => {
  it("accepts a range of exactly 93 days", () => {
    const to = ninetyThreeDaysLater.toISOString();

    expect(UsageQuerySchema.safeParse({ from, to }).success).toBe(true);
  });

  it.each([
    [
      "a range longer than 93 days",
      new Date(ninetyThreeDaysLater.getTime() + 1).toISOString(),
    ],
    ["an empty range", from],
  ])("rejects %s", (_, to) => {
    const result = UsageQuerySchema.safeParse({ from, to });

    expect(result.success).toBe(false);
    expect(result.error?.issues.map(({ path }) => path)).toEqual([["to"]]);
  });
});

describe("GenerationListQuerySchema", () => {
  const range = { from, to: "2026-01-02T00:00:00.000Z" };

  it("coerces the limit", () => {
    expect(
      GenerationListQuerySchema.parse({ ...range, limit: "50" }).limit,
    ).toBe(50);
  });

  it("defaults the limit and sort", () => {
    expect(GenerationListQuerySchema.parse(range)).toMatchObject({
      limit: 25,
      sort: "newest",
    });
  });

  it.each(["0", "101"])("rejects limit %s", (limit) => {
    expect(
      GenerationListQuerySchema.safeParse({ ...range, limit }).success,
    ).toBe(false);
  });
});
