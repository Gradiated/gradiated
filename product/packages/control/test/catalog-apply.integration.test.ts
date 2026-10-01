import { eq } from "drizzle-orm";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { applyCatalog } from "../src/catalog/apply.js";
import {
  catalogModels,
  createQwenSftModelConfiguration,
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
      .select({ id: models.id })
      .from(models);
    expect(stored.map((model) => model.id)).toEqual(
      expect.arrayContaining([
        ...catalogModels.map((model) => model.id),
        createQwenSftModelConfiguration().id,
      ]),
    );
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
