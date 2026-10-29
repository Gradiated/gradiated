import { eq } from "drizzle-orm";
import { ModelPropertiesSchema } from "@gradiated/contracts";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { applyCatalog } from "../src/catalog/apply.js";
import {
  catalogModels,
  trainingOnlyModels,
  legacyModels,
} from "../src/catalog/models/index.js";
import { createCatalogService } from "../src/catalog/service.js";
import { models } from "../src/db/schema/index.js";
import { modelInput } from "./support/fixtures.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";

describe("catalog apply", () => {
  let testDatabase: TestDatabase;

  beforeAll(async () => {
    testDatabase = await createTestDatabase();
  });

  afterAll(() => testDatabase.dispose());

  it("writes every model in the catalog", async () => {
    await applyCatalog(testDatabase.database);

    const stored = await testDatabase.database
      .select({ id: models.id, properties: models.properties })
      .from(models);
    expect(stored.map((model) => model.id)).toEqual(
      expect.arrayContaining([
        ...catalogModels.map((model) => model.id),
        ...trainingOnlyModels().map((model) => model.id),
      ]),
    );

    for (const model of stored) {
      expect(model.properties).not.toHaveProperty("type");
      expect(ModelPropertiesSchema.safeParse(model.properties).success).toBe(
        true,
      );
    }
  });

  it("puts a model edited in the database back to its catalog definition", async () => {
    const [kev] = catalogModels.filter(
      (model) => model.id === "jaredpalmer/kev-9b",
    );
    await applyCatalog(testDatabase.database);
    await testDatabase.database
      .update(models)
      .set({ name: "Edited by hand", status: "unavailable" })
      .where(eq(models.id, kev!.id));

    await applyCatalog(testDatabase.database);

    const [stored] = await testDatabase.database
      .select()
      .from(models)
      .where(eq(models.id, kev!.id));
    expect(stored).toMatchObject({ name: kev!.name, status: kev!.status });
  });

  it("keeps the previous Dealign ID available while exposing the requested public name", async () => {
    const catalog = createCatalogService(testDatabase.database);
    const legacy = legacyModels[0]!;
    await catalog.upsertModel({ ...legacy, status: "unavailable" });

    await applyCatalog(testDatabase.database);

    const listed = await catalog.listModels();
    expect(listed).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ id: legacy.id, status: "available" }),
      ]),
    );
    expect(listed).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: "dealignai/glm-5.3-flash-uncensored",
          name: "GLM-5.3 Flash Uncensored",
          status: "available",
        }),
      ]),
    );
  });

  it("reports models the catalog does not define without changing them", async () => {
    const manual = await createCatalogService(
      testDatabase.database,
    ).upsertModel(modelInput());

    const result = await applyCatalog(testDatabase.database);

    expect(result.unmanaged).toContain(manual.id);
    const [stored] = await testDatabase.database
      .select()
      .from(models)
      .where(eq(models.id, manual.id));
    expect(stored?.status).toBe("available");
  });
});
