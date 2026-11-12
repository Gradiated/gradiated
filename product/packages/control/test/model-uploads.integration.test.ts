import { randomUUID } from "node:crypto";
import { readFile, writeFile, stat } from "node:fs/promises";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { eq } from "drizzle-orm";
import { createModelUploads } from "../src/training/uploads.js";
import { createTrainingStore } from "../src/training/store.js";
import { createTrainingArtifactCleanup } from "../src/training/artifact-cleanup.js";
import {
  modelUploads,
  models,
  tasks,
  taskVersions,
  workspaces,
} from "../src/db/schema/index.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";
import { seedTrainingTask } from "./support/training.js";
import { seedMember, seedWorkspace } from "./support/fixtures.js";
import { adapterFiles } from "./support/adapter-upload.js";
import type { BaseModelConfiguration } from "../src/training/base-model-configuration.js";
import { createMemoryContentStore } from "./support/content-store.js";

describe("model uploads", () => {
  let db: TestDatabase;
  beforeAll(async () => {
    db = await createTestDatabase();
  });
  afterAll(() => db.dispose());

  const setup = async () => {
    const member = await seedTrainingTask(db.database, "Qwen/Qwen3-0.6B");
    const objects = new Map<string, Buffer>();
    const storage = {
      signUpload: vi.fn(
        async (key: string) => `https://storage.invalid/${key}`,
      ),
      read: async (key: string, options: { maxBytes: number }) => {
        const bytes = objects.get(key);
        if (!bytes || bytes.length > options.maxBytes)
          throw new Error("Read failed");
        return bytes;
      },
      downloadFile: vi.fn(
        async (
          key: string,
          destination: string,
          options: { maxBytes: number },
        ) => {
          const bytes = objects.get(key);
          if (!bytes || bytes.length > options.maxBytes)
            throw new Error("Read failed");

          await writeFile(destination, bytes, { flag: "wx" });
          return bytes.length;
        },
      ),
      putFile: vi.fn(async (key: string, path: string) => {
        objects.set(key, await readFile(path));
      }),
      delete: vi.fn(async (keys: string[]) => {
        for (const key of keys) objects.delete(key);
      }),
      uri: (key: string) => `s3://test/${key}`,
    };
    const loadBaseConfiguration = vi.fn(
      async (): Promise<BaseModelConfiguration> => ({
        layerCount: 1,
        expertCount: 0,
        projectionShapes: { "0/self_attn.q_proj": [4, 4] as const },
      }),
    );
    const service = createModelUploads(
      db.database,
      storage,
      loadBaseConfiguration,
    );
    const files = adapterFiles(member.input.baseModelId);
    const body = {
      task: member.task.name,
      create_task: false,
      name: "triage-v1",
      base_model_id: member.input.baseModelId,
      base_model_revision: "a".repeat(40),
      config_size: files.config.length,
      weights_size: files.weights.length,
    };
    const stage = async (input = body) => {
      const upload = await service.create(
        member.userId,
        member.workspaceId,
        input,
      );
      objects.set(`uploads/${upload.id}/adapter_config.json`, files.config);
      objects.set(
        `uploads/${upload.id}/adapter_model.safetensors`,
        files.weights,
      );
      return upload;
    };
    return {
      member,
      objects,
      service,
      files,
      body,
      stage,
      storage,
      loadBaseConfiguration,
    };
  };
  it("rejects a different base model when appending to a task", async () => {
    const { member, body, service, storage } = await setup();
    await db.database
      .update(tasks)
      .set({ baseModelId: null })
      .where(eq(tasks.id, member.task.id));
    await expect(
      service.create(member.userId, member.workspaceId, body),
    ).rejects.toThrow("must match");
    expect(storage.signUpload).not.toHaveBeenCalled();
  });
  it.each(["unavailable", "retired"] as const)(
    "rejects an %s non-training base before issuing grants",
    async (status) => {
      const { member, body, service, storage } = await setup();
      const [original] = await db.database
        .select()
        .from(models)
        .where(eq(models.id, body.base_model_id));
      await db.database
        .insert(models)
        .values({ ...original!, id: `unsupported/${status}`, status })
        .onConflictDoUpdate({ target: models.id, set: { status } });
      await expect(
        service.create(member.userId, member.workspaceId, {
          ...body,
          create_task: true,
          task: "new-task",
          base_model_id: `unsupported/${status}`,
        }),
      ).rejects.toThrow("unavailable");
      expect(storage.signUpload).not.toHaveBeenCalled();
    },
  );
  it("rejects a task base changed after granting the upload", async () => {
    const { member, stage, service } = await setup();
    const upload = await stage();
    await db.database
      .update(tasks)
      .set({ baseModelId: null })
      .where(eq(tasks.id, member.task.id));
    await expect(
      service.complete(member.userId, member.workspaceId, upload.id),
    ).rejects.toThrow("must match");
  });
  it("exposes the immutable base configuration to workspace members", async () => {
    const { member, body, service, loadBaseConfiguration } = await setup();
    expect(
      await service.configuration(
        member.userId,
        member.workspaceId,
        body.base_model_id,
      ),
    ).toMatchObject({
      layerCount: 1,
      projectionShapes: { "0/self_attn.q_proj": [4, 4] },
    });
    expect(loadBaseConfiguration).toHaveBeenCalledWith(
      body.base_model_id,
      "c1899de289a04d12100db370d81485cdf75e47ca",
    );
  });
  it("discovers promoted uploads with only a validated checkpoint revision", async () => {
    const { member, stage, service } = await setup();
    const upload = await stage();
    const { version } = await service.complete(
      member.userId,
      member.workspaceId,
      upload.id,
    );
    expect(version.adapter.base_model_revision).toBeUndefined();
    await db.database
      .update(taskVersions)
      .set({ status: "available" })
      .where(eq(taskVersions.id, version.id));
    await db.database
      .update(tasks)
      .set({ productionVersionId: version.id })
      .where(eq(tasks.id, member.task.id));
    expect(
      (
        await createTrainingStore(db.database).listProductionVersions(
          version.baseModelId,
        )
      ).map((v) => v.id),
    ).toContain(version.id);
  });
  it("publishes a private version without a training run and completes idempotently", async () => {
    const { member, stage, service, objects, storage } = await setup();
    const upload = await stage();
    const result = await service.complete(
      member.userId,
      member.workspaceId,
      upload.id,
    );
    expect(result.version.trainingRunId).toBeNull();
    expect(result.version.status).toBe("unavailable");
    expect(result.version.adapter.rank).toBe(2);
    expect(objects.has(`uploads/${upload.id}/adapter_config.json`)).toBe(false);
    expect(objects.has(`uploads/${upload.id}/adapter_model.safetensors`)).toBe(
      false,
    );
    await expect(
      stat(storage.downloadFile.mock.calls[0]![1]),
    ).rejects.toMatchObject({ code: "ENOENT" });
    await expect(stat(storage.putFile.mock.calls[0]![1])).rejects.toMatchObject(
      { code: "ENOENT" },
    );
    expect(result.version.adapter.artifact_uri).toContain(
      `/output/${result.version.adapter.sha256}/`,
    );
    expect(
      storage.signUpload.mock.calls.every(([key]) =>
        key.startsWith("uploads/"),
      ),
    ).toBe(true);
    objects.set(
      `uploads/${upload.id}/adapter_model.safetensors`,
      Buffer.from("replaced"),
    );
    expect(
      (await service.complete(member.userId, member.workspaceId, upload.id))
        .version.id,
    ).toBe(result.version.id);
    const tasks = await createTrainingStore(db.database).listTasks(
      member.workspaceId,
    );
    expect(tasks[0]?.latestVersion?.id).toBe(result.version.id);
    expect(tasks[0]?.latestRun).toBeNull();
  });
  it.each([
    "c1899de289a04d12100db370d81485cdf75e47ca",
    "b".repeat(40),
    "main",
    null,
  ])(
    "preserves declared revision %s without trusting the submitted hint",
    async (revision) => {
      const { member, stage, service, body, files, objects } = await setup();
      const config = Buffer.from(
        JSON.stringify({ ...JSON.parse(files.config.toString()), revision }),
      );
      const upload = await stage({ ...body, config_size: config.length });
      objects.set(`uploads/${upload.id}/adapter_config.json`, config);
      const { version } = await service.complete(
        member.userId,
        member.workspaceId,
        upload.id,
      );
      expect(version.adapter.validated_base_model_revision).toBe(
        "c1899de289a04d12100db370d81485cdf75e47ca",
      );
      expect(version.adapter.base_model_revision).toBe(
        typeof revision === "string" && /^[0-9a-f]{40}$/.test(revision)
          ? revision
          : undefined,
      );
      expect(version.adapter.declared_base_model_revision).toBe(
        revision ?? undefined,
      );
      expect(version.status).toBe("unavailable");
    },
  );
  it("rejects matching revision metadata with incompatible serving tensor dimensions", async () => {
    const { member, stage, service, loadBaseConfiguration } = await setup();
    const upload = await stage();
    loadBaseConfiguration.mockResolvedValueOnce({
      layerCount: 1,
      expertCount: 0,
      projectionShapes: { "0/self_attn.q_proj": [8, 8] },
    });
    await expect(
      service.complete(member.userId, member.workspaceId, upload.id),
    ).rejects.toMatchObject({ code: "conflict" });
    expect(
      await createTrainingStore(db.database).listVersions(member.task.id),
    ).toEqual([]);
  });
  it("rejects publication when serving shape validation is unavailable", async () => {
    const { member, stage, service, loadBaseConfiguration } = await setup();
    const upload = await stage();
    loadBaseConfiguration.mockResolvedValueOnce({
      layerCount: 1,
      expertCount: 0,
    } as never);
    await expect(
      service.complete(member.userId, member.workspaceId, upload.id),
    ).rejects.toMatchObject({ code: "unavailable" });
  });
  it("checks coverage against the immutable base revision before publishing", async () => {
    const {
      member,
      stage,
      service,
      storage,
      body,
      loadBaseConfiguration,
      files,
      objects,
    } = await setup();
    const spoofedConfig = Buffer.from(
      JSON.stringify({
        ...JSON.parse(files.config.toString()),
        num_hidden_layers: 1,
      }),
    );
    const upload = await stage({ ...body, config_size: spoofedConfig.length });
    objects.set(`uploads/${upload.id}/adapter_config.json`, spoofedConfig);
    loadBaseConfiguration.mockResolvedValueOnce({
      layerCount: 2,
      expertCount: 0,
      projectionShapes: { "0/self_attn.q_proj": [8, 8] as const },
    });
    await expect(
      service.complete(member.userId, member.workspaceId, upload.id),
    ).rejects.toMatchObject({ code: "conflict" });
    expect(loadBaseConfiguration).toHaveBeenCalledWith(
      body.base_model_id,
      "c1899de289a04d12100db370d81485cdf75e47ca",
    );
    expect(storage.putFile).not.toHaveBeenCalled();
    expect(
      await createTrainingStore(db.database).listVersions(member.task.id),
    ).toEqual([]);
  });
  it("keeps publication successful when staging deletion fails and retries it on completion", async () => {
    const { member, stage, service, storage, objects } = await setup();
    const upload = await stage();
    storage.delete.mockRejectedValueOnce(
      new Error("Temporary storage failure"),
    );
    const first = await service.complete(
      member.userId,
      member.workspaceId,
      upload.id,
    );
    expect(objects.has(`uploads/${upload.id}/adapter_model.safetensors`)).toBe(
      true,
    );
    const retried = await service.complete(
      member.userId,
      member.workspaceId,
      upload.id,
    );
    expect(retried.version.id).toBe(first.version.id);
    expect(objects.has(`uploads/${upload.id}/adapter_model.safetensors`)).toBe(
      false,
    );
    expect(storage.putFile).toHaveBeenCalledOnce();
  });
  it("waits for downloads to settle before cleaning files after a failure", async () => {
    const { member, stage, service, storage } = await setup();
    const upload = await stage();
    vi.spyOn(storage, "read").mockRejectedValueOnce(
      new Error("Config unavailable"),
    );
    const download = storage.downloadFile.getMockImplementation()!;
    storage.downloadFile.mockImplementationOnce(async (...args) => {
      await new Promise((resolve) => setTimeout(resolve, 20));
      return download(...args);
    });
    await expect(
      service.complete(member.userId, member.workspaceId, upload.id),
    ).rejects.toMatchObject({ code: "conflict" });
    await expect(
      storage.downloadFile.mock.results[0]!.value,
    ).resolves.toBeGreaterThan(0);
    await expect(
      stat(storage.downloadFile.mock.calls[0]![1]),
    ).rejects.toMatchObject({ code: "ENOENT" });
    expect(storage.putFile).not.toHaveBeenCalled();
    expect(
      (await service.complete(member.userId, member.workspaceId, upload.id))
        .version.id,
    ).toBe(upload.id);
  });
  it("creates a task atomically and disables automatic training", async () => {
    const { member, stage, service, body } = await setup();
    await db.database
      .update(workspaces)
      .set({ defaultJudgeModel: "Qwen/Qwen3-0.6B" })
      .where(eq(workspaces.id, member.workspaceId));
    const upload = await stage({
      ...body,
      create_task: true,
      task: "new-task",
    });
    expect(
      await createTrainingStore(db.database).getTask(
        member.workspaceId,
        "new-task",
      ),
    ).toBeUndefined();
    const result = await service.complete(
      member.userId,
      member.workspaceId,
      upload.id,
    );
    expect(result.task.name).toBe("new-task");
    expect(result.task.trainingSchedule).toBeNull();
    expect(result.task.judgeModelId).toBe("Qwen/Qwen3-0.6B");
  });
  it("rejects cross-workspace completion, non-admin uploads, invalid weights and expired sessions", async () => {
    const { member, stage, service, body, objects } = await setup();
    const upload = await stage();
    const outsider = await seedMember(db.database, { role: "admin" });
    await expect(
      service.complete(outsider.userId, outsider.workspaceId, upload.id),
    ).rejects.toMatchObject({ code: "not_found" });
    const viewer = await seedMember(db.database, { role: "member" });
    await expect(
      service.create(viewer.userId, viewer.workspaceId, body),
    ).rejects.toMatchObject({ code: "forbidden" });
    objects.set(
      `uploads/${upload.id}/adapter_model.safetensors`,
      Buffer.alloc(body.weights_size),
    );
    await expect(
      service.complete(member.userId, member.workspaceId, upload.id),
    ).rejects.toMatchObject({ code: "conflict" });
    await db.database
      .update(modelUploads)
      .set({ createdAt: new Date(Date.now() - 7200_000) })
      .where(eq(modelUploads.id, upload.id));
    await expect(
      service.complete(member.userId, member.workspaceId, upload.id),
    ).rejects.toThrow("expired");
  });
  it("keeps model names unique across an organization and version names within a model", async () => {
    const { member, stage, service, body, objects, files } = await setup();
    await service.complete(
      member.userId,
      member.workspaceId,
      (await stage()).id,
    );
    const workspaceId = await seedWorkspace(db.database, {
      organizationId: member.organizationId,
    });
    const traceTask = async (name: string) =>
      (
        await db.database
          .insert(tasks)
          .values({
            id: randomUUID(),
            workspaceId,
            name,
            baseModelId: body.base_model_id,
          })
          .returning()
      )[0]!;

    await expect(
      service.create(member.userId, workspaceId, {
        ...body,
        create_task: true,
      }),
    ).rejects.toMatchObject({ code: "conflict" });
    // Trace labels register tasks per workspace; only a model claims the name.
    await traceTask(body.task);
    await expect(
      service.create(member.userId, workspaceId, body),
    ).rejects.toMatchObject({ code: "conflict" });

    const other = await traceTask("other-task");
    const upload = await service.create(member.userId, workspaceId, {
      ...body,
      task: other.name,
    });
    objects.set(`uploads/${upload.id}/adapter_config.json`, files.config);
    objects.set(
      `uploads/${upload.id}/adapter_model.safetensors`,
      files.weights,
    );
    const version = await service.complete(
      member.userId,
      workspaceId,
      upload.id,
    );
    expect(version.version.name).toBe(body.name);
    const [claimed] = await db.database
      .select({ organizationId: tasks.organizationId })
      .from(tasks)
      .where(eq(tasks.id, other.id));
    expect(claimed?.organizationId).toBe(member.organizationId);
  });
  it("rejects duplicate task and version names and cleans abandoned artifacts", async () => {
    const { member, stage, service, body, objects } = await setup();
    await expect(
      service.create(member.userId, member.workspaceId, {
        ...body,
        create_task: true,
      }),
    ).rejects.toMatchObject({ code: "conflict" });
    const first = await stage();
    await service.complete(member.userId, member.workspaceId, first.id);
    const second = await stage();
    await expect(
      service.complete(member.userId, member.workspaceId, second.id),
    ).rejects.toMatchObject({ code: "conflict" });
    await db.database
      .update(modelUploads)
      .set({ createdAt: new Date(Date.now() - 86400_000) })
      .where(eq(modelUploads.id, second.id));
    const cleanup = createTrainingArtifactCleanup(
      db.database,
      createMemoryContentStore(objects),
    );
    await cleanup();
    expect(
      [...objects.keys()].some((key) =>
        key.startsWith(`uploads/${second.id}/`),
      ),
    ).toBe(false);
    expect(
      [...objects.keys()].some((key) => key.startsWith(`runs/${second.id}/`)),
    ).toBe(false);
    await cleanup();
    expect(
      [...objects.keys()].some((key) =>
        key.startsWith(`runs/${first.id}/output/`),
      ),
    ).toBe(true);
  });
});
