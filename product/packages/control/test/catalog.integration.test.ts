import { ModelPropertiesInputSchema } from "@gradiated/contracts";
import { eq } from "drizzle-orm";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { ZodError } from "zod";

import {
  createCatalogService,
  type CatalogService,
} from "../src/catalog/service.js";
import { modelDeployments, models } from "../src/db/schema/index.js";
import {
  deploymentInput,
  deploymentRelease,
  modelInput,
  modelProperties,
} from "./support/fixtures.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";

describe("model catalog", () => {
  let testDatabase: TestDatabase;
  let catalog: CatalogService;

  beforeAll(async () => {
    testDatabase = await createTestDatabase();
    catalog = createCatalogService(testDatabase.database);
  });

  afterAll(() => testDatabase.dispose());

  const storedModel = async (id: string) => {
    const [row] = await testDatabase.database
      .select()
      .from(models)
      .where(eq(models.id, id));

    return row;
  };

  const storedDeployment = async (id: string) => {
    const [row] = await testDatabase.database
      .select()
      .from(modelDeployments)
      .where(eq(modelDeployments.id, id));

    return row;
  };

  it("stores normalized properties", async () => {
    const input = modelInput();

    const model = await catalog.upsertModel(input);
    const normalized = ModelPropertiesInputSchema.parse(input.properties);

    expect(model.properties).toEqual(normalized);
    expect((await storedModel(input.id))?.properties).toEqual(normalized);
  });

  it("stores and clears model aliases", async () => {
    const input = modelInput();
    const aliases = ["short-model", "vendor/short-model"];
    const created = await catalog.upsertModel({
      ...input,
      aliases,
    });
    expect(created.aliases).toEqual(aliases);
    expect((await storedModel(input.id))?.aliases).toEqual(aliases);

    const cleared = await catalog.upsertModel(input);
    expect(cleared.aliases).toEqual([]);
    expect((await storedModel(input.id))?.aliases).toEqual([]);
  });

  it("stores, replaces and clears an OpenRouter mapping", async () => {
    const input = modelInput();

    const created = await catalog.upsertModel(input);
    expect(created.openrouterModelId).toBeNull();

    const mapped = await catalog.upsertModel({
      ...input,
      openrouterModelId: "author/model-a",
    });
    expect(mapped.openrouterModelId).toBe("author/model-a");
    expect((await storedModel(input.id))?.openrouterModelId).toBe(
      "author/model-a",
    );

    const cleared = await catalog.upsertModel(input);
    expect(cleared.openrouterModelId).toBeNull();
    expect((await storedModel(input.id))?.openrouterModelId).toBeNull();
  });

  it("refuses an OpenRouter variant in the record and in the table", async () => {
    const input = modelInput();

    await expect(
      catalog.upsertModel({ ...input, openrouterModelId: "author/model:free" }),
    ).rejects.toBeInstanceOf(ZodError);
    await expect(
      testDatabase.database.insert(models).values({
        id: `${input.id}-raw`,
        name: "Raw",
        status: "available",
        properties: ModelPropertiesInputSchema.parse(input.properties),
        openrouterModelId: "author/model:free",
      }),
    ).rejects.toThrow();
  });

  it("updates the name, status and properties of an existing model", async () => {
    const input = modelInput();
    const created = await catalog.upsertModel(input);
    const properties = { ...modelProperties(), description: "Updated." };

    const updated = await catalog.upsertModel({
      ...input,
      name: "Renamed",
      status: "unavailable",
      properties,
    });

    expect(updated).toMatchObject({
      name: "Renamed",
      status: "unavailable",
      properties: { description: "Updated." },
      createdAt: created.createdAt,
    });
    expect(await storedModel(input.id)).toMatchObject({
      name: "Renamed",
      status: "unavailable",
    });
  });

  it("lists models that are not retired in creation order", async () => {
    const earlier = new Date("2020-01-01T00:00:00.000Z");
    const later = new Date("2020-01-02T00:00:00.000Z");
    const seeded = [
      { id: "listing/c", createdAt: earlier, status: "available" },
      { id: "listing/b", createdAt: earlier, status: "unavailable" },
      { id: "listing/a", createdAt: later, status: "available" },
      { id: "listing/retired", createdAt: earlier, status: "retired" },
    ] as const;

    for (const { id, createdAt, status } of seeded) {
      await catalog.upsertModel(modelInput({ id, status }));
      await testDatabase.database
        .update(models)
        .set({ createdAt })
        .where(eq(models.id, id));
    }

    const listed = (await catalog.listModels())
      .map(({ id }) => id)
      .filter((id) => id.startsWith("listing/"));

    expect(listed).toEqual(["listing/b", "listing/c", "listing/a"]);
  });

  it("stores a deployment and updates it without moving it to another model", async () => {
    const model = await catalog.upsertModel(modelInput());
    const other = await catalog.upsertModel(modelInput());
    const input = deploymentInput(model.id);

    const created = await catalog.upsertModelDeployment(input);
    const release = { ...deploymentRelease(), model_revision: "next" };
    const updated = await catalog.upsertModelDeployment({
      ...input,
      modelId: other.id,
      status: "draining",
      provider: "aws",
      region: "us-east",
      faultDomain: "us-east/rack-2",
      serviceUrl: "https://next-runtime.example.test",
      release,
    });

    expect(created).toMatchObject({
      id: input.id,
      modelId: model.id,
      status: "available",
      provider: "runpod",
      region: "eu-west",
      faultDomain: "eu-west/rack-1",
      serviceUrl: "https://runtime.example.test",
      release: input.release,
    });
    expect(created).not.toHaveProperty("instanceId");
    expect(updated).toMatchObject({
      id: input.id,
      modelId: model.id,
      status: "draining",
      provider: "aws",
      region: "us-east",
      faultDomain: "us-east/rack-2",
      serviceUrl: "https://next-runtime.example.test",
      release,
      createdAt: created.createdAt,
    });
    expect(await storedDeployment(input.id)).toMatchObject({
      modelId: model.id,
      status: "draining",
      release,
    });
  });

  it.each([
    ["service URL", { serviceUrl: "ftp://runtime.example.test" }],
    ["provider", { provider: "RunPod" }],
  ] as const)(
    "rejects a deployment with an invalid %s",
    async (_, overrides) => {
      const model = await catalog.upsertModel(modelInput());
      const input = deploymentInput(model.id, overrides);

      await expect(catalog.upsertModelDeployment(input)).rejects.toBeInstanceOf(
        ZodError,
      );
      expect(await storedDeployment(input.id)).toBeUndefined();
    },
  );

  it("rejects a deployment of an unknown model", async () => {
    const input = deploymentInput("unknown/model");

    await expect(catalog.upsertModelDeployment(input)).rejects.toMatchObject({
      cause: { code: "23503" },
    });
    expect(await storedDeployment(input.id)).toBeUndefined();
  });
  it("rejects invalid properties before writing and corrupt properties on reads", async () => {
    const input = modelInput();
    await expect(
      catalog.upsertModel({
        ...input,
        properties: {
          ...input.properties,
          description: 123 as unknown as string,
        },
      }),
    ).rejects.toBeInstanceOf(ZodError);
    expect(await storedModel(input.id)).toBeUndefined();

    const model = await catalog.upsertModel(input);
    await testDatabase.database
      .update(models)
      .set({
        properties: { ...model.properties, schema_version: 2 as 1 },
      })
      .where(eq(models.id, model.id));

    try {
      await expect(catalog.listModels()).rejects.toBeInstanceOf(ZodError);
    } finally {
      await testDatabase.database
        .update(models)
        .set({ properties: model.properties })
        .where(eq(models.id, model.id));
    }
  });

  it("rejects invalid deployment release JSON before writing", async () => {
    const model = await catalog.upsertModel(modelInput());
    const input = deploymentInput(model.id);
    await expect(
      catalog.upsertModelDeployment({
        ...input,
        release: { ...input.release, schema_version: 2 as 1 },
      }),
    ).rejects.toBeInstanceOf(ZodError);
    expect(await storedDeployment(input.id)).toBeUndefined();
  });
});
