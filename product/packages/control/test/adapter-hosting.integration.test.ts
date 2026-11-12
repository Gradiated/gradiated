import { eq, sql } from "drizzle-orm";
import { v7 as uuidv7 } from "uuid";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { createCatalogService } from "../src/catalog/service.js";
import {
  organizations,
  tasks,
  taskVersions,
  trainingRuns,
  workspaces,
} from "../src/db/schema/index.js";
import { createAdapterHostingService } from "../src/training/hosting.js";
import { modelInput, seedMember } from "./support/fixtures.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";

const sha256 = "a".repeat(64);

describe("private adapter hosting", () => {
  let db: TestDatabase;
  let baseModelId: string;
  beforeAll(async () => {
    db = await createTestDatabase();
    const model = modelInput();
    await createCatalogService(db.database).upsertModel(model);
    baseModelId = model.id;
  });
  afterAll(() => db.dispose());

  const seed = async (status: "available" | "unavailable" = "available") => {
    const owner = await seedMember(db.database, { role: "admin" });
    const [task] = await db.database
      .insert(tasks)
      .values({
        id: uuidv7(),
        organizationId: owner.organizationId,
        workspaceId: owner.workspaceId,
        name: "triage",
      })
      .returning();
    const runId = uuidv7();
    await db.database.insert(trainingRuns).values({
      id: runId,
      taskId: task!.id,
      trigger: "manual",
      stage: "succeeded",
      baseModelId,
      inputCutoff: new Date(),
      finishedAt: new Date(),
    });
    const [version] = await db.database
      .insert(taskVersions)
      .values({
        id: uuidv7(),
        workspaceId: owner.workspaceId,
        taskId: task!.id,
        trainingRunId: runId,
        name: "triage-v1",
        baseModelId,
        status,
        adapter: {
          format: "peft_lora",
          artifact_uri: `s3://bucket/runs/${runId}/adapter.tar.gz`,
          sha256,
          size_bytes: 1024,
          rank: 2,
          base_model_revision: "frozen-revision",
        },
      })
      .returning();
    return { owner, task: task!, version: version! };
  };
  const service = () => {
    const sign = vi.fn(async () => ({
      url: "https://bucket.s3.amazonaws.com/adapter?signature=test",
      expires_at: "2030-01-01T00:00:00Z",
    }));
    return {
      sign,
      hosting: createAdapterHostingService(db.database, { sign }),
    };
  };
  const promote = async (taskId: string, versionId: string) => {
    await db.database
      .update(tasks)
      .set({ productionVersionId: versionId })
      .where(eq(tasks.id, taskId));
  };

  it("signs the exact immutable artifact, including an unavailable qualification candidate", async () => {
    const { owner, task, version } = await seed("unavailable");
    const { hosting, sign } = service();
    const result = await hosting.grant(
      owner.workspaceId,
      `${task.name}/${version.name}`,
    );
    expect(result.task.id).toBe(task.id);
    expect(result.version.status).toBe("unavailable");
    expect(result.download.url).toContain("signature=test");
    expect(sign).toHaveBeenCalledWith(
      version.adapter.artifact_uri,
      version.trainingRunId,
      1024,
      sha256,
    );
    expect(
      (await db.database.select().from(tasks).where(eq(tasks.id, task.id)))[0]!
        .productionVersionId,
    ).toBeNull();
  });

  it("rejects workspace and version name mismatches without signing", async () => {
    const { owner, task, version } = await seed();
    const { hosting, sign } = service();
    for (const [workspaceId, name] of [
      [uuidv7(), `${task.name}/${version.name}`],
      [owner.workspaceId, "missing-version"],
      [owner.workspaceId, `other-task/${version.name}`],
    ]) {
      await expect(hosting.grant(workspaceId!, name!)).rejects.toMatchObject({
        code: "not_found",
      });
    }
    expect(sign).not.toHaveBeenCalled();
  });

  it.each(["archived", "suspended"] as const)(
    "excludes %s ownership from grants and startup",
    async (state) => {
      const { owner, task, version } = await seed();
      await promote(task.id, version.id);
      if (state === "archived")
        await db.database
          .update(workspaces)
          .set({ archivedAt: new Date() })
          .where(eq(workspaces.id, owner.workspaceId));
      else
        await db.database
          .update(organizations)
          .set({ status: "suspended" })
          .where(eq(organizations.id, owner.organizationId));
      const { hosting, sign } = service();
      await expect(
        hosting.grant(owner.workspaceId, version.name),
      ).rejects.toMatchObject({ code: "not_found" });
      expect(await hosting.productionVersions(baseModelId)).not.toContainEqual(
        expect.objectContaining({
          workspace_id: version.workspaceId,
          version_name: `${task.name}/${version.name}`,
        }),
      );
      expect(sign).not.toHaveBeenCalled();
    },
  );

  it.each(["revision", "archive"] as const)(
    "rejects a missing %s without signing",
    async (missing) => {
      const { owner, task, version } = await seed();
      const adapter = {
        ...version.adapter,
        ...(missing === "revision"
          ? { base_model_revision: undefined }
          : { size_bytes: 0 }),
      };
      await db.database
        .update(taskVersions)
        .set({ adapter })
        .where(eq(taskVersions.id, version.id));
      await promote(task.id, version.id);
      const { hosting, sign } = service();
      await expect(
        hosting.grant(owner.workspaceId, version.name),
      ).rejects.toMatchObject({ code: "unavailable" });
      expect(await hosting.productionVersions(baseModelId)).not.toContainEqual(
        expect.objectContaining({
          workspace_id: version.workspaceId,
          version_name: `${task.name}/${version.name}`,
        }),
      );
      expect(sign).not.toHaveBeenCalled();
    },
  );

  it("lists only current available pointers for the requested base without signing", async () => {
    const selected = await seed();
    const unpromoted = await seed();
    const unavailable = await seed("unavailable");
    await promote(selected.task.id, selected.version.id);
    await promote(unavailable.task.id, unavailable.version.id);
    const { hosting, sign } = service();
    const targets = await hosting.productionVersions(baseModelId);
    expect(targets).toContainEqual({
      workspace_id: selected.owner.workspaceId,
      version_name: `${selected.task.name}/${selected.version.name}`,
    });
    for (const { task, version } of [unpromoted, unavailable])
      expect(targets).not.toContainEqual(
        expect.objectContaining({
          workspace_id: version.workspaceId,
          version_name: `${task.name}/${version.name}`,
        }),
      );
    expect(await hosting.productionVersions("gradiated/no-adapters")).toEqual(
      [],
    );
    expect(sign).not.toHaveBeenCalled();
  });

  it("filters legacy production pointers before applying the startup cap", async () => {
    const selected = await seed();
    await promote(selected.task.id, selected.version.id);
    await db.database
      .update(tasks)
      .set({ updatedAt: new Date("2000-01-01") })
      .where(eq(tasks.id, selected.task.id));
    const legacy = Array.from({ length: 4096 }, (_, index) => ({
      task: uuidv7(),
      run: uuidv7(),
      version: uuidv7(),
      name: "legacy-" + index,
    }));
    await db.database.insert(tasks).values(
      legacy.map((item) => ({
        id: item.task,
        organizationId: selected.owner.organizationId,
        workspaceId: selected.owner.workspaceId,
        name: item.name,
      })),
    );
    await db.database.insert(trainingRuns).values(
      legacy.map((item) => ({
        id: item.run,
        taskId: item.task,
        trigger: "manual" as const,
        stage: "succeeded" as const,
        baseModelId,
        inputCutoff: new Date(),
        finishedAt: new Date(),
      })),
    );
    await db.database.insert(taskVersions).values(
      legacy.map((item) => ({
        id: item.version,
        taskId: item.task,
        workspaceId: selected.owner.workspaceId,
        trainingRunId: item.run,
        name: item.name,
        baseModelId,
        status: "available" as const,
        adapter: {
          ...selected.version.adapter,
          base_model_revision: undefined,
        },
      })),
    );
    await db.database.execute(
      sql`update ${tasks} set production_version_id = ${taskVersions.id} from ${taskVersions} where ${tasks.id} = ${taskVersions.taskId} and ${tasks.workspaceId} = ${selected.owner.workspaceId}`,
    );
    expect(
      await service().hosting.productionVersions(baseModelId),
    ).toContainEqual({
      workspace_id: selected.owner.workspaceId,
      version_name: `${selected.task.name}/${selected.version.name}`,
    });
  });

  it("does not follow a production pointer into a different task", async () => {
    const first = await seed();
    const second = await seed();
    await promote(first.task.id, second.version.id);
    const { hosting } = service();
    expect(await hosting.productionVersions(baseModelId)).not.toContainEqual(
      expect.objectContaining({
        workspace_id: second.version.workspaceId,
        version_name: `${second.task.name}/${second.version.name}`,
      }),
    );
  });

  it("propagates signing failures without changing the production pointer", async () => {
    const { owner, task, version } = await seed();
    const { hosting, sign } = service();
    sign.mockRejectedValueOnce(new Error("storage unavailable"));
    await expect(
      hosting.grant(owner.workspaceId, version.name),
    ).rejects.toThrow("storage unavailable");
    expect(
      (await db.database.select().from(tasks).where(eq(tasks.id, task.id)))[0]!
        .productionVersionId,
    ).toBeNull();
  });
});
