import { describe, expect } from "vitest";
import { fetchCatalog } from "../src/catalog.js";
import { WizardError } from "../src/errors.js";
import { API_KEY, CATALOG_MODELS, FIXTURE_CATALOG } from "./support/catalog.js";
import { test } from "./support/gradiated-api.js";

const it = test.extend(
  "fetchServedCatalog",
  async ({ serveGradiatedApi }) =>
    async (catalog: unknown) => {
      const api = await serveGradiatedApi({ acceptedKeys: [API_KEY], catalog });

      return fetchCatalog(api.baseUrl, API_KEY);
    },
);

describe("fetchCatalog", () => {
  it("reads names and token limits from the catalog", async ({
    fetchServedCatalog,
  }) => {
    expect(await fetchServedCatalog(FIXTURE_CATALOG)).toEqual(CATALOG_MODELS);
  });

  it("skips entries without an id and falls back to the id for a name", async ({
    fetchServedCatalog,
  }) => {
    const models = await fetchServedCatalog({
      data: [{ name: "Nameless" }, { id: "" }, "text", { id: "vendor/model" }],
    });

    expect(models).toEqual([
      { id: "vendor/model", name: "vendor/model", limit: null },
    ]);
  });

  it("gives no limit unless both the context and output limits are known", async ({
    fetchServedCatalog,
  }) => {
    const [model] = FIXTURE_CATALOG.data;
    const withoutOutput = { ...model, output_modalities: [] };

    const models = await fetchServedCatalog({ data: [withoutOutput] });

    expect(models[0]?.limit).toBeNull();
  });

  it.for([
    [{ data: {} }, "The model catalog response was not understood."],
    ["[]", "The model catalog response was not understood."],
    [{ data: [] }, "The model catalog is empty."],
    [{ data: [{ name: "No id" }] }, "The model catalog is empty."],
  ] as const)(
    "rejects %j",
    async ([catalog, message], { fetchServedCatalog }) => {
      await expect(fetchServedCatalog(catalog)).rejects.toThrow(
        new WizardError(message),
      );
    },
  );
});
