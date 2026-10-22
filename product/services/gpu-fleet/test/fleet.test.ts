import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { RETIRE_GRACE_MS, syncFleetInstances } from "@gradiated/control";

import { instances } from "../../../packages/control/src/db/schema/instances.js";
import {
  createTestDatabase,
  type TestDatabase,
} from "../../../packages/control/test/support/postgres.js";
import { createFleet } from "../src/fleet.js";
import { GPU_HOSTS, SERVICES } from "../src/hosts.js";
import { createMetrics } from "../src/metrics.js";
import { pingHost } from "../src/observe.js";
import { UNREACHABLE_AFTER_MS } from "../src/status.js";
import { fakeKubernetes } from "./support/kubernetes.js";
import {
  FIRST,
  SECOND,
  fakeHostAgents,
  gpuHost,
  hostPath,
} from "./support/fleet.js";

describe("the GPU fleet operator", () => {
  let database: TestDatabase;
  let agents: Awaited<ReturnType<typeof fakeHostAgents>>;
  beforeAll(async () => {
    database = await createTestDatabase();
  });
  afterAll(() => database.dispose());
  afterEach(async () => {
    await agents?.close();
    await database.database.delete(instances);
  });

  const operator = async () => {
    const cluster = fakeKubernetes();
    agents = await fakeHostAgents();
    const metrics = createMetrics();
    const events: Record<string, unknown>[] = [];
    // Moving the sync clock past the retirement grace lets a test retire rows.
    let syncTime = new Date();
    const replica = (now?: () => Date) =>
      createFleet({
        api: cluster.api,
        metrics,
        ping: (id) => pingHost(id, agents.keys, agents.endpoint, 200),
        sync: () => (hosts, beforeCommit) =>
          syncFleetInstances(database.database, hosts, {
            now: syncTime,
            beforeCommit,
          }),
        leading: () => true,
        log: (event) => events.push(event),
        ...(now && { now }),
      });
    const skipGrace = () => {
      syncTime = new Date(Date.now() + RETIRE_GRACE_MS + 60_000);
    };
    return { cluster, metrics, events, replica, skipGrace };
  };
  const phase = (cluster: ReturnType<typeof fakeKubernetes>, id: string) =>
    (cluster.read(hostPath(id))?.status as { phase?: string } | undefined)
      ?.phase;
  const rows = async () =>
    (await database.database.select().from(instances)).sort((a, b) =>
      a.id.localeCompare(b.id),
    );

  it("brings a new fleet up: Services, PostgreSQL rows and Ready hosts", async () => {
    const { cluster, metrics, replica } = await operator();
    for (const [id, pod] of [
      [FIRST, "firstpod"],
      [SECOND, "secondpod"],
    ] as const) {
      cluster.seed(GPU_HOSTS, gpuHost(id, pod));
      await agents.addKey(id);
    }
    const fleet = replica();
    await fleet.syncDatabase();
    await fleet.reconcile();

    expect(cluster.read(`${SERVICES}/gpu-${FIRST}`)).toBeDefined();
    expect(cluster.read(`${SERVICES}/gpu-${SECOND}`)).toBeDefined();
    expect(phase(cluster, FIRST)).toBe("Ready");
    expect(phase(cluster, SECOND)).toBe("Ready");
    expect(
      (await rows()).map((row) => [row.id, row.providerInstanceId]),
    ).toEqual([
      [FIRST, "firstpod"],
      [SECOND, "secondpod"],
    ]);
    expect(
      await metrics.registry.getSingleMetricAsString(
        "gradiated_gpu_fleet_hosts",
      ),
    ).toContain('gradiated_gpu_fleet_hosts{phase="Ready"} 2');
  });

  it("changes nothing when a restarted operator reconciles a settled fleet", async () => {
    const { cluster, replica } = await operator();
    cluster.seed(GPU_HOSTS, gpuHost(FIRST, "firstpod"));
    await agents.addKey(FIRST);
    await replica().syncDatabase();
    await replica().reconcile();
    const service = cluster.read(`${SERVICES}/gpu-${FIRST}`);
    const before = await rows();
    const writes = cluster.calls.length;

    const restarted = replica();
    await restarted.syncDatabase();
    await restarted.reconcile();
    // lastSeen alone changed, which is not worth a write yet.
    expect(
      cluster.calls
        .slice(writes)
        .filter((call) => ["POST", "PUT", "PATCH"].includes(call.method)),
    ).toEqual([]);
    expect(cluster.read(`${SERVICES}/gpu-${FIRST}`)).toEqual(service);
    expect(await rows()).toEqual(before);
  });

  it("retires a deleted host and restores it when it is added back", async () => {
    const { cluster, replica, skipGrace } = await operator();
    cluster.seed(GPU_HOSTS, gpuHost(FIRST, "firstpod"));
    cluster.seed(GPU_HOSTS, gpuHost(SECOND, "secondpod"));
    const fleet = replica();
    await fleet.syncDatabase();

    cluster.remove(hostPath(SECOND));
    await fleet.syncDatabase();
    expect(
      (await rows()).find((row) => row.id === SECOND)?.retiredAt,
    ).toBeNull();
    skipGrace();
    await fleet.syncDatabase();
    expect(
      (await rows()).find((row) => row.id === SECOND)?.retiredAt,
    ).toBeInstanceOf(Date);

    cluster.seed(GPU_HOSTS, gpuHost(SECOND, "secondpod"));
    await fleet.syncDatabase();
    expect(
      (await rows()).find((row) => row.id === SECOND)?.retiredAt,
    ).toBeNull();
  });

  it("reports a PostgreSQL conflict on the host and leaves the row alone", async () => {
    const { cluster, metrics, replica, events } = await operator();
    cluster.seed(GPU_HOSTS, gpuHost(FIRST, "firstpod"));
    await agents.addKey(FIRST);
    const fleet = replica();
    await fleet.syncDatabase();
    // Someone edits the pod ID in Git to a different pod.
    cluster.remove(hostPath(FIRST));
    cluster.seed(GPU_HOSTS, gpuHost(FIRST, "otherpod"));

    await fleet.syncDatabase();
    await fleet.reconcile();
    const status = cluster.read(hostPath(FIRST))?.status as {
      phase: string;
      conditions: { type: string; reason: string }[];
    };
    expect(status.phase).toBe("Degraded");
    expect(status.conditions).toContainEqual(
      expect.objectContaining({ type: "Degraded", reason: "PostgresConflict" }),
    );
    expect((await rows())[0]?.providerInstanceId).toBe("firstpod");
    expect(events).toContainEqual(
      expect.objectContaining({
        event: "gpu_instance_conflict",
        instance_id: FIRST,
      }),
    );
    expect(
      await metrics.registry.getSingleMetricAsString(
        "gradiated_gpu_fleet_host_degraded",
      ),
    ).toContain(`instance_id="${FIRST}",reason="PostgresConflict"} 1`);
  });

  it("marks a host that stops answering Degraded without touching its Service", async () => {
    const { cluster, replica } = await operator();
    const created = new Date(Date.now() - 10 * 60_000).toISOString();
    cluster.seed(GPU_HOSTS, {
      ...gpuHost(FIRST, "firstpod"),
      metadata: { name: `gpu-${FIRST}`, creationTimestamp: created },
    });
    let time = new Date();
    const fleet = replica(() => time);
    await fleet.reconcile();
    const service = cluster.read(`${SERVICES}/gpu-${FIRST}`);
    // A new leader first waits out its own grace period.
    expect(phase(cluster, FIRST)).toBe("Pending");

    time = new Date(time.getTime() + UNREACHABLE_AFTER_MS);
    await fleet.reconcile();
    expect(phase(cluster, FIRST)).toBe("Degraded");
    expect(cluster.read(`${SERVICES}/gpu-${FIRST}`)).toEqual(service);
  });

  it("starts the PostgreSQL sync when the credential appears later", async () => {
    const cluster = fakeKubernetes();
    agents = await fakeHostAgents();
    cluster.seed(GPU_HOSTS, gpuHost(FIRST, "firstpod"));
    await agents.addKey(FIRST);
    const metrics = createMetrics();
    let credential = false;
    const fleet = createFleet({
      api: cluster.api,
      metrics,
      ping: (id) => pingHost(id, agents.keys, agents.endpoint, 200),
      sync: () =>
        credential
          ? (hosts) => syncFleetInstances(database.database, hosts)
          : undefined,
      leading: () => true,
      log: () => {},
    });
    const configured = () =>
      metrics.registry.getSingleMetricAsString(
        "gradiated_gpu_fleet_postgres_configured",
      );

    await fleet.syncDatabase();
    await fleet.reconcile();
    expect(phase(cluster, FIRST)).toBe("Ready");
    expect(await configured()).toContain("postgres_configured 0");
    expect(await rows()).toEqual([]);

    credential = true;
    await fleet.syncDatabase();
    expect(await configured()).toContain("postgres_configured 1");
    expect((await rows()).map((row) => row.id)).toEqual([FIRST]);
  });

  it("never retires live hosts when the fleet could not be read in full", async () => {
    const { cluster, replica, events } = await operator();
    cluster.seed(GPU_HOSTS, gpuHost(FIRST, "firstpod"));
    cluster.seed(GPU_HOSTS, gpuHost(SECOND, "secondpod"));
    const fleet = replica();
    await fleet.syncDatabase();

    // An object the operator cannot parse, then an empty list.
    const unreadable = cluster.read(hostPath(SECOND))!;
    cluster.objects.set(hostPath(SECOND), {
      ...unreadable,
      spec: { ...(unreadable.spec as object), instanceId: "not-a-uuid" },
    });
    await fleet.syncDatabase();
    cluster.remove(hostPath(FIRST));
    cluster.remove(hostPath(SECOND));
    await fleet.syncDatabase();

    expect((await rows()).map((row) => row.retiredAt)).toEqual([null, null]);
    expect(
      events.filter((event) => event.event === "gpu_instance_sync_skipped"),
    ).toHaveLength(2);
  });

  it("drops its per-host series when it stops leading", async () => {
    const { cluster, metrics, replica } = await operator();
    const created = new Date(Date.now() - 10 * 60_000).toISOString();
    cluster.seed(GPU_HOSTS, {
      ...gpuHost(FIRST, "firstpod"),
      metadata: { name: `gpu-${FIRST}`, creationTimestamp: created },
    });
    let time = new Date();
    const fleet = replica(() => time);
    await fleet.reconcile();
    time = new Date(time.getTime() + UNREACHABLE_AFTER_MS);
    await fleet.reconcile();
    const degraded = () =>
      metrics.registry.getSingleMetricAsString(
        "gradiated_gpu_fleet_host_degraded",
      );
    expect(await degraded()).toContain(`instance_id="${FIRST}"`);

    fleet.standDown();
    expect(await degraded()).not.toContain(`instance_id="${FIRST}"`);
  });
});
