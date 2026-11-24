import type { ControlDatabase, SkippedCatalogModel } from "@gradiated/control";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createCatalogApply } from "../src/catalog-apply.js";

afterEach(() => {
  vi.restoreAllMocks();
});

const logged = (log: { mock: { calls: unknown[][] } }, event: string) =>
  log.mock.calls
    .map(([line]) => JSON.parse(String(line)) as Record<string, unknown>)
    .filter((entry) => entry.event === event);

describe("catalog apply loop", () => {
  it("warns about unmanaged models once per change, not every pass", async () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const results = [["vendor/manual"], ["vendor/manual"], []];
    const apply = createCatalogApply({} as ControlDatabase, async () => ({
      applied: 5,
      unmanaged: results.shift() ?? [],
      skipped: [],
    }));

    await apply();
    await apply();
    await apply();

    expect(logged(log, "catalog_model_unmanaged")).toEqual([
      expect.objectContaining({ model_id: "vendor/manual" }),
    ]);
  });

  it("warns once about an owned model waiting for its organization", async () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const skipped: SkippedCatalogModel[] = [
      { id: "posthog/jeeves", reason: "owner_missing" },
    ];
    const apply = createCatalogApply({} as ControlDatabase, async () => ({
      applied: 5,
      unmanaged: [],
      skipped,
    }));

    await apply();
    await apply();

    expect(logged(log, "catalog_model_skipped")).toEqual([
      expect.objectContaining({
        model_id: "posthog/jeeves",
        reason: "owner_missing",
      }),
    ]);
  });
});
