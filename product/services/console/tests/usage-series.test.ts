import { describe, expect, it } from "vitest";

import { dailyUsageSeries, usageDateRange } from "@/pages/usage-series";

describe("usageDateRange", () => {
  it("ends at the next UTC midnight and spans whole days", () => {
    expect(usageDateRange("7d", new Date("2026-09-23T15:30:00.000Z"))).toEqual({
      from: "2026-09-17T00:00:00.000Z",
      to: "2026-09-24T00:00:00.000Z",
    });
  });
});

describe("dailyUsageSeries", () => {
  it("fills every day of the range and converts nano-USD to USD", () => {
    const series = dailyUsageSeries(
      [
        {
          date: "2026-09-22",
          charge: "2500000000",
          generation_count: "4",
          input_tokens: "100",
          output_tokens: "50",
        },
      ],
      { from: "2026-09-21T00:00:00.000Z", to: "2026-09-24T00:00:00.000Z" },
    );

    expect(series).toEqual([
      { date: "2026-09-21", cost: 0, requests: 0, tokens: 0 },
      { date: "2026-09-22", cost: 2.5, requests: 4, tokens: 150 },
      { date: "2026-09-23", cost: 0, requests: 0, tokens: 0 },
    ]);
  });
});
