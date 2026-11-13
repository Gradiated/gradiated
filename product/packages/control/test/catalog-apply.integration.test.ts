import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import { eq, sql } from "drizzle-orm";
import { ModelPropertiesSchema } from "@gradiated/contracts";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { applyCatalog } from "../src/catalog/apply.js";
import {
  catalogModels,
  trainingOnlyModels,
  legacyModels,
} from "../src/catalog/models/index.js";
import { createCatalogService } from "../src/catalog/service.js";
import {
  models,
  tasks,
  workspaces,
  trainingRuns,
  taskVersions,
} from "../src/db/schema/index.js";
import { trainingAdapter } from "./support/training.js";
import { modelInput, seedMember } from "./support/fixtures.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";

describe("catalog apply", () => {
  let testDatabase: TestDatabase;

  beforeAll(async () => {
    testDatabase = await createTestDatabase();
  });

  afterAll(() => testDatabase.dispose());

  it("rejects conflicting aliases before changing the catalog", async () => {
    const first = modelInput({ aliases: ["shared-alias"] });
    for (const second of [
      modelInput({ aliases: ["shared-alias"] }),
      modelInput({ id: "shared-alias" }),
      modelInput({ aliases: ["INVALID-ALIAS"] }),
    ]) {
      await expect(
        applyCatalog(testDatabase.database, [first, second]),
      ).rejects.toThrow();
    }

    const rows = await testDatabase.database
      .select()
      .from(models)
      .where(eq(models.id, first.id));
    expect(rows).toEqual([]);
  });

  it("writes every model in the catalog", async () => {
    await applyCatalog(testDatabase.database);

    const stored = await testDatabase.database
      .select({
        id: models.id,
        aliases: models.aliases,
        properties: models.properties,
      })
      .from(models);
    expect(stored.map((model) => model.id)).toEqual(
      expect.arrayContaining([
        ...catalogModels.map((model) => model.id),
        ...trainingOnlyModels().map((model) => model.id),
      ]),
    );
    expect(
      stored.find((model) => model.id === "deepseek/deepseek-v4.1-flash-1017")
        ?.aliases,
    ).toContain("deepseek/deepseek-v4.1-flash");

    for (const model of stored) {
      expect(model.properties).not.toHaveProperty("type");
      expect(ModelPropertiesSchema.safeParse(model.properties).success).toBe(
        true,
      );
    }
  });

  it("rejects collisions with unmanaged IDs and aliases before writing", async () => {
    const catalog = createCatalogService(testDatabase.database);
    const alias = `unmanaged-${randomUUID()}`;
    const stored = await catalog.upsertModel(modelInput({ aliases: [alias] }));
    const retiredAlias = `retired-alias-${randomUUID()}`;
    await catalog.upsertModel(
      modelInput({ status: "retired", aliases: [retiredAlias] }),
    );

    for (const input of [
      modelInput({ aliases: [stored.id] }),
      modelInput({ aliases: [alias] }),
      modelInput({ id: alias }),
      modelInput({ aliases: [retiredAlias] }),
    ]) {
      await expect(
        applyCatalog(testDatabase.database, [input]),
      ).rejects.toThrow("Conflicting model alias");
      const rows = await testDatabase.database
        .select()
        .from(models)
        .where(eq(models.id, input.id));
      expect(rows).toEqual([]);
    }
  });

  it("transfers aliases atomically and rolls back a failed apply", async () => {
    const catalog = createCatalogService(testDatabase.database);
    const alias = `transfer-${randomUUID()}`;
    const previous = modelInput({ aliases: [alias] });
    const next = modelInput();
    await catalog.upsertModel(previous);
    await catalog.upsertModel(next);
    const owners = async () =>
      testDatabase.database
        .select({ id: models.id })
        .from(models)
        .where(sql`${alias} = any(${models.aliases})`);

    await expect(
      applyCatalog(testDatabase.database, [
        { ...next, aliases: [alias] },
        { ...previous, aliases: [], name: "" },
      ]),
    ).rejects.toThrow();
    expect(await owners()).toEqual([{ id: previous.id }]);

    await applyCatalog(testDatabase.database, [
      { ...next, aliases: [alias] },
      { ...previous, aliases: [] },
    ]);
    expect(await owners()).toEqual([{ id: next.id }]);
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

  it("retires the previous Dealign ID after the requested model qualifies", async () => {
    const catalog = createCatalogService(testDatabase.database);
    const legacy = legacyModels[0]!;
    await catalog.upsertModel({ ...legacy, status: "unavailable" });

    await applyCatalog(testDatabase.database);

    const listed = await catalog.listModels();
    expect(listed.map((model) => model.id)).not.toContain(legacy.id);
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

  it("retires original DeepSeek Flash without redirecting its model ID", async () => {
    const catalog = createCatalogService(testDatabase.database);
    const original = legacyModels.find(
      (model) => model.id === "deepseek/deepseek-v4.1-flash",
    )!;
    await catalog.upsertModel({ ...original, status: "available" });

    await applyCatalog(testDatabase.database);

    const [stored] = await testDatabase.database
      .select()
      .from(models)
      .where(eq(models.id, original.id));
    expect(stored?.status).toBe("retired");
    const listed = await catalog.listModels();
    expect(listed.some((model) => model.id === original.id)).toBe(false);
    expect(listed).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: "deepseek/deepseek-v4.1-flash-1017",
          status: "available",
        }),
      ]),
    );
  });

  it.each(["dealignai/glm-5.3-flash-uncensored-nvfp4", "z-ai/glm-5.3-flash"])(
    "moves active %s selections and disables retired-base training",
    async (legacy) => {
      await applyCatalog(testDatabase.database);
      const renamed = "dealignai/glm-5.3-flash-uncensored";
      const { workspaceId } = await seedMember(testDatabase.database, {
        role: "admin",
      });
      await testDatabase.database
        .update(workspaces)
        .set({ defaultJudgeModel: legacy })
        .where(eq(workspaces.id, workspaceId));
      const taskId = randomUUID();
      await testDatabase.database.insert(tasks).values({
        id: taskId,
        workspaceId,
        name: "Rename migration",
        baseModelId: "z-ai/glm-5.3-flash",
        trainingSchedule: "0 3 * * 1",
        judgeModelId: legacy,
        comparisonModelId: legacy,
      });
      const runId = randomUUID();
      const versionId = randomUUID();
      await testDatabase.database.insert(trainingRuns).values({
        id: runId,
        taskId,
        trigger: "manual",
        stage: "succeeded",
        baseModelId: "z-ai/glm-5.3-flash",
        inputCutoff: new Date(),
        finishedAt: new Date(),
      });
      await testDatabase.database.insert(taskVersions).values({
        id: versionId,
        workspaceId,
        taskId,
        trainingRunId: runId,
        name: "retired-adapter",
        baseModelId: "z-ai/glm-5.3-flash",
        adapter: trainingAdapter,
        status: "available",
      });
      await testDatabase.database
        .update(tasks)
        .set({ productionVersionId: versionId })
        .where(eq(tasks.id, taskId));
      const migration = await readFile(
        new URL(
          "../migrations/0024_retire_stock_glm_adapters.sql",
          import.meta.url,
        ),
        "utf8",
      );

      await testDatabase.database.execute(sql.raw(migration));

      const [workspace] = await testDatabase.database
        .select()
        .from(workspaces)
        .where(eq(workspaces.id, workspaceId));
      const [task] = await testDatabase.database
        .select()
        .from(tasks)
        .where(eq(tasks.id, taskId));
      expect(workspace?.defaultJudgeModel).toBe(renamed);
      const [version] = await testDatabase.database
        .select()
        .from(taskVersions)
        .where(eq(taskVersions.id, versionId));
      expect(version).toMatchObject({
        status: "unavailable",
        adapter: trainingAdapter,
      });
      expect(task).toMatchObject({
        judgeModelId: renamed,
        comparisonModelId: renamed,
        trainingSchedule: null,
        productionVersionId: null,
      });
    },
  );

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
