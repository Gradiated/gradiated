import type { ControlDatabase } from "@gradiated/control";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createCatalogApply } from "../src/catalog-apply.js";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("catalog apply loop", () => {
  it("warns about unmanaged models once per change, not every pass", async () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const results = [["vendor/manual"], ["vendor/manual"], []];
    const apply = createCatalogApply({} as ControlDatabase, async () => ({
      applied: 5,
      unmanaged: results.shift() ?? [],
    }));

    await apply();
    await apply();
    await apply();

    const unmanaged = log.mock.calls
      .map(([line]) => JSON.parse(String(line)) as Record<string, unknown>)
      .filter((entry) => entry.event === "catalog_model_unmanaged");
    expect(unmanaged).toEqual([
      expect.objectContaining({ model_id: "vendor/manual" }),
    ]);
  });
});
