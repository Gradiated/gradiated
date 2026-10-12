import { randomUUID } from "node:crypto";

import { eq } from "drizzle-orm";
import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";

import {
  createCatalogService,
  type CatalogService,
} from "../src/catalog/service.js";
import { modelDeployments } from "../src/db/schema/index.js";
import {
  createInstanceService,
  type InstanceRecord,
} from "../src/instances/service.js";
import {
  createNomadDeploymentStore,
  type NomadAllocation,
  type NomadDeploymentStore,
} from "../src/deployments/nomad.js";
import {
  deploymentInput,
  deploymentRelease,
  modelInput,
} from "./support/fixtures.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";

describe("Nomad deployment reconciliation", () => {
  let testDatabase: TestDatabase;
  let catalog: CatalogService;
  let store: NomadDeploymentStore;
  let modelId: string;
  let host: InstanceRecord;
  let nodeId: string;

  beforeAll(async () => {
    testDatabase = await createTestDatabase();
    catalog = createCatalogService(testDatabase.database);
    store = createNomadDeploymentStore(testDatabase.database);
  });

  afterAll(() => testDatabase.dispose());

  beforeEach(async () => {
    await testDatabase.database.delete(modelDeployments);
    modelId = (await catalog.upsertModel(modelInput())).id;
    nodeId = randomUUID();
    const instances = createInstanceService(testDatabase.database);
    const registered = await instances.register({
      provider: "runpod",
      providerAccountId: "user_test",
      providerInstanceId: `pod${randomUUID().slice(0, 8)}`,
      region: "US-NE-1",
      faultDomain: "runpod:machine-a",
      sku: "2x NVIDIA RTX PRO 6000 Blackwell Server Edition",
    });
    await instances.bindNomadNode(registered.id, nodeId);
    host = await instances.setServingUrl(
      registered.id,
      `http://gpu-${registered.id}.tailscale-inference.svc.cluster.local:8888`,
    );
  });

  const allocation = (
    overrides: Partial<NomadAllocation> = {},
  ): NomadAllocation => ({
    allocationId: randomUUID(),
    nodeId,
    modelId,
    release: deploymentRelease(),
    draining: false,
    ...overrides,
  });

  const nomad = (
    running: NomadAllocation[],
    isGone: (allocationId: string) => Promise<boolean> = async () => true,
  ) => ({ running: async () => running, isGone });

  const deploymentsOf = (id: string) =>
    testDatabase.database
      .select()
      .from(modelDeployments)
      .where(eq(modelDeployments.id, id));

  it("routes a running allocation through its host's proxy", async () => {
    const running = allocation();

    const result = await store.reconcile(nomad([running]));

    expect(result).toEqual({ written: 1, removed: 0, unplaced: [] });
    expect(
      await store.verificationReplicas(modelId, [running.allocationId]),
    ).toEqual([
      {
        id: running.allocationId,
        modelId,
        status: "available",
        release: running.release,
      },
    ]);
    expect(await deploymentsOf(running.allocationId)).toMatchObject([
      {
        modelId,
        instanceId: host.id,
        status: "available",
        provider: "runpod",
        region: "US-NE-1",
        faultDomain: "runpod:machine-a",
        serviceUrl: `http://gpu-${host.id}.tailscale-inference.svc.cluster.local:8888/alloc/${running.allocationId}`,
        release: running.release,
      },
    ]);
  });

  it("withdraws a serving allocation when its private endpoint is unset", async () => {
    const running = allocation();
    await store.reconcile(nomad([running]));
    await createInstanceService(testDatabase.database).setServingUrl(
      host.id,
      null,
    );

    expect(await store.reconcile(nomad([running]))).toMatchObject({
      written: 0,
      unplaced: [
        {
          allocationId: running.allocationId,
          reason: "provider_has_no_serving_address",
        },
      ],
    });
    expect(await deploymentsOf(running.allocationId)).toMatchObject([
      { status: "unavailable" },
    ]);
    expect(await store.replicas()).toEqual([]);
  });

  it("keeps migrated allocations and metrics on their registered private endpoint", async () => {
    const running = allocation({
      release: { ...deploymentRelease(), lora_enabled: true },
    });
    await store.reconcile(nomad([running]));
    const servingUrl = `http://gpu-${host.id}.tailscale-inference.svc.cluster.local:8888`;

    await createInstanceService(testDatabase.database).setServingUrl(
      host.id,
      servingUrl,
    );
    await store.reconcile(nomad([running]));
    await store.reconcile(nomad([running]));

    expect(await deploymentsOf(running.allocationId)).toMatchObject([
      { serviceUrl: `${servingUrl}/alloc/${running.allocationId}` },
    ]);
    expect(await store.adapterMetricsTargets()).toMatchObject([
      { serviceUrl: `${servingUrl}/alloc/${running.allocationId}` },
    ]);
  });

  it("drains an allocation Nomad is stopping", async () => {
    const stopping = allocation({ draining: true });

    await store.reconcile(nomad([stopping]));

    expect(await deploymentsOf(stopping.allocationId)).toMatchObject([
      { status: "draining" },
    ]);
  });

  it("keeps an unverified canary out of customer routing until promotion", async () => {
    const canary = allocation({ verificationPending: true });
    await store.reconcile(nomad([canary]));
    expect(await deploymentsOf(canary.allocationId)).toMatchObject([
      { status: "unavailable" },
    ]);
    await store.reconcile(nomad([{ ...canary, verificationPending: false }]));
    expect(await deploymentsOf(canary.allocationId)).toMatchObject([
      { status: "available" },
    ]);
  });

  it("keeps a qualified replica serving while a scale-up is verified", async () => {
    const existing = allocation();
    const added = allocation({ verificationPending: true });
    await store.reconcile(nomad([existing]));

    await store.reconcile(
      nomad([{ ...existing, verificationPending: true }, added]),
    );

    expect(await deploymentsOf(existing.allocationId)).toMatchObject([
      { status: "available" },
    ]);
    expect(await deploymentsOf(added.allocationId)).toMatchObject([
      { status: "unavailable" },
    ]);

    await store.reconcile(
      nomad([
        { ...existing, verificationPending: true, draining: true },
        added,
      ]),
    );
    expect(await deploymentsOf(existing.allocationId)).toMatchObject([
      { status: "draining" },
    ]);
  });

  it("keeps exactly one available allocation per slot across stale health snapshots and rollback", async () => {
    const original = allocation({
      replica: { key: "slot-0", child: true, order: 10 },
    });
    const replacement = allocation({
      replica: { key: "slot-0", child: true, order: 20 },
    });
    const peer = allocation({
      replica: { key: "slot-1", child: true, order: 15 },
    });
    const frames = [
      [original, { ...replacement, verificationPending: true }, peer],
      [{ ...original, draining: true }, replacement, peer],
      [original, { ...replacement, verificationPending: true }, peer],
      [{ ...original, verificationPending: true }, replacement, peer],
      [original, { ...replacement, draining: true }, peer],
    ];
    for (const frame of frames) {
      await store.reconcile(nomad(frame));
      expect(await store.replicas()).toHaveLength(2);
    }
    expect((await store.replicas()).map((row) => row.id).sort()).toEqual(
      [original.allocationId, peer.allocationId].sort(),
    );
    expect(await deploymentsOf(replacement.allocationId)).toMatchObject([
      { status: "draining" },
    ]);
  });

  it("does not carry qualification to changed release contents on the same allocation", async () => {
    const existing = allocation();
    await store.reconcile(nomad([existing]));

    await store.reconcile(
      nomad([
        {
          ...existing,
          verificationPending: true,
          release: {
            ...existing.release,
            runtime_revision: "unverified-revision",
          },
        },
      ]),
    );

    expect(await deploymentsOf(existing.allocationId)).toMatchObject([
      { status: "unavailable" },
    ]);
  });

  it("follows a new release on the same allocation", async () => {
    const running = allocation();
    await store.reconcile(nomad([running]));
    const release = { ...running.release, runtime_revision: "next-revision" };

    await store.reconcile(nomad([{ ...running, release }]));

    expect(await deploymentsOf(running.allocationId)).toMatchObject([
      { release },
    ]);
  });

  it("removes gone allocation deployments, including legacy rows without an instance", async () => {
    const gone = allocation();
    await store.reconcile(nomad([gone]));
    const configured = await catalog.upsertModelDeployment(
      deploymentInput(modelId),
    );

    const result = await store.reconcile(nomad([]));

    expect(result).toMatchObject({ removed: 2 });
    expect(await deploymentsOf(gone.allocationId)).toEqual([]);
    expect(await deploymentsOf(configured.id)).toEqual([]);
  });

  it("keeps a running allocation's deployment while it is temporarily unroutable", async () => {
    const running = allocation();
    await store.reconcile(nomad([running]));

    const result = await store.reconcile(
      nomad([{ ...running, nodeId: randomUUID() }]),
    );

    expect(result).toMatchObject({ written: 0, removed: 0 });
    expect(await deploymentsOf(running.allocationId)).toMatchObject([
      { status: "available", instanceId: host.id },
    ]);
  });

  it("keeps a deployment Nomad stops listing until Nomad confirms the allocation is gone", async () => {
    const running = allocation();
    await store.reconcile(nomad([running]));

    const result = await store.reconcile(nomad([], async () => false));

    expect(result).toMatchObject({ removed: 0 });
    expect(await deploymentsOf(running.allocationId)).toHaveLength(1);
  });

  it("changes nothing when Nomad cannot confirm a removal", async () => {
    const running = allocation();
    await store.reconcile(nomad([running]));

    await expect(
      store.reconcile(
        nomad([], async () => {
          throw new Error("Nomad refused");
        }),
      ),
    ).rejects.toThrow("Nomad refused");
    expect(await deploymentsOf(running.allocationId)).toHaveLength(1);
  });

  it("lists available replicas and excludes draining allocations", async () => {
    const running = allocation();
    const stopping = allocation({ draining: true });
    await store.reconcile(nomad([running, stopping]));

    expect(await store.replicas()).toEqual([
      {
        id: running.allocationId,
        modelId,
        release: running.release,
      },
    ]);
  });

  it("discovers only qualified serving loaders and excludes startup canaries, disabled and draining allocations", async () => {
    const enabled = { ...deploymentRelease(), lora_enabled: true };
    const running = allocation({ release: enabled });
    const canary = allocation({ release: enabled, verificationPending: true });
    const stopping = allocation({ release: enabled, draining: true });
    await store.reconcile(nomad([running, canary, stopping, allocation()]));
    const targets = await store.adapterMetricsTargets();
    expect(targets.map((target) => target.id).sort()).toEqual(
      [running.allocationId].sort(),
    );
    await testDatabase.database
      .update(modelDeployments)
      .set({ serviceUrl: "https://untrusted.example/metrics" })
      .where(eq(modelDeployments.id, running.allocationId));
    expect(
      (await store.adapterMetricsTargets()).map((target) => target.id),
    ).toEqual([]);

    await store.reconcile(
      nomad([running, { ...canary, verificationPending: false }, stopping]),
    );
    expect(
      (await store.adapterMetricsTargets()).map((target) => target.id).sort(),
    ).toEqual([running.allocationId, canary.allocationId].sort());

    for (const target of targets) {
      expect(target.modelId).toBe(modelId);
      expect(target.serviceUrl).toBe(
        `http://gpu-${host.id}.tailscale-inference.svc.cluster.local:8888/alloc/${target.id}`,
      );
    }
  });

  it("reports allocations it cannot route instead of failing the pass", async () => {
    const unregistered = allocation({ nodeId: randomUUID() });
    const uncatalogued = allocation({ modelId: `test/${randomUUID()}` });
    const running = allocation();

    const result = await store.reconcile(
      nomad([unregistered, uncatalogued, running]),
    );

    expect(result).toEqual({
      written: 1,
      removed: 0,
      unplaced: [
        {
          allocationId: unregistered.allocationId,
          modelId,
          reason: "node_not_registered",
        },
        {
          allocationId: uncatalogued.allocationId,
          modelId: uncatalogued.modelId,
          reason: "model_not_in_catalog",
        },
      ],
    });
  });

  it("skips a pass while another worker holds it", async () => {
    let release!: () => void;
    const held = new Promise<void>((resolve) => (release = resolve));
    let entered!: () => void;
    const holding = new Promise<void>((resolve) => (entered = resolve));

    const first = store.reconcile({
      running: async () => {
        entered();
        await held;
        return [];
      },
      isGone: async () => true,
    });
    await holding;
    const second = await store.reconcile({
      running: async () => {
        throw new Error("a concurrent pass must not read Nomad");
      },
      isGone: async () => true,
    });
    release();

    expect(second).toBeNull();
    await expect(first).resolves.toMatchObject({ written: 0 });
  });
  it("rejects invalid release JSON before committing a reconciliation pass", async () => {
    const valid = allocation();
    const invalid = allocation({
      release: { ...deploymentRelease(), schema_version: 2 as 1 },
    });

    await expect(
      store.reconcile(nomad([valid, invalid])),
    ).rejects.toMatchObject({ name: "ZodError" });
    expect(await deploymentsOf(valid.allocationId)).toEqual([]);
    expect(await deploymentsOf(invalid.allocationId)).toEqual([]);
  });

  it("rejects corrupt stored release JSON before returning replicas", async () => {
    const running = allocation();
    await store.reconcile(nomad([running]));
    await testDatabase.database
      .update(modelDeployments)
      .set({
        release: { ...running.release, schema_version: 2 as 1 },
      })
      .where(eq(modelDeployments.id, running.allocationId));

    await expect(store.replicas()).rejects.toMatchObject({ name: "ZodError" });
    await expect(
      store.verificationReplicas(modelId, [running.allocationId]),
    ).rejects.toMatchObject({ name: "ZodError" });
  });
});
