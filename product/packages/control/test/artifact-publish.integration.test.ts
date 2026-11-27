import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { eq } from "drizzle-orm";
import {
  taskProductionChanges,
  tasks,
  taskVersionPinReleases,
  taskVersions,
} from "../src/db/schema/index.js";
import {
  createArtifactPublisher,
  servingBase,
  type ServingBases,
} from "../src/training/publish.js";
import { createEvalVersions } from "../src/training/evals.js";
import { createTrainingService } from "../src/training/service.js";
import { createMemoryContentStore } from "./support/content-store.js";
import { createTrainingStore } from "../src/training/store.js";
import type { GradArtifact, GradArtifacts } from "../src/training/grad.js";
import type { AdapterQualifier } from "../src/training/qualification.js";
import type { BaseModelConfiguration } from "../src/training/base-model-configuration.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";
import { seedTrainingTask } from "./support/training.js";
import { adapterFiles } from "./support/adapter-upload.js";
import { cartridgeFile } from "./support/cartridge.js";
import { gradBundle, QWEN_REPO, QWEN_REVISION } from "./support/grad-bundle.js";

const loraFiles = (rank = 2) => {
  const { config, weights } = adapterFiles(QWEN_REPO, 1, undefined, rank);
  return {
    "adapter_config.json": Buffer.from(
      JSON.stringify({
        ...JSON.parse(config.toString()),
        revision: QWEN_REVISION,
      }),
    ),
    "adapter_model.safetensors": weights,
  };
};

describe("publishing grad artifacts", () => {
  let db: TestDatabase;
  beforeAll(async () => {
    db = await createTestDatabase();
  });
  afterAll(() => db.dispose());

  const setup = async ({
    qualify = vi.fn<AdapterQualifier>(async () => undefined),
    servingBases = {},
  }: { qualify?: AdapterQualifier; servingBases?: ServingBases } = {}) => {
    const member = await seedTrainingTask(db.database, "Qwen/Qwen3-0.6B");
    const objects = new Map<string, Buffer>();
    const artifacts = new Map<string, GradArtifact>();
    const pins = new Set<string>();
    const grad = {
      resolve: vi.fn(async (workspaceId: string, reference: string) => {
        const found = [...artifacts.values()].find(
          (artifact) =>
            artifact.workspace_id === workspaceId &&
            (artifact.id === reference ||
              `${artifact.name}@${artifact.version}` === reference),
        );
        return found ?? null;
      }),
      pin: vi.fn(async (_workspaceId: string, id: string, holder: string) => {
        pins.add(`${id}/${holder}`);
      }),
      unpin: vi.fn(async (_workspaceId: string, id: string, holder: string) => {
        pins.delete(`${id}/${holder}`);
      }),
    } satisfies GradArtifacts;
    const bundles = {
      async *stream(key: string, options: { maxBytes: number }) {
        const bytes = objects.get(key);
        if (!bytes || bytes.length > options.maxBytes)
          throw new Error("Read failed");
        yield bytes;
      },
      uri: (key: string) => `s3://grad-test/${key}`,
    };
    const loadBaseConfiguration = vi.fn(
      async (): Promise<BaseModelConfiguration> => ({
        layerCount: 1,
        expertCount: 0,
        projectionShapes: { "0/self_attn.q_proj": [4, 4] as const },
        hiddenSize: 8,
        vocabSize: 1000,
      }),
    );
    const publisher = createArtifactPublisher({
      database: db.database,
      grad,
      bundles,
      qualifyAdapter: qualify,
      loadBaseConfiguration,
      servingBases,
    });
    const add = (
      files: Record<string, Buffer>,
      overrides: Partial<GradArtifact> = {},
      bundleOptions: Parameters<typeof gradBundle>[1] = {},
    ) => {
      const bundle = gradBundle(files, bundleOptions);
      const name = overrides.name ?? "fast-diff-merge";
      const version = overrides.version ?? `2026-11-26-${artifacts.size + 1}`;
      const artifact: GradArtifact = {
        id: `${name}@${version}`,
        workspace_id: member.workspaceId,
        name,
        version,
        source: "run",
        format: bundleOptions.format ?? "peft_lora",
        recipe_kind: "sft",
        base_model: "qwen/qwen3-0.6b",
        key: `artifacts/${member.workspaceId}/${bundle.sha256}`,
        sha256: bundle.sha256,
        size_bytes: bundle.sizeBytes,
        ...overrides,
      };
      artifacts.set(artifact.id, artifact);
      objects.set(artifact.key, bundle.bytes);
      return artifact;
    };
    return { member, publisher, grad, pins, add, qualify };
  };

  it("creates the model and an available version that reads the bundle in place", async () => {
    const { member, publisher, pins, add, qualify } = await setup();
    const artifact = add(loraFiles());

    const result = await publisher.publish(member.userId, member.workspaceId, {
      artifact: "fast-diff-merge@2026-11-26-1",
    });

    expect(result).toMatchObject({
      created: true,
      qualification: { outcome: "passed" },
      task: { name: "fast-diff-merge", baseModelId: "Qwen/Qwen3-0.6B" },
      version: { name: "2026-11-26-1", status: "available" },
    });
    expect(result.version.adapter).toEqual({
      format: "peft_lora",
      artifact_uri: `s3://grad-test/artifacts/${member.workspaceId}/${artifact.sha256}`,
      sha256: artifact.sha256,
      size_bytes: artifact.size_bytes,
      rank: 2,
      base_model_revision: QWEN_REVISION,
      validated_base_model_revision: QWEN_REVISION,
      source: {
        kind: "grad",
        artifact_id: artifact.id,
        artifact_source: "run",
        bundle: "grad.artifact/1",
      },
    });
    expect([...pins]).toEqual([
      `${artifact.id}/inference:version:${result.version.id}`,
    ]);
    expect(qualify).toHaveBeenCalledTimes(1);

    const again = await publisher.publish(member.userId, member.workspaceId, {
      artifact: artifact.id,
    });
    expect(again).toMatchObject({
      created: false,
      version: { id: result.version.id },
    });
    expect(pins.size).toBe(1);
  });

  it("reads a release made before grad stored bundles under artifacts/ at its job key", async () => {
    const { member, publisher, add } = await setup();
    const key = `ws/${member.workspaceId}/jobs/job_1/1/${"c".repeat(64)}`;
    const artifact = add(loraFiles(), { key });

    const { version } = await publisher.publish(
      member.userId,
      member.workspaceId,
      { artifact: artifact.id },
    );

    expect(version.adapter.artifact_uri).toBe(`s3://grad-test/${key}`);
  });

  it("maps grad's base model IDs to serving bases by catalog, or by configuration", async () => {
    const manifest = (base_model: string, repo: string, revision: string) =>
      ({
        base_model,
        base_model_repo: repo,
        base_model_revision: revision,
      }) as Parameters<typeof servingBase>[0];

    expect(
      servingBase(
        manifest(
          "qwen/qwen3-8b",
          "Qwen/Qwen3-8B",
          "b968826d9c46dd6066d109eabc6255188de91218",
        ),
      ),
    ).toEqual({
      modelId: "Qwen/Qwen3-8B",
      repository: "Qwen/Qwen3-8B",
      revision: "b968826d9c46dd6066d109eabc6255188de91218",
    });

    const pinned = "e".repeat(40);
    const { member, publisher, add } = await setup({
      servingBases: {
        "qwen/qwen3-0.6b": {
          model_id: "Qwen/Qwen3-0.6B",
          repository: QWEN_REPO,
          revision: pinned,
        },
      },
    });
    const files = {
      "adapter_config.json": Buffer.from(
        JSON.stringify({
          ...JSON.parse(loraFiles()["adapter_config.json"].toString()),
          revision: pinned,
        }),
      ),
      "adapter_model.safetensors": loraFiles()["adapter_model.safetensors"],
    };
    const artifact = add(
      files,
      {},
      { manifest: { base_model_revision: pinned } },
    );

    const { version } = await publisher.publish(
      member.userId,
      member.workspaceId,
      { artifact: artifact.id },
    );
    expect(version.adapter).toMatchObject({
      validated_base_model_revision: pinned,
    });
  });

  it("publishes into a named model and keeps an unqualified version unavailable", async () => {
    const qualify = vi.fn<AdapterQualifier>(async () => {
      const { ControlServiceError } = await import("../src/errors.js");
      throw new ControlServiceError("unavailable", "No serving capacity.");
    });
    const { member, publisher, add } = await setup({ qualify });
    add(loraFiles());

    const result = await publisher.publish(member.userId, member.workspaceId, {
      artifact: "fast-diff-merge@2026-11-26-1",
      task: member.task.name,
      name: "first",
    });

    expect(result).toMatchObject({
      task: { id: member.task.id },
      version: { name: "first", status: "unavailable" },
      qualification: { outcome: "pending", detail: "No serving capacity." },
    });
  });

  it("accepts grad's default rank 32 and refuses rank 64", async () => {
    const { member, publisher, add } = await setup();
    add(loraFiles(32));
    const rank64 = add(loraFiles(64));

    const { version } = await publisher.publish(
      member.userId,
      member.workspaceId,
      { artifact: "fast-diff-merge@2026-11-26-1" },
    );
    expect(version.adapter).toMatchObject({ rank: 32 });
    await expect(
      publisher.publish(member.userId, member.workspaceId, {
        artifact: rank64.id,
      }),
    ).rejects.toMatchObject({ code: "invalid_artifact" });
  });

  it("publishes a cartridge bundle", async () => {
    const { member, publisher, add } = await setup();
    const file = cartridgeFile();
    add({ "cartridge.safetensors": file }, {}, { format: "cartridge" });

    const { version } = await publisher.publish(
      member.userId,
      member.workspaceId,
      {
        artifact: "fast-diff-merge@2026-11-26-1",
      },
    );

    expect(version.adapter).toMatchObject({
      format: "cartridge",
      num_tokens: 4,
      hidden_size: 8,
      has_slot_token_ids: true,
      source: { kind: "grad" },
    });
  });

  it.each([
    [
      { format: "router_bundle" },
      "format_not_servable_yet",
      "peft_lora, cartridge",
    ],
    [
      { format: "merged_safetensors" },
      "format_not_servable",
      "Supported formats",
    ],
    [{ sha256: "0".repeat(64) }, "invalid_artifact", "SHA-256"],
  ] as const)(
    "refuses %o with %s and pins nothing",
    async (overrides, code, message) => {
      const { member, publisher, pins, add } = await setup();
      const artifact = add(loraFiles(), overrides);

      await expect(
        publisher.publish(member.userId, member.workspaceId, {
          artifact: artifact.id,
        }),
      ).rejects.toMatchObject({
        code,
        message: expect.stringContaining(message),
      });
      expect(pins.size).toBe(0);
    },
  );

  it.each([
    [{ format_version: 3 }, "invalid_artifact", "format version"],
    [
      { base_model_revision: "f".repeat(40) },
      "base_revision_mismatch",
      "pins revision",
    ],
    [
      { base_model_repo: "BAAI/bge-small-en-v1.5" },
      "base_model_not_servable",
      "No Gradiated",
    ],
  ])(
    "refuses a bundle whose manifest has %o with %s",
    async (manifest, code, message) => {
      const { member, publisher, pins, add } = await setup();
      const artifact = add(loraFiles(), {}, { manifest });

      await expect(
        publisher.publish(member.userId, member.workspaceId, {
          artifact: artifact.id,
        }),
      ).rejects.toMatchObject({
        code,
        message: expect.stringContaining(message),
      });
      expect(pins.size).toBe(0);
    },
  );

  it("refuses a model of another base and a taken version name, releasing the pin", async () => {
    const { member, publisher, pins, add } = await setup();
    add(loraFiles());
    add(loraFiles(), { name: "other-merge", version: "2026-11-26-1" });
    await publisher.publish(member.userId, member.workspaceId, {
      artifact: "fast-diff-merge@2026-11-26-1",
    });

    await expect(
      publisher.publish(member.userId, member.workspaceId, {
        artifact: "other-merge@2026-11-26-1",
        task: "fast-diff-merge",
      }),
    ).rejects.toMatchObject({ code: "version_name_taken" });
    expect(pins.size).toBe(1);

    await db.database
      .update(tasks)
      .set({ baseModelId: null })
      .where(eq(tasks.id, member.task.id));
    await expect(
      publisher.publish(member.userId, member.workspaceId, {
        artifact: "other-merge@2026-11-26-1",
        task: member.task.name,
      }),
    ).rejects.toMatchObject({ code: "model_base_mismatch" });
  });

  it("deletes a version, unpins its artifact and refuses the production version", async () => {
    const { member, publisher, grad, pins, add } = await setup();
    add(loraFiles());
    const { task, version } = await publisher.publish(
      member.userId,
      member.workspaceId,
      { artifact: "fast-diff-merge@2026-11-26-1" },
    );
    await createTrainingStore(db.database).setProductionVersion(
      task.id,
      version.id,
      `user:${member.userId}`,
    );

    await expect(
      publisher.deleteVersion(
        member.userId,
        member.workspaceId,
        task.name,
        version.name,
      ),
    ).rejects.toMatchObject({ code: "version_in_production" });

    await db.database
      .update(tasks)
      .set({ productionVersionId: null })
      .where(eq(tasks.id, task.id));
    grad.unpin.mockRejectedValueOnce(new Error("grad is down"));
    await publisher.deleteVersion(
      member.userId,
      member.workspaceId,
      task.name,
      version.id,
    );

    expect(
      await db.database
        .select()
        .from(taskVersions)
        .where(eq(taskVersions.id, version.id)),
    ).toEqual([]);
    expect(pins.size).toBe(1);
    expect(
      await db.database
        .select()
        .from(taskVersionPinReleases)
        .where(eq(taskVersionPinReleases.versionId, version.id)),
    ).toHaveLength(1);

    expect(
      await publisher.releasePendingPins(new Date(Date.now() + 120_000)),
    ).toMatchObject({ released: 1 });
    expect(pins.size).toBe(0);
  });

  it("records every move of the production pointer", async () => {
    const { member, publisher, add } = await setup();
    add(loraFiles());
    add(loraFiles());
    const first = await publisher.publish(member.userId, member.workspaceId, {
      artifact: "fast-diff-merge@2026-11-26-1",
    });
    const second = await publisher.publish(member.userId, member.workspaceId, {
      artifact: "fast-diff-merge@2026-11-26-2",
    });
    const store = createTrainingStore(db.database);
    const actor = `user:${member.userId}`;
    await store.setProductionVersion(first.task.id, first.version.id, actor);
    await store.setProductionVersion(first.task.id, second.version.id, actor);
    await store.setProductionVersion(first.task.id, second.version.id, actor);
    await store.setProductionVersion(first.task.id, first.version.id, actor);

    const changes = await store.listProductionChanges(first.task.id);
    expect(
      changes.map((change) => [change.fromVersionId, change.toVersionId]),
    ).toEqual([
      [second.version.id, first.version.id],
      [first.version.id, second.version.id],
      [null, first.version.id],
    ]);
    expect(
      await db.database
        .select()
        .from(taskProductionChanges)
        .where(eq(taskProductionChanges.taskId, first.task.id)),
    ).toHaveLength(3);
  });

  describe("eval-only versions", () => {
    it("publishes eval-only versions into a hidden model that never serves production", async () => {
      const { member, publisher, pins, add } = await setup();
      const evals = createEvalVersions(db.database, publisher);
      const artifact = add(loraFiles());

      const published = await evals.publish(
        member.workspaceId,
        "fast-diff-merge@2026-11-26-1",
      );

      expect(published.model).toMatch(
        new RegExp(
          `^[a-z0-9-]+/grad-eval-${member.workspaceId}/fast-diff-merge\\.2026-11-26-1$`,
        ),
      );
      expect(published.task).toMatchObject({ purpose: "eval" });
      expect(published).toMatchObject({
        version: { status: "available" },
        qualification: { outcome: "skipped" },
      });
      expect(published.version.expiresAt!.getTime()).toBeGreaterThan(
        Date.now() + 6 * 24 * 3600_000,
      );
      const again = await evals.publish(member.workspaceId, artifact.id);
      expect(again.version.id).toBe(published.version.id);
      expect(pins.size).toBe(1);

      const training = createTrainingService(
        db.database,
        createMemoryContentStore(new Map()),
      );
      expect(
        (await training.listTasks(member.userId, member.workspaceId)).map(
          (task) => task.name,
        ),
      ).toEqual([member.task.name]);
      await expect(
        training.promote(
          member.userId,
          member.workspaceId,
          published.task.name,
          published.version.id,
        ),
      ).rejects.toMatchObject({ code: "not_found" });
      await expect(
        publisher.publish(member.userId, member.workspaceId, {
          artifact: artifact.id,
          task: published.task.name,
        }),
      ).rejects.toMatchObject({ code: "invalid_artifact" });

      expect(await publisher.deleteExpiredVersions(new Date())).toEqual({
        deleted: 0,
      });
      expect(
        await publisher.deleteExpiredVersions(
          new Date(Date.now() + 8 * 24 * 3600_000),
        ),
      ).toEqual({ deleted: 1 });
      expect(pins.size).toBe(0);
    });
  });
});
