import { afterEach, describe, expect, it } from "vitest";

import { DRAIN_FINALIZER } from "../src/drain.js";
import { createFleet, LAST_SEEN_REFRESH_MS } from "../src/fleet.js";
import { GPU_HOSTS, NODES, PODS, SERVICES } from "../src/hosts.js";
import { createMetrics } from "../src/metrics.js";
import { pingHost } from "../src/observe.js";
import { fakeKubernetes } from "./support/kubernetes.js";
import {
  FIRST,
  SECOND,
  fakeHostAgents,
  gpuHost,
  hostPath,
} from "./support/fleet.js";
import { virtualKubeletPod } from "./support/pods.js";

const pod = (name: string, node: string, phase = "Running") => ({
  apiVersion: "v1",
  kind: "Pod",
  metadata: { name, namespace: "gpu-inference" },
  spec: { nodeName: node },
  status: { phase },
});

describe("retiring and leadership", () => {
  let agents: Awaited<ReturnType<typeof fakeHostAgents>>;
  afterEach(() => agents?.close());

  const operator = async (leading = () => true) => {
    const cluster = fakeKubernetes();
    agents = await fakeHostAgents();
    let time = new Date();
    const fleet = createFleet({
      api: cluster.api,
      metrics: createMetrics(),
      ping: (id) => pingHost(id, agents.keys, agents.endpoint, 200),
      sync: () => undefined,
      leading,
      log: () => {},
      now: () => time,
    });
    const advance = (ms: number) => {
      time = new Date(time.getTime() + ms);
    };
    return { cluster, fleet, advance };
  };

  it("holds a deleted host until no pod runs on it, and keeps its Service", async () => {
    const { cluster, fleet } = await operator();
    cluster.seed(GPU_HOSTS, gpuHost(FIRST, "firstpod"));
    await agents.addKey(FIRST);
    cluster.seed(PODS, pod("kev-a", `gpu-${FIRST}`));
    cluster.seed(PODS, pod("done", `gpu-${FIRST}`, "Succeeded"));
    cluster.seed(PODS, pod("elsewhere", `gpu-${SECOND}`));
    cluster.seed(NODES, {
      apiVersion: "v1",
      kind: "Node",
      metadata: { name: `gpu-${FIRST}` },
      spec: {},
    });
    await fleet.reconcile();
    expect(cluster.read(`${NODES}/gpu-${FIRST}`)?.spec).toEqual({});
    expect(cluster.read(hostPath(FIRST))?.metadata.finalizers).toEqual([
      DRAIN_FINALIZER,
    ]);

    cluster.delete(hostPath(FIRST));
    await fleet.reconcile();
    const draining = cluster.read(hostPath(FIRST));
    expect(draining?.metadata.deletionTimestamp).toBeDefined();
    expect(draining?.status).toMatchObject({ phase: "Draining" });
    // Cordoned, so nothing new can be scheduled there before the release.
    expect(cluster.read(`${NODES}/gpu-${FIRST}`)?.spec).toEqual({
      unschedulable: true,
    });
    const cordoned = cluster.calls.findIndex(
      (call) =>
        call.method === "PATCH" && call.path === `${NODES}/gpu-${FIRST}`,
    );
    const counted = cluster.calls.findIndex(
      (call) => call.method === "LIST" && call.path.startsWith(PODS),
    );
    expect(cordoned).toBeGreaterThan(-1);
    expect(cordoned).toBeLessThan(counted);

    cluster.remove(`${PODS}/kev-a`);
    await fleet.reconcile();
    expect(cluster.read(hostPath(FIRST))).toBeUndefined();
    // Retiring never deletes the route; removing it is a separate, explicit step.
    expect(cluster.read(`${SERVICES}/gpu-${FIRST}`)).toBeDefined();
  });

  it("keeps an empty host for one pass after cordoning it, so a late pod is still counted", async () => {
    const { cluster, fleet } = await operator();
    cluster.seed(GPU_HOSTS, gpuHost(FIRST, "firstpod"));
    cluster.seed(NODES, {
      apiVersion: "v1",
      kind: "Node",
      metadata: { name: `gpu-${FIRST}` },
      spec: {},
    });
    await fleet.reconcile();
    cluster.delete(hostPath(FIRST));

    await fleet.reconcile();
    expect(cluster.read(hostPath(FIRST))?.status).toMatchObject({
      phase: "Draining",
    });
    // A pod the scheduler placed just before the cordon.
    cluster.seed(PODS, pod("late", `gpu-${FIRST}`));
    await fleet.reconcile();
    expect(cluster.read(hostPath(FIRST))).toBeDefined();

    cluster.remove(`${PODS}/late`);
    await fleet.reconcile();
    expect(cluster.read(hostPath(FIRST))).toBeUndefined();
  });

  it("holds a deleted host while a pod the virtual kubelet publishes runs on it", async () => {
    const { cluster, fleet } = await operator();
    const name = "deepseek-5867b44cff-x2k9p";
    cluster.seed(GPU_HOSTS, gpuHost(FIRST, "firstpod"));
    cluster.seed(NODES, {
      apiVersion: "v1",
      kind: "Node",
      metadata: { name: `gpu-${FIRST}` },
      spec: {},
    });
    cluster.seed(PODS, virtualKubeletPod("deepseek", name, `gpu-${FIRST}`));
    await fleet.reconcile();
    cluster.delete(hostPath(FIRST));

    for (let pass = 0; pass < 3; pass++) await fleet.reconcile();
    expect(cluster.read(hostPath(FIRST))).toMatchObject({
      metadata: { finalizers: [DRAIN_FINALIZER] },
      status: { phase: "Draining" },
    });

    cluster.remove(`${PODS}/${name}`);
    await fleet.reconcile();
    expect(cluster.read(hostPath(FIRST))).toBeUndefined();
  });

  it("uncordons a returned host it had cordoned, and never a cordon made by hand", async () => {
    const { cluster, fleet } = await operator();
    const node = (id: string, cordonedBy?: string) => ({
      apiVersion: "v1",
      kind: "Node",
      metadata: {
        name: `gpu-${id}`,
        ...(cordonedBy && {
          annotations: { "fleet.gradiated.com/cordoned-by": cordonedBy },
        }),
      },
      spec: { unschedulable: true },
    });
    cluster.seed(GPU_HOSTS, gpuHost(FIRST, "firstpod"));
    cluster.seed(GPU_HOSTS, gpuHost(SECOND, "secondpod"));
    cluster.seed(NODES, node(FIRST, "gpu-fleet"));
    cluster.seed(NODES, node(SECOND));
    await agents.addKey(FIRST);
    await agents.addKey(SECOND);

    await fleet.reconcile();
    const returned = cluster.read(`${NODES}/gpu-${FIRST}`)!;
    expect(returned.spec).toEqual({ unschedulable: false });
    expect(returned.metadata.annotations ?? {}).not.toHaveProperty(
      "fleet.gradiated.com/cordoned-by",
    );
    expect(cluster.read(`${NODES}/gpu-${SECOND}`)?.spec).toEqual({
      unschedulable: true,
    });
  });

  it("keeps a returned host cordoned until it answers as itself", async () => {
    const { cluster, fleet } = await operator();
    cluster.seed(GPU_HOSTS, gpuHost(FIRST, "firstpod"));
    cluster.seed(NODES, {
      apiVersion: "v1",
      kind: "Node",
      metadata: {
        name: `gpu-${FIRST}`,
        annotations: { "fleet.gradiated.com/cordoned-by": "gpu-fleet" },
      },
      spec: { unschedulable: true },
    });
    const cordoned = () =>
      (
        cluster.read(`${NODES}/gpu-${FIRST}`)?.spec as {
          unschedulable: boolean;
        }
      ).unschedulable;

    // No management key, so the agent cannot be reached.
    await fleet.reconcile();
    expect(cordoned()).toBe(true);

    await agents.addKey(FIRST);
    agents.identity.set(FIRST, SECOND);
    await fleet.reconcile();
    expect(cordoned()).toBe(true);

    agents.identity.delete(FIRST);
    await fleet.reconcile();
    expect(cordoned()).toBe(false);
  });

  it("measures an outage from the latest answer, not the last written status", async () => {
    const { cluster, fleet, advance } = await operator();
    cluster.seed(GPU_HOSTS, gpuHost(FIRST, "firstpod"));
    await agents.addKey(FIRST);
    await fleet.reconcile();
    const status = () =>
      cluster.read(hostPath(FIRST))?.status as {
        phase: string;
        observed: { lastSeen: string };
      };
    const firstSeen = Date.parse(status().observed.lastSeen);

    // Answers keep coming, but lastSeen is not rewritten before the refresh.
    advance(4 * 60_000);
    await fleet.reconcile();
    expect(Date.parse(status().observed.lastSeen)).toBe(firstSeen);

    advance(30_000);
    agents.down.add(FIRST);
    await fleet.reconcile();
    expect(status().phase).toBe("Ready");
    // Going silent records when the host last answered.
    expect(Date.parse(status().observed.lastSeen) - firstSeen).toBe(4 * 60_000);

    advance(2 * 60_000);
    await fleet.reconcile();
    expect(
      (cluster.read(hostPath(FIRST))?.status as { phase: string }).phase,
    ).toBe("Degraded");
  });

  it("gives a new leader its own grace period before reporting a host Unreachable", async () => {
    const { cluster, fleet, advance } = await operator();
    // The previous leader last wrote lastSeen four minutes ago; the host has
    // been answering since, but this replica has seen none of it.
    cluster.seed(GPU_HOSTS, {
      ...gpuHost(FIRST, "firstpod"),
      status: {
        phase: "Ready",
        observed: {
          reachable: true,
          lastSeen: new Date(Date.now() - 4 * 60_000).toISOString(),
        },
      },
    });
    const phase = () =>
      (cluster.read(hostPath(FIRST))?.status as { phase: string }).phase;

    // No management key, so every ping from this replica fails.
    await fleet.reconcile();
    expect(phase()).toBe("Ready");
    advance(90_000);
    await fleet.reconcile();
    expect(phase()).toBe("Ready");
    advance(30_000);
    await fleet.reconcile();
    expect(phase()).toBe("Degraded");

    // Losing and retaking the lease starts a fresh grace period.
    fleet.standDown();
    await agents.addKey(FIRST);
    await fleet.reconcile();
    expect(phase()).toBe("Ready");
    agents.down.add(FIRST);
    fleet.standDown();
    advance(10 * 60_000);
    await fleet.reconcile();
    expect(phase()).toBe("Ready");
  });

  it("reports a malformed credential as a sync failure instead of stopping", async () => {
    const cluster = fakeKubernetes();
    cluster.seed(GPU_HOSTS, gpuHost(FIRST, "firstpod"));
    const events: Record<string, unknown>[] = [];
    const fleet = createFleet({
      api: cluster.api,
      metrics: createMetrics(),
      ping: async () => ({ reachable: false, error: "down", silent: true }),
      sync: () => {
        throw new TypeError("Invalid URL");
      },
      leading: () => true,
      log: (event) => events.push(event),
    });

    await expect(fleet.syncDatabase()).resolves.toBeUndefined();
    expect(events).toContainEqual({
      event: "gpu_instance_sync_failed",
      error: "Invalid URL",
    });
  });

  it("never gives a Service an owner, so no deletion can cascade to it", async () => {
    const { cluster, fleet } = await operator();
    for (const [id, podId] of [
      [FIRST, "firstpod"],
      [SECOND, "secondpod"],
    ] as const)
      cluster.seed(GPU_HOSTS, gpuHost(id, podId));
    await fleet.reconcile();
    cluster.delete(hostPath(FIRST));
    await fleet.reconcile();
    cluster.remove(hostPath(SECOND));
    await fleet.reconcile();

    const services = await cluster.api.list(SERVICES);
    expect(services).toHaveLength(2);
    for (const service of services)
      expect((service as { metadata: object }).metadata).not.toHaveProperty(
        "ownerReferences",
      );
  });

  it("stops writing as soon as the lease is no longer held", async () => {
    let held = true;
    const { cluster, fleet } = await operator(() => held);
    cluster.seed(GPU_HOSTS, gpuHost(FIRST, "firstpod"));
    held = false;
    const before = cluster.calls.length;

    await fleet.reconcile();
    expect(
      cluster.calls
        .slice(before)
        .filter((call) => ["POST", "PUT", "PATCH"].includes(call.method)),
    ).toEqual([]);
    expect(cluster.read(`${SERVICES}/gpu-${FIRST}`)).toBeUndefined();
  });

  it("reports a GpuHost it cannot read as Degraded and keeps reconciling the rest", async () => {
    const { cluster, fleet } = await operator();
    cluster.seed(GPU_HOSTS, gpuHost(FIRST, "firstpod"));
    const broken = gpuHost(SECOND, "secondpod");
    cluster.seed(GPU_HOSTS, {
      ...broken,
      spec: { ...broken.spec, instanceId: "not-a-uuid" },
    });

    await fleet.reconcile();
    expect(cluster.read(hostPath(SECOND))?.status).toMatchObject({
      phase: "Degraded",
      conditions: [expect.objectContaining({ reason: "InvalidSpec" })],
    });
    expect(cluster.read(`${SERVICES}/gpu-${FIRST}`)).toBeDefined();

    const before = cluster.calls.length;
    await fleet.reconcile();
    expect(
      cluster.calls
        .slice(before)
        .filter((call) => call.path === `${hostPath(SECOND)}/status`),
    ).toEqual([]);
  });

  it("rewrites status for lastSeen alone only after the refresh interval", async () => {
    const { cluster, fleet, advance } = await operator();
    cluster.seed(GPU_HOSTS, gpuHost(FIRST, "firstpod"));
    await agents.addKey(FIRST);
    await fleet.reconcile();
    const written = () =>
      (
        cluster.read(hostPath(FIRST))?.status as {
          observed: { lastSeen: string };
        }
      ).observed.lastSeen;
    const first = written();

    advance(60_000);
    await fleet.reconcile();
    expect(written()).toBe(first);

    advance(LAST_SEEN_REFRESH_MS);
    await fleet.reconcile();
    expect(written()).not.toBe(first);
  });
});
