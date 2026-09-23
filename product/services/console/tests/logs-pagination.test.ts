import { describe, expect, it } from "vitest";

import {
  dateRange,
  firstPage,
  generationLogParams,
  logQueryKey,
  nextPage,
  pageCursors,
  previousPage,
  type LogFilters,
} from "@/pages/logs-filters";

const RANGE = {
  from: "2026-09-22T12:00:00.000Z",
  to: "2026-09-23T12:00:00.000Z",
};

const unfiltered: LogFilters = {
  range: "24h",
  status: "all",
  model: "all",
  apiKeyId: "all",
  sort: "newest",
  search: "",
};

describe("pagination", () => {
  const key = logQueryKey(unfiltered, RANGE);

  it("returns to the first page after next then previous", () => {
    const second = nextPage(firstPage(key), key, "cursor-2");
    const third = nextPage(second, key, "cursor-3");

    expect(second).toEqual({ queryKey: key, cursors: ["cursor-2"] });
    expect(third).toEqual({
      queryKey: key,
      cursors: ["cursor-2", "cursor-3"],
    });
    expect(previousPage(second, key)).toEqual(firstPage(key));
  });

  it("stays on the first page when there is no previous page", () => {
    expect(previousPage(firstPage(key), key)).toEqual(firstPage(key));
  });

  it("drops back to the first page when the filters change", () => {
    const changed = logQueryKey({ ...unfiltered, status: "failed" }, RANGE);
    const third = nextPage(
      nextPage(firstPage(key), key, "cursor-2"),
      key,
      "cursor-3",
    );

    expect(pageCursors(third, key)).toEqual(["cursor-2", "cursor-3"]);
    expect(pageCursors(third, changed)).toEqual([]);
    expect(nextPage(third, changed, "cursor-9")).toEqual({
      queryKey: changed,
      cursors: ["cursor-9"],
    });
    expect(previousPage(third, changed)).toEqual(firstPage(changed));
  });

  it("drops back to the first page when the range is refreshed", () => {
    const refreshed = logQueryKey(
      unfiltered,
      dateRange("24h", new Date("2026-09-23T12:05:00.000Z")),
    );
    const second = nextPage(firstPage(key), key, "cursor-2");

    expect(refreshed).not.toBe(key);
    expect(pageCursors(second, refreshed)).toEqual([]);
  });
});

describe("generationLogParams", () => {
  it("omits unset filters and the cursor of the first page", () => {
    expect(generationLogParams(unfiltered, RANGE, undefined)).toEqual({
      ...RANGE,
      limit: 25,
      sort: "newest",
    });
  });

  it("sends every set filter and the page cursor", () => {
    const filters: LogFilters = {
      range: "7d",
      status: "failed",
      model: "google/gemma-4-31b-it",
      apiKeyId: "key-1",
      sort: "highest_cost",
      search: "gen_1",
    };

    expect(generationLogParams(filters, RANGE, "cursor-2")).toEqual({
      ...RANGE,
      limit: 25,
      sort: "highest_cost",
      cursor: "cursor-2",
      status: "failed",
      model: "google/gemma-4-31b-it",
      api_key_id: "key-1",
      search: "gen_1",
    });
  });
});

describe("dateRange", () => {
  it.each([
    ["24h", "2026-09-22T12:00:00.000Z"],
    ["7d", "2026-09-16T12:00:00.000Z"],
    ["30d", "2026-08-24T12:00:00.000Z"],
  ] as const)("starts %s before now", (key, from) => {
    expect(dateRange(key, new Date(RANGE.to))).toEqual({ from, to: RANGE.to });
  });
});
