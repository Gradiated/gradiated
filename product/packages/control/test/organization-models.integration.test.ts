import { randomUUID } from "node:crypto";
import { eq } from "drizzle-orm";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { applyCatalog } from "../src/catalog/apply.js";
import type { CatalogModelInput } from "../src/catalog/service.js";
import { createCatalogService } from "../src/catalog/service.js";
import {
  modelDeployments,
  models,
  organizations,
  tasks,
  taskVersions,
} from "../src/db/schema/index.js";
import { createKubernetesDeploymentStore } from "../src/deployments/kubernetes.js";
import { createInstanceService } from "../src/instances/service.js";
import { trainingAdapter } from "./support/training.js";
import { requireChangeableSlug } from "../src/organizations/slugs.js";
import {
  modelNameProblem,
  OWNED_MODEL_NAME,
} from "../src/training/model-names.js";
import { createTrainingStore } from "../src/training/store.js";
import {
  deploymentInput,
  deploymentRelease,
  modelInput,
  ownedModelDefinition,
  seedMember,
} from "./support/fixtures.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";

describe("organization-owned models", () => {
  let testDatabase: TestDatabase;

  beforeAll(async () => {
    testDatabase = await createTestDatabase();
  });

  afterAll(() => testDatabase.dispose());

  const seedOwner = async () => {
    const member = await seedMember(testDatabase.database, { role: "member" });
    const slug = `owner-${randomUUID().slice(0, 8)}`;
    await testDatabase.database
      .update(organizations)
      .set({ slug })
      .where(eq(organizations.id, member.organizationId));

    return { ...member, slug };
  };

  // Writes a version of a new task, which claims its name if it can.
  const claimTask = async (
    owner: { workspaceId: string },
    name: string,
  ): Promise<string | null> => {
    const baseModel = await createCatalogService(
      testDatabase.database,
    ).upsertModel(modelInput());
    const taskId = randomUUID();
    await testDatabase.database.insert(tasks).values({
      id: taskId,
      workspaceId: owner.workspaceId,
      name,
      baseModelId: baseModel.id,
    });
    await testDatabase.database.insert(taskVersions).values({
      id: randomUUID(),
      workspaceId: owner.workspaceId,
      taskId,
      name: "v1",
      baseModelId: baseModel.id,
      adapter: trainingAdapter,
      status: "unavailable",
    });
    const [task] = await testDatabase.database
      .select({ organizationId: tasks.organizationId })
      .from(tasks)
      .where(eq(tasks.id, taskId));

    return task!.organizationId;
  };

  const catalog = (input: ReturnType<typeof modelInput>) =>
    createCatalogService(testDatabase.database).upsertModel(input);

  const stored = async (id: string) =>
    (
      await testDatabase.database.select().from(models).where(eq(models.id, id))
    )[0];

  it("defaults existing rows to public catalog models", async () => {
    const model = await createCatalogService(testDatabase.database).upsertModel(
      modelInput(),
    );

    expect(model).toMatchObject({ organizationId: null, type: "chat" });
  });

  it("gives a definition to the organization with its slug and hides it from public lists", async () => {
    const owner = await seedOwner();
    const definition = ownedModelDefinition(owner.slug);
    const catalog = createCatalogService(testDatabase.database);

    const result = await applyCatalog(testDatabase.database, [definition]);

    expect(result).toMatchObject({ applied: 1, skipped: [] });
    expect(result.unmanaged).not.toContain(definition.id);
    expect(await stored(definition.id)).toMatchObject({
      organizationId: owner.organizationId,
      type: "chat",
    });
    expect((await catalog.listModels()).map((model) => model.id)).not.toContain(
      definition.id,
    );
    expect(
      (
        await catalog.listModels({
          includeRetired: true,
          includeOrganizationModels: true,
        })
      ).map((model) => model.id),
    ).toContain(definition.id);
  });

  it("records a decision model's declared type and refuses chat deployments for it", async () => {
    const owner = await seedOwner();
    const definition = ownedModelDefinition(owner.slug, { type: "decision" });
    const catalog = createCatalogService(testDatabase.database);
    await applyCatalog(testDatabase.database, [definition]);

    await catalog.upsertModelDeployment(
      deploymentInput(definition.id, {
        release: { ...deploymentRelease(), protocol: "system_one" },
      }),
    );
    await expect(
      catalog.upsertModelDeployment(deploymentInput(definition.id)),
    ).rejects.toMatchObject({ code: "conflict" });

    expect(await stored(definition.id)).toMatchObject({ type: "decision" });
  });

  it("requires every model to declare a known type", async () => {
    const owner = await seedOwner();
    const { type: _type, ...untyped } = ownedModelDefinition(owner.slug);
    const { type: _chat, ...publicUntyped } = modelInput();

    for (const definition of [untyped, publicUntyped])
      await expect(
        applyCatalog(testDatabase.database, [
          definition as unknown as CatalogModelInput,
        ]),
      ).rejects.toThrow("must declare its type");
    await expect(
      testDatabase.database
        .update(models)
        .set({ type: "other" as "chat" })
        .where(eq(models.id, (await catalog(modelInput())).id)),
    ).rejects.toThrow();
  });

  it("withdraws deployments that no longer serve a model whose type changed", async () => {
    const model = modelInput();
    const service = createCatalogService(testDatabase.database);
    await service.upsertModel(model);
    const chat = deploymentInput(model.id);
    await service.upsertModelDeployment(chat);

    await service.upsertModel({ ...model, type: "decision" });

    const [deployment] = await testDatabase.database
      .select({ status: modelDeployments.status })
      .from(modelDeployments)
      .where(eq(modelDeployments.id, chat.id));
    expect(deployment?.status).toBe("unavailable");
  });

  it("refuses an owned ID that isn't lowercase", async () => {
    const owner = await seedOwner();

    await expect(
      testDatabase.database.insert(models).values({
        id: `${owner.slug}/Jeeves`,
        name: "Upper",
        type: "chat",
        status: "available",
        properties: (await catalog(modelInput())).properties,
        organizationId: owner.organizationId,
      }),
    ).rejects.toThrow();
  });

  it("refuses a SystemOne deployment for a public chat model", async () => {
    const model = await catalog(modelInput());

    await expect(
      createCatalogService(testDatabase.database).upsertModelDeployment(
        deploymentInput(model.id, {
          release: { ...deploymentRelease(), protocol: "system_one" },
        }),
      ),
    ).rejects.toMatchObject({ code: "conflict" });
  });

  it("withdraws a pod whose release can't serve its organization model's type", async () => {
    const owner = await seedOwner();
    const definition = ownedModelDefinition(owner.slug, { type: "decision" });
    await applyCatalog(testDatabase.database, [definition]);
    const host = await createInstanceService(testDatabase.database).register({
      provider: "runpod",
      providerAccountId: "test",
      providerInstanceId: randomUUID(),
      region: "US-NE-1",
      sku: "RTX PRO 6000",
      faultDomain: "test-host",
    });
    const pod = (protocol?: "system_one") => ({
      id: randomUUID(),
      name: "jeeves",
      instanceId: host.id,
      modelId: definition.id,
      release: { ...deploymentRelease(), ...(protocol ? { protocol } : {}) },
      qualified: true,
      draining: false,
    });
    const decision = pod("system_one");
    const chat = pod();
    const store = createKubernetesDeploymentStore(testDatabase.database);
    const status = async (id: string) =>
      (
        await testDatabase.database
          .select({ status: modelDeployments.status })
          .from(modelDeployments)
          .where(eq(modelDeployments.id, id))
      )[0]?.status;

    const result = await store.reconcile({
      running: async () => [decision, chat],
      isGone: async () => false,
    });

    expect(result?.refused).toEqual([chat.id]);
    expect(await status(decision.id)).toBe("available");
    expect(await status(chat.id)).toBeUndefined();

    // A model ID's type is fixed: changing it retires the ID, as a cached
    // record would keep serving deployments of the old protocol.
    const changed = await applyCatalog(testDatabase.database, [
      { ...definition, type: "chat" },
    ]);
    expect(changed.skipped).toEqual([
      { id: definition.id, reason: "type_changed" },
    ]);
    expect(await stored(definition.id)).toMatchObject({
      type: "decision",
      status: "retired",
    });
  });

  it("lets a private model take a name its organization's retired model had", async () => {
    const owner = await seedOwner();
    const definition = ownedModelDefinition(owner.slug);
    await applyCatalog(testDatabase.database, [definition]);
    const name = definition.id.slice(owner.slug.length + 1);
    await testDatabase.database
      .update(models)
      .set({ status: "retired" })
      .where(eq(models.id, definition.id));

    expect(
      await modelNameProblem(testDatabase.database, owner.workspaceId, name),
    ).toBeUndefined();
    expect(await claimTask(owner, name)).toBe(owner.organizationId);
  });

  it("refuses an owned ID or alias with more than one segment after the slug", async () => {
    const owner = await seedOwner();
    const nested = ownedModelDefinition(owner.slug);

    await expect(
      testDatabase.database.insert(models).values({
        id: `${owner.slug}/support/v1`,
        name: "Nested",
        status: "available",
        properties: (await catalog(modelInput())).properties,
        organizationId: owner.organizationId,
        type: "chat",
      }),
    ).rejects.toThrow();
    await applyCatalog(testDatabase.database, [nested]);
    await expect(
      testDatabase.database
        .update(models)
        .set({ aliases: [`${owner.slug}/ok`, `${owner.slug}/support/v1`] })
        .where(eq(models.id, nested.id)),
    ).rejects.toThrow();
    await testDatabase.database
      .update(models)
      .set({ aliases: [`${owner.slug}/ok`] })
      .where(eq(models.id, nested.id));
  });

  it("skips a definition whose owner this environment lacks, never writing it public", async () => {
    const definition = ownedModelDefinition(
      `missing-${randomUUID().slice(0, 8)}`,
    );
    const publicModel = modelInput();

    const result = await applyCatalog(testDatabase.database, [
      definition,
      publicModel,
    ]);

    expect(result).toMatchObject({
      applied: 1,
      skipped: [{ id: definition.id, reason: "owner_missing" }],
    });
    expect(await stored(definition.id)).toBeUndefined();
    expect(await stored(publicModel.id)).toBeDefined();
  });

  it.each([
    [
      "an ID outside the owner's slug",
      (slug: string) => ({ id: `other/${slug}` }),
    ],
    ["a bare slug ID", (slug: string) => ({ id: `${slug}/` })],
    [
      "an alias outside the owner's slug",
      (slug: string) => ({ aliases: [`public-${slug}`] }),
    ],
  ])("rejects %s before writing", async (_, override) => {
    const owner = await seedOwner();
    const definition = ownedModelDefinition(owner.slug, override(owner.slug));
    const publicModel = modelInput();

    await expect(
      applyCatalog(testDatabase.database, [publicModel, definition]),
    ).rejects.toThrow("must be named");
    expect(await stored(publicModel.id)).toBeUndefined();
  });

  it("never changes a model's owner in place, retiring the ID instead", async () => {
    const owner = await seedOwner();
    const other = await seedOwner();
    const definition = ownedModelDefinition(owner.slug);
    const { owner: _owner, ...unowned } = definition;
    const catalog = createCatalogService(testDatabase.database);
    await catalog.upsertModel(unowned);

    const result = await applyCatalog(testDatabase.database, [definition]);

    expect(result.skipped).toEqual([
      { id: definition.id, reason: "owner_changed" },
    ]);
    expect(await stored(definition.id)).toMatchObject({
      organizationId: null,
      status: "retired",
    });

    // Owned to public, or to another owner, is refused the same way.
    const owned = ownedModelDefinition(owner.slug);
    await applyCatalog(testDatabase.database, [owned]);
    const { owner: _again, ...published } = owned;
    expect(
      (await applyCatalog(testDatabase.database, [published])).skipped,
    ).toEqual([{ id: owned.id, reason: "owner_changed" }]);
    await expect(
      catalog.upsertModel({
        ...published,
        organizationId: other.organizationId,
      }),
    ).rejects.toThrow("returned no row");
    expect(await stored(owned.id)).toMatchObject({
      organizationId: owner.organizationId,
      status: "retired",
    });
  });

  it("refuses to write a definition with an owner directly", async () => {
    const owner = await seedOwner();

    await expect(
      createCatalogService(testDatabase.database).upsertModel(
        ownedModelDefinition(owner.slug),
      ),
    ).rejects.toThrow("applyCatalog");
  });

  it("keeps public IDs and aliases out of every organization's namespace", async () => {
    const owner = await seedOwner();
    const listed = modelInput();
    await applyCatalog(testDatabase.database, [listed]);

    for (const intruder of [
      { ...listed, aliases: [`${owner.slug}/borrowed`] },
      modelInput({ id: `${owner.slug}/public` }),
    ]) {
      const result = await applyCatalog(testDatabase.database, [intruder]);

      expect(result.skipped).toEqual([
        { id: intruder.id, reason: "namespace_conflict" },
      ]);
    }
    // The public row that tried to take the name keeps its old names.
    expect(await stored(listed.id)).toMatchObject({
      status: "available",
      aliases: [],
    });
    expect(await stored(`${owner.slug}/public`)).toBeUndefined();
  });

  it("never hands a name a public row answers to over to an owned model", async () => {
    const owner = await seedOwner();
    const name = `${owner.slug}/grandfathered`;
    await catalog(modelInput({ aliases: [name] }));
    const definition = ownedModelDefinition(owner.slug, { aliases: [name] });

    const result = await applyCatalog(testDatabase.database, [definition]);

    expect(result.skipped).toEqual([
      { id: definition.id, reason: "namespace_conflict" },
    ]);
    expect(await stored(definition.id)).toBeUndefined();
  });

  it("makes catalog apply wait for a slug being chosen", async () => {
    const owner = await seedOwner();
    const author = `author-${randomUUID().slice(0, 8)}`;
    let release!: () => void;
    const released = new Promise<void>((resolve) => (release = resolve));
    let chosen!: () => void;
    const checked = new Promise<void>((resolve) => (chosen = resolve));

    // The slug check holds the namespace lock until its transaction commits.
    const choosing = testDatabase.database.transaction(async (transaction) => {
      await requireChangeableSlug(transaction, owner.organizationId, author);
      await transaction
        .update(organizations)
        .set({ slug: author })
        .where(eq(organizations.id, owner.organizationId));
      chosen();
      await released;
    });
    await checked;
    let applied = false;
    const applying = applyCatalog(testDatabase.database, [
      modelInput({ id: `${author}/public` }),
    ]).then((result) => {
      applied = true;
      return result;
    });
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(applied).toBe(false);

    release();
    await choosing;
    // Applied after the slug committed, the public ID can't take its namespace.
    expect((await applying).skipped).toEqual([
      { id: `${author}/public`, reason: "namespace_conflict" },
    ]);
  });

  it("reserves a slug that a public alias's author already uses", async () => {
    const owner = await seedOwner();
    const author = `author-${randomUUID().slice(0, 8)}`;
    await applyCatalog(testDatabase.database, [
      modelInput({ aliases: [`${author}/alias`] }),
    ]);

    await expect(
      testDatabase.database.transaction((transaction) =>
        requireChangeableSlug(transaction, owner.organizationId, author),
      ),
    ).rejects.toMatchObject({ code: "conflict" });
  });

  it("fixes the owner's slug", async () => {
    const owner = await seedOwner();
    await applyCatalog(testDatabase.database, [
      ownedModelDefinition(owner.slug),
    ]);

    await expect(
      testDatabase.database.transaction((transaction) =>
        requireChangeableSlug(
          transaction,
          owner.organizationId,
          `renamed-${randomUUID().slice(0, 8)}`,
        ),
      ),
    ).rejects.toMatchObject({ code: "conflict" });
  });

  it("refuses a private model name the organization's own model already uses", async () => {
    const owner = await seedOwner();
    const other = await seedOwner();
    const definition = ownedModelDefinition(owner.slug);
    await applyCatalog(testDatabase.database, [definition]);
    const name = definition.id.slice(owner.slug.length + 1);

    expect(
      await modelNameProblem(testDatabase.database, owner.workspaceId, name),
    ).toBe(OWNED_MODEL_NAME);
    expect(
      await modelNameProblem(
        testDatabase.database,
        owner.workspaceId,
        name.toUpperCase(),
      ),
    ).toBe(OWNED_MODEL_NAME);
    expect(
      await modelNameProblem(testDatabase.database, other.workspaceId, name),
    ).toBeUndefined();
  });

  it("never offers an organization's model as a base model", async () => {
    const owner = await seedOwner();
    const definition = ownedModelDefinition(owner.slug);
    await applyCatalog(testDatabase.database, [definition]);

    expect(
      await createTrainingStore(testDatabase.database).getModel(definition.id),
    ).toBeUndefined();
  });

  it.each([
    ["ID", (slug: string, name: string) => ({ id: `${slug}/${name}` })],
    [
      "alias",
      (slug: string, name: string) => ({ aliases: [`${slug}/${name}`] }),
    ],
  ])(
    "skips a definition whose %s an existing private model answers to",
    async (_, names) => {
      const owner = await seedOwner();
      const name = `Triage-${randomUUID().slice(0, 8)}`;
      expect(await claimTask(owner, name)).toBe(owner.organizationId);
      const definition = ownedModelDefinition(
        owner.slug,
        names(owner.slug, name.toLowerCase()),
      );

      const result = await applyCatalog(testDatabase.database, [definition]);

      expect(result.skipped).toEqual([
        { id: definition.id, reason: "private_model_conflict" },
      ]);
      expect(await stored(definition.id)).toBeUndefined();
    },
  );

  it("retires a public row whose definition gains an owner this environment lacks", async () => {
    const slug = `missing-${randomUUID().slice(0, 8)}`;
    const definition = ownedModelDefinition(slug);
    const { owner: _owner, ...unowned } = definition;
    await applyCatalog(testDatabase.database, [unowned]);
    expect(await stored(definition.id)).toMatchObject({ status: "available" });

    const result = await applyCatalog(testDatabase.database, [definition]);

    expect(result.skipped).toEqual([
      { id: definition.id, reason: "owner_missing" },
    ]);
    expect(await stored(definition.id)).toMatchObject({
      status: "retired",
      organizationId: null,
    });
    expect(
      (await createCatalogService(testDatabase.database).listModels()).map(
        (model) => model.id,
      ),
    ).not.toContain(definition.id);

    // Even once the owner exists, the public ID stays retired.
    const owner = await seedMember(testDatabase.database, { role: "member" });
    await testDatabase.database
      .update(organizations)
      .set({ slug })
      .where(eq(organizations.id, owner.organizationId));
    expect(
      (await applyCatalog(testDatabase.database, [definition])).skipped,
    ).toEqual([{ id: definition.id, reason: "owner_changed" }]);
    expect(await stored(definition.id)).toMatchObject({
      status: "retired",
      organizationId: null,
    });
  });

  it("leaves a private name an owned model or alias answers to unclaimed", async () => {
    const owner = await seedOwner();
    const definition = ownedModelDefinition(owner.slug, {
      aliases: [`${owner.slug}/aliased`],
    });
    await applyCatalog(testDatabase.database, [definition]);
    const name = definition.id.slice(owner.slug.length + 1);

    expect(await claimTask(owner, name.toUpperCase())).toBeNull();
    expect(await claimTask(owner, "Aliased")).toBeNull();
    expect(
      await modelNameProblem(
        testDatabase.database,
        owner.workspaceId,
        "aliased",
      ),
    ).toBe(OWNED_MODEL_NAME);
    expect(await claimTask(owner, `other-${randomUUID().slice(0, 8)}`)).toBe(
      owner.organizationId,
    );
  });
});
