import { randomUUID } from "node:crypto";
import { eq } from "drizzle-orm";
import { v7 as uuidv7 } from "uuid";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";

import { createCatalogService } from "../src/catalog/service.js";
import { tasks, taskVersions } from "../src/db/schema/index.js";
import { createKubernetesDeploymentStore } from "../src/deployments/kubernetes.js";
import { createDeploymentStore } from "../src/deployments/store.js";
import { createInstanceService } from "../src/instances/service.js";
import { createAdapterHostingService } from "../src/training/hosting.js";
import {
  createAdapterQualifier,
  type AdapterProbe,
  type AdapterQualificationResult,
  type QualificationLock,
} from "../src/training/qualification.js";
import { createTrainingService } from "../src/training/service.js";
import { createMemoryContentStore } from "./support/content-store.js";
import {
  deploymentRelease,
  modelInput,
  seedMember,
} from "./support/fixtures.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";

const REVISION = "a".repeat(40);

describe("adapter qualification on promotion", () => {
  let db: TestDatabase;
  let baseModelId: string;
  let otherModelId: string;
  let loraDeploymentIds: string[];
  let hostId: string;

  beforeAll(async () => {
    db = await createTestDatabase();
    const catalog = createCatalogService(db.database);
    baseModelId = (await catalog.upsertModel(modelInput())).id;
    otherModelId = (await catalog.upsertModel(modelInput())).id;
    const host = await createInstanceService(db.database).register({
      provider: "runpod",
      providerAccountId: "test",
      providerInstanceId: randomUUID(),
      region: "US-NE-1",
      sku: "B300",
      faultDomain: "test-host",
    });
    hostId = host.id;
    const lora = {
      ...deploymentRelease(),
      lora_enabled: true,
      lora_base_model_revision: REVISION,
    };
    const pod = (
      modelId: string,
      release: typeof lora | ReturnType<typeof deploymentRelease>,
      extra: { draining?: boolean } = {},
    ) => ({
      id: randomUUID(),
      name: `pod-${randomUUID()}`,
      instanceId: host.id,
      modelId,
      release,
      qualified: true,
      draining: extra.draining ?? false,
    });
    const pods = [
      pod(baseModelId, lora),
      pod(baseModelId, lora),
      pod(baseModelId, deploymentRelease()),
      pod(baseModelId, lora, { draining: true }),
      pod(otherModelId, lora),
    ];
    loraDeploymentIds = [pods[0]!.id, pods[1]!.id];
    await createKubernetesDeploymentStore(db.database).reconcile({
      running: async () => pods,
      isGone: async () => false,
    });
  });
  afterAll(() => db.dispose());

  const seedUpload = async (role: "admin" | "member" = "admin") => {
    const name = `upload-${randomUUID().slice(0, 8)}`;
    const owner = await seedMember(db.database, { role });
    const [task] = await db.database
      .insert(tasks)
      .values({
        id: uuidv7(),
        organizationId: null,
        workspaceId: owner.workspaceId,
        name,
        baseModelId,
      })
      .returning();
    const versionId = uuidv7();
    const [version] = await db.database
      .insert(taskVersions)
      .values({
        id: versionId,
        workspaceId: owner.workspaceId,
        taskId: task!.id,
        trainingRunId: null,
        name: "v1",
        baseModelId,
        status: "unavailable",
        adapter: {
          format: "peft_lora",
          artifact_uri: `s3://bucket/runs/${versionId}/output/${"b".repeat(64)}/adapter.tar.gz`,
          sha256: "b".repeat(64),
          size_bytes: 2048,
          rank: 2,
          validated_base_model_revision: REVISION,
        },
      })
      .returning();
    return { owner, task: task!, version: version! };
  };

  const setup = (probe: AdapterProbe, lock?: QualificationLock) => {
    const reports: AdapterQualificationResult[] = [];
    const store = createDeploymentStore(db.database);
    const qualify = createAdapterQualifier({
      targets: (modelId) => store.adapterProbeTargets(modelId),
      probe,
      report: (result) => reports.push(result),
      order: (items) => [...items],
    });
    const service = createTrainingService(
      db.database,
      createMemoryContentStore(new Map()),
      undefined,
      undefined,
      undefined,
      undefined,
      qualify,
      lock,
    );
    return { reports, service };
  };

  const stored = async (taskId: string, versionId: string) => ({
    task: (
      await db.database.select().from(tasks).where(eq(tasks.id, taskId))
    )[0]!,
    version: (
      await db.database
        .select()
        .from(taskVersions)
        .where(eq(taskVersions.id, versionId))
    )[0]!,
  });

  it("lists only available LoRA-enabled allocations of the model behind their host proxy", async () => {
    const targets = await createDeploymentStore(
      db.database,
    ).adapterProbeTargets(baseModelId);

    expect(targets.map((target) => target.id).sort()).toEqual(
      [...loraDeploymentIds].sort(),
    );
    for (const target of targets) {
      expect(target.serviceUrl).toBe(
        `http://gpu-${hostId}.tailscale-inference.svc.cluster.local:8888/alloc/${target.id}`,
      );
      expect(target.release.lora_base_model_revision).toBe(REVISION);
    }
  });

  it("qualifies an uploaded version, then makes it the available production version", async () => {
    const { owner, task, version } = await seedUpload();
    const probe = vi.fn<AdapterProbe>(async () => ({ ok: true }));
    const { reports, service } = setup(probe);

    const promoted = await service.promote(
      owner.userId,
      owner.workspaceId,
      task.name,
      version.id,
    );

    expect(promoted.productionVersionId).toBe(version.id);
    expect(probe.mock.calls.map(([target]) => target.id).sort()).toEqual(
      [...loraDeploymentIds].sort(),
    );
    for (const [, identity] of probe.mock.calls)
      expect(identity).toEqual({
        workspaceId: owner.workspaceId,
        versionId: version.id,
      });
    const after = await stored(task.id, version.id);
    expect(after.version.status).toBe("available");
    expect(after.task.productionVersionId).toBe(version.id);
    expect(reports).toMatchObject([
      { outcome: "passed", attempts: 2, versionId: version.id },
    ]);

    // GPU preload now lists it, under the version ID runtimes use.
    const hosting = createAdapterHostingService(db.database, {
      sign: async () => ({
        url: "https://bucket.s3.amazonaws.com/a",
        expires_at: "2030-01-01T00:00:00Z",
      }),
    });
    expect(await hosting.productionVersions(baseModelId)).toContainEqual({
      workspace_id: owner.workspaceId,
      version_name: version.id,
    });

    // Promoting an available version again skips qualification.
    await service.promote(
      owner.userId,
      owner.workspaceId,
      task.name,
      version.id,
    );
    expect(probe).toHaveBeenCalledTimes(2);
  });

  it("passes when one allocation cannot test the adapter and another passes", async () => {
    const { owner, task, version } = await seedUpload();
    const probe = vi
      .fn<AdapterProbe>()
      .mockResolvedValueOnce({
        ok: false,
        rejected: false,
        reason: "capacity_unavailable",
      })
      .mockResolvedValueOnce({ ok: true });
    const { reports, service } = setup(probe);

    await service.promote(
      owner.userId,
      owner.workspaceId,
      task.name,
      version.id,
    );

    expect(probe).toHaveBeenCalledTimes(2);
    expect(new Set(probe.mock.calls.map(([target]) => target.id)).size).toBe(2);
    expect(reports).toMatchObject([{ outcome: "passed", attempts: 2 }]);
    expect((await stored(task.id, version.id)).version.status).toBe(
      "available",
    );
  });

  it.each([
    ["rejected", true, "invalid_adapter", "conflict", 2],
    ["failed", false, "preparation_failed", "unavailable", 2],
  ] as const)(
    "leaves a %s adapter unavailable and production unchanged",
    async (outcome, rejected, reason, code, attempts) => {
      const { owner, task, version } = await seedUpload();
      const probe = vi.fn<AdapterProbe>(async () => ({
        ok: false,
        rejected,
        reason,
      }));
      const { reports, service } = setup(probe);

      await expect(
        service.promote(owner.userId, owner.workspaceId, task.name, version.id),
      ).rejects.toMatchObject({ code });

      expect(probe).toHaveBeenCalledTimes(attempts);
      const after = await stored(task.id, version.id);
      expect(after.version.status).toBe("unavailable");
      expect(after.task.productionVersionId).toBeNull();
      expect(reports).toMatchObject([{ outcome, attempts, reason }]);
    },
  );

  it("does not overwrite a promotion made while the adapter was being tested", async () => {
    const { owner, task, version } = await seedUpload();
    const [other] = await db.database
      .insert(taskVersions)
      .values({
        ...version,
        id: uuidv7(),
        name: "already-serving",
        status: "available",
      })
      .returning();
    const probe = vi.fn<AdapterProbe>(async () => {
      await db.database
        .update(tasks)
        .set({ productionVersionId: other!.id })
        .where(eq(tasks.id, task.id));
      return { ok: true };
    });
    const { service } = setup(probe);

    await expect(
      service.promote(owner.userId, owner.workspaceId, task.name, version.id),
    ).rejects.toMatchObject({ code: "conflict" });

    const after = await stored(task.id, version.id);
    expect(after.task.productionVersionId).toBe(other!.id);
    expect(after.version.status).toBe("available");
  });

  it("succeeds when a concurrent promotion of the same version already won", async () => {
    const { owner, task, version } = await seedUpload();
    const probe = vi.fn<AdapterProbe>(async () => {
      await db.database
        .update(tasks)
        .set({ productionVersionId: version.id })
        .where(eq(tasks.id, task.id));
      return { ok: true };
    });
    const { service } = setup(probe);

    const promoted = await service.promote(
      owner.userId,
      owner.workspaceId,
      task.name,
      version.id,
    );

    expect(promoted.productionVersionId).toBe(version.id);
  });

  it("refuses a version another request is already qualifying", async () => {
    const { owner, task, version } = await seedUpload();
    const probe = vi.fn<AdapterProbe>(async () => ({ ok: true }));
    const { service } = setup(probe, async () => undefined);

    await expect(
      service.promote(owner.userId, owner.workspaceId, task.name, version.id),
    ).rejects.toMatchObject({ code: "conflict" });

    expect(probe).not.toHaveBeenCalled();
    expect((await stored(task.id, version.id)).version.status).toBe(
      "unavailable",
    );
  });

  it.each([
    ["passes", { ok: true } as const, 200],
    [
      "fails",
      { ok: false, rejected: false, reason: "probe_timeout" } as const,
      503,
    ],
  ])(
    "holds the version lock until the promotion %s",
    async (_, outcome, status) => {
      const { owner, task, version } = await seedUpload();
      const events: string[] = [];
      const probe = vi.fn<AdapterProbe>(async () => {
        events.push("probe");
        return outcome;
      });
      const { service } = setup(probe, async (versionId) => {
        events.push(`lock:${versionId}`);
        return async () => {
          events.push(
            `release:${(await stored(task.id, version.id)).version.status}`,
          );
        };
      });

      const result = await service
        .promote(owner.userId, owner.workspaceId, task.name, version.id)
        .then(
          () => 200,
          () => 503,
        );

      expect(result).toBe(status);
      expect(events[0]).toBe(`lock:${version.id}`);
      expect(events.at(-1)).toBe(
        status === 200 ? "release:available" : "release:unavailable",
      );
    },
  );

  it("reports missing capacity without probing", async () => {
    const { owner, task, version } = await seedUpload();
    await db.database
      .update(taskVersions)
      .set({
        adapter: {
          ...version.adapter,
          validated_base_model_revision: "c".repeat(40),
        },
      })
      .where(eq(taskVersions.id, version.id));
    const probe = vi.fn<AdapterProbe>(async () => ({ ok: true }));
    const { reports, service } = setup(probe);

    await expect(
      service.promote(owner.userId, owner.workspaceId, task.name, version.id),
    ).rejects.toMatchObject({ code: "unavailable" });

    expect(probe).not.toHaveBeenCalled();
    expect(reports).toMatchObject([{ outcome: "no_capacity", attempts: 0 }]);
    expect((await stored(task.id, version.id)).version.status).toBe(
      "unavailable",
    );
  });

  it("does not let a member qualify a version", async () => {
    const { task, version, owner } = await seedUpload("member");
    const probe = vi.fn<AdapterProbe>(async () => ({ ok: true }));
    const { service } = setup(probe);

    await expect(
      service.promote(owner.userId, owner.workspaceId, task.name, version.id),
    ).rejects.toMatchObject({ code: "forbidden" });
    expect(probe).not.toHaveBeenCalled();
  });
});
