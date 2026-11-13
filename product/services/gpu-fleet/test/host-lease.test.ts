import { describe, expect, it } from "vitest";

import { createCluster, PAUSED_REPLICAS } from "../src/cluster.js";
import {
  GPU_HOSTS,
  LEASE_ANNOTATION,
  NODES,
  PODS,
  RETRY_ANNOTATION,
  ROLLOUTS,
  SCALED_OBJECTS,
} from "../src/hosts.js";
import { createMetrics, type Metrics } from "../src/metrics.js";
import type { Pins } from "../src/pins.js";
import { createRollouts } from "../src/rollout.js";
import {
  NEW_BUNDLE,
  NEW_IMAGE,
  OLD_BUNDLE,
  OLD_IMAGE,
  pins,
  simulateFleet,
  type Simulation,
} from "./support/simulation.js";

const SPARE = "01a0f19d-1ff3-7613-8cbf-81b693c0f0d4";
const FIRST = "01a0fbf7-5276-700b-903b-7e04da150ed6";
const SECOND = "01a0fbf8-06fc-7658-96e1-ae72f7dba135";
const HOUR = 60 * 60_000;
const CURRENT = pins(OLD_IMAGE, OLD_BUNDLE);

// Each pass uses a fresh engine, so every step resumes from GpuHost status alone.
const run = async (
  fleet: Simulation,
  pinned: Pins,
  until: () => boolean,
  metrics: Metrics = createMetrics(),
  passes = 400,
) => {
  for (let pass = 0; pass < passes && !until(); pass++) {
    const rollouts = createRollouts({
      api: fleet.kube.api,
      cluster: createCluster(fleet.kube.api, () => undefined),
      ping: fleet.ping,
      pins: async () => pinned,
      enrollment: async () => fleet.enrollment,
      modelStatuses: async () => new Map(),
      mode: "act",
      leading: () => true,
      identity: "gpu-fleet-a",
      log: () => undefined,
      metrics,
      now: fleet.now,
      limits: { soakFor: 60_000, unschedulable: 120_000 },
    });
    await fleet.observe();
    await rollouts.pass().catch(() => undefined);
    fleet.tick();
  }
};

const kevFleet = (
  spare: {
    volumeInGb?: number;
    hasAttachedVolumes?: boolean;
    gpus?: number;
  } = {},
) => {
  const fleet = simulateFleet(
    [
      { instanceId: SPARE, podId: "yzno396wdsidu4", gpus: 1, ...spare },
      { instanceId: FIRST, podId: "zhimpngvqyotuj", gpus: 1 },
      { instanceId: SECOND, podId: "dv31b4wrd2yc8n", gpus: 1 },
    ],
    [{ name: "kev", gpus: 1, replicas: 2 }],
  );
  fleet.place("kev", FIRST);
  fleet.place("kev", SECOND);
  return fleet;
};

const request = (fleet: Simulation, hours = 4) => ({
  holder: "research-agent",
  purpose: "SFT sweep on private data",
  until: new Date(fleet.now().getTime() + hours * HOUR).toISOString(),
});

// KEDA asks for more replicas than the floor, as demand would.
const scale = (fleet: Simulation, model: string, replicas: number) => {
  fleet.kube.objects.get(`${ROLLOUTS}/${model}`)!.spec = { replicas };
  (
    fleet.kube.objects.get(`${SCALED_OBJECTS}/${model}`)!.spec as {
      minReplicaCount: number;
    }
  ).minReplicaCount = replicas;
};

const failed = (fleet: Simulation, id: string) => () =>
  fleet.host(id).status?.rollout?.result === "Failed";

const leased = (fleet: Simulation, id: string) => () =>
  fleet.host(id).status?.lease !== undefined;
const returned = (fleet: Simulation, id: string) => () =>
  fleet.host(id).status?.rollout?.kind === "return" &&
  fleet.host(id).status?.rollout?.result === "Succeeded";

const requested = (fleet: Simulation, id: string) =>
  fleet.host(id).metadata.annotations?.[LEASE_ANNOTATION] !== undefined;

// The operator records why a lease ended and removes its request.
const expectEnded = (fleet: Simulation, id: string, reason: string) => {
  expect(fleet.host(id).status?.rollout).toMatchObject({
    kind: "lease",
    result: "Failed",
  });
  expect(fleet.host(id).status?.rollout?.lastError).toContain(reason);
  expect(requested(fleet, id)).toBe(false);
};

const expectInPool = (fleet: Simulation, id: string) => {
  expect(fleet.host(id).status?.lease).toBeUndefined();
  expect(fleet.node(id).spec?.unschedulable).toBeFalsy();
};

describe("host leases", () => {
  it("moves a host's replicas, holds it out of the pool, and wipes it when handed back", async () => {
    const fleet = kevFleet();
    fleet.annotateLease(FIRST, request(fleet));

    await run(fleet, CURRENT, leased(fleet, FIRST));

    expect(fleet.host(FIRST).status).toMatchObject({
      lease: { holder: "research-agent", purpose: "SFT sweep on private data" },
      rollout: { kind: "lease", result: "Succeeded" },
    });
    expect(fleet.node(FIRST).spec?.unschedulable).toBe(true);
    expect(fleet.podsOn(FIRST)).toEqual([]);
    expect(fleet.ready("kev")).toBe(2);
    expect(
      fleet.scaledObject("kev").metadata.annotations?.[PAUSED_REPLICAS],
    ).toBeUndefined();
    expect(fleet.sim(FIRST).resets).toBe(0);

    await run(fleet, CURRENT, () => false, createMetrics(), 30);

    expect(fleet.host(FIRST).status?.plan).toContain(
      "Leased to research-agent until",
    );
    expect(fleet.node(FIRST).spec?.unschedulable).toBe(true);
    expect(fleet.sim(FIRST).resets).toBe(0);

    fleet.annotateLease(FIRST);
    await run(fleet, CURRENT, returned(fleet, FIRST));

    // The return re-imaged the pod, which recreates its container disk.
    expect(fleet.sim(FIRST)).toMatchObject({
      image: OLD_IMAGE,
      state: "enrolled",
      resets: 1,
    });
    expectInPool(fleet, FIRST);
    expect([...fleet.keys.values()].every((key) => key.revoked)).toBe(true);
    expect(fleet.violations).toEqual([]);
  });

  it("returns a host by itself when its lease expires", async () => {
    const fleet = kevFleet();
    fleet.annotateLease(SPARE, request(fleet, 1));
    await run(fleet, CURRENT, leased(fleet, SPARE));

    fleet.advance(HOUR);
    await run(fleet, CURRENT, returned(fleet, SPARE));

    expect(fleet.host(SPARE).status?.rollout?.lastError).toBeUndefined();
    expect(fleet.sim(SPARE).resets).toBe(1);
    expectInPool(fleet, SPARE);
  });

  it("cordons a leased host again when someone lifts its cordon", async () => {
    const fleet = kevFleet();
    fleet.annotateLease(SPARE, request(fleet));
    await run(fleet, CURRENT, leased(fleet, SPARE));

    const node = fleet.kube.objects.get(`${NODES}/gpu-${SPARE}`)!;
    node.metadata.annotations = {};
    node.spec = {};
    await run(fleet, CURRENT, () => false, createMetrics(), 2);

    expect(fleet.node(SPARE).spec?.unschedulable).toBe(true);
    expect(fleet.host(SPARE).status?.lease).toBeDefined();
    expect(fleet.podsOn(SPARE)).toEqual([]);
  });

  it("keeps a returning host cordoned until the return uncordons it", async () => {
    const fleet = kevFleet();
    fleet.annotateLease(SPARE, request(fleet));
    await run(fleet, CURRENT, leased(fleet, SPARE));

    fleet.annotateLease(SPARE);
    await run(
      fleet,
      CURRENT,
      () => fleet.host(SPARE).status?.rollout?.step === "Join",
    );
    const node = fleet.kube.objects.get(`${NODES}/gpu-${SPARE}`)!;
    node.metadata.annotations = {};
    node.spec = {};
    await run(fleet, CURRENT, () => false, createMetrics(), 1);
    expect(fleet.node(SPARE).spec?.unschedulable).toBe(true);

    await run(fleet, CURRENT, returned(fleet, SPARE));
    expectInPool(fleet, SPARE);
  });

  it("reports the time a leased host is due back", async () => {
    const fleet = kevFleet();
    const metrics = createMetrics();
    const lease = request(fleet);
    fleet.annotateLease(SPARE, lease);
    await run(fleet, CURRENT, leased(fleet, SPARE), metrics);
    await run(fleet, CURRENT, () => false, metrics, 1);

    expect(
      await metrics.registry.getSingleMetricAsString(
        "gradiated_gpu_fleet_lease_until_timestamp_seconds",
      ),
    ).toContain(
      `{instance_id="${SPARE}",holder="research-agent"} ${Date.parse(lease.until) / 1000}`,
    );
  });

  it.each([
    [
      "the host is reserved",
      (fleet: Simulation) => {
        const host = fleet.kube.objects.get(
          `${GPU_HOSTS}/gpu-${SPARE}`,
        ) as unknown as { spec: Record<string, unknown> };
        host.spec.extraTaints = [
          {
            key: "gradiated.com/reserved",
            value: "kimi-k31",
            effect: "NoSchedule",
          },
        ];
        fleet.annotateLease(SPARE, request(fleet));
      },
    ],
    [
      "the lease annotation is invalid",
      (fleet: Simulation) =>
        fleet.annotateLease(SPARE, { ...request(fleet), until: "tomorrow" }),
    ],
    [
      "the lease ended",
      (fleet: Simulation) => fleet.annotateLease(SPARE, request(fleet, -1)),
    ],
    [
      "the node is already cordoned",
      (fleet: Simulation) => {
        fleet.cordonByHand(SPARE);
        fleet.annotateLease(SPARE, request(fleet));
      },
    ],
  ])(
    "refuses a lease when %s, before touching the host",
    async (reason, prepare) => {
      const fleet = kevFleet();
      prepare(fleet);

      await run(fleet, CURRENT, failed(fleet, SPARE));

      expectEnded(fleet, SPARE, `Not leased: ${reason}`);
      expect(fleet.host(SPARE).status?.lease).toBeUndefined();
      // The hand cordon stays the person's to lift.
      expect(fleet.node(SPARE).spec?.unschedulable ?? false).toBe(
        reason === "the node is already cordoned",
      );
    },
  );

  it("refuses a lease at once on a host whose re-image is blocked for room", async () => {
    const fleet = simulateFleet(
      [
        { instanceId: FIRST, podId: "zhimpngvqyotuj", gpus: 1 },
        { instanceId: SECOND, podId: "dv31b4wrd2yc8n", gpus: 1 },
      ],
      [{ name: "kev", gpus: 1, replicas: 2 }],
    );
    fleet.place("kev", FIRST);
    fleet.place("kev", SECOND);
    const updated = pins(NEW_IMAGE, NEW_BUNDLE);
    const blockedHost = () =>
      [FIRST, SECOND].find(
        (id) => fleet.host(id).status?.rollout?.result === "Blocked",
      );
    await run(fleet, updated, () => blockedHost() !== undefined);
    const id = blockedHost()!;

    fleet.annotateLease(id, request(fleet));
    await run(fleet, updated, failed(fleet, id), createMetrics(), 20);

    expectEnded(fleet, id, "Not leased: its reimage is blocked");
    expectInPool(fleet, id);
  });

  it("does not hand over a host whose drain outlasted the lease", async () => {
    const fleet = kevFleet();
    fleet.annotateLease(FIRST, request(fleet, 1 / 120));

    await run(fleet, CURRENT, failed(fleet, FIRST));

    expectEnded(fleet, FIRST, "before the host was drained");
    expect(fleet.host(FIRST).status?.lease).toBeUndefined();
    expectInPool(fleet, FIRST);
    expect(fleet.ready("kev")).toBe(2);
  });

  it("refuses a lease at once when the operator only observes", async () => {
    const fleet = kevFleet();
    fleet.annotateLease(SPARE, request(fleet));

    for (let pass = 0; pass < 5 && !failed(fleet, SPARE)(); pass++) {
      const rollouts = createRollouts({
        api: fleet.kube.api,
        cluster: createCluster(fleet.kube.api, () => undefined),
        ping: fleet.ping,
        pins: async () => CURRENT,
        enrollment: async () => fleet.enrollment,
        modelStatuses: async () => new Map(),
        mode: "observe",
        leading: () => true,
        identity: "gpu-fleet-a",
        log: () => undefined,
        metrics: createMetrics(),
        now: fleet.now,
      });
      await fleet.observe();
      await rollouts.pass();
      fleet.tick();
    }

    expectEnded(fleet, SPARE, "Not leased: the operator is in observe mode");
    expectInPool(fleet, SPARE);
  });

  it.each([{ volumeInGb: 100 }, { hasAttachedVolumes: true }])(
    "refuses a host whose RunPod storage a re-image would not wipe (%j)",
    async (storage) => {
      const fleet = kevFleet(storage);
      fleet.annotateLease(SPARE, request(fleet));

      await run(fleet, CURRENT, failed(fleet, SPARE));

      expectEnded(fleet, SPARE, "Not leased: the pod has a RunPod volume");
      expectInPool(fleet, SPARE);
    },
  );

  it("fails a lease with no room for the host's replicas at once, keeps it in the pool and does not retry it", async () => {
    const fleet = simulateFleet(
      [
        { instanceId: FIRST, podId: "zhimpngvqyotuj", gpus: 1 },
        { instanceId: SECOND, podId: "dv31b4wrd2yc8n", gpus: 1 },
      ],
      [{ name: "kev", gpus: 1, replicas: 2 }],
    );
    fleet.place("kev", FIRST);
    fleet.place("kev", SECOND);
    fleet.annotateLease(FIRST, request(fleet));

    await run(fleet, CURRENT, failed(fleet, FIRST));
    const attempt = fleet.host(FIRST).status?.rollout;
    expect(attempt).toMatchObject({ kind: "lease", step: "Cordon" });
    expectEnded(fleet, FIRST, "No capacity for a replacement kev replica");
    expectInPool(fleet, FIRST);

    await run(fleet, CURRENT, () => false, createMetrics(), 30);

    expect(fleet.host(FIRST).status?.rollout).toEqual(attempt);
    expect(fleet.ready("kev")).toBe(2);
    expect(fleet.violations).toEqual([]);
  });

  it("fails a lease while a training job runs, then leases the host on a new request", async () => {
    const fleet = kevFleet();
    const job = fleet.placeTraining(SPARE);
    fleet.annotateLease(SPARE, request(fleet));

    await run(fleet, CURRENT, failed(fleet, SPARE));

    expectEnded(fleet, SPARE, "A training job runs on the host");
    expectInPool(fleet, SPARE);

    fleet.kube.objects.delete(`${PODS}/${job}`);
    fleet.annotateLease(SPARE, request(fleet, 5));
    await run(fleet, CURRENT, leased(fleet, SPARE));

    expect(fleet.node(SPARE).spec?.unschedulable).toBe(true);
  });

  it("does not hold up the fleet's rollouts when a lease fails, even with the retry annotation set", async () => {
    const fleet = kevFleet({ gpus: 2 });
    const job = fleet.placeTraining(SPARE);
    fleet.annotateLease(SPARE, request(fleet));
    await run(fleet, CURRENT, failed(fleet, SPARE));
    const host = fleet.kube.objects.get(`${GPU_HOSTS}/gpu-${SPARE}`)!;
    host.metadata.annotations = {
      ...(host.metadata.annotations as Record<string, string>),
      [RETRY_ANNOTATION]: "1",
    };

    // kev moves onto the spare's free GPU while the job keeps the other.
    const updated = pins(NEW_IMAGE, NEW_BUNDLE);
    await run(fleet, updated, () =>
      [FIRST, SECOND].every(
        (id) =>
          fleet.sim(id).image === NEW_IMAGE &&
          fleet.host(id).status?.rollout?.result === "Succeeded",
      ),
    );
    for (const id of [FIRST, SECOND]) expectInPool(fleet, id);

    // With its request gone, the spare is planned as any host again.
    fleet.kube.objects.delete(`${PODS}/${job}`);
    await run(fleet, updated, () => fleet.sim(SPARE).image === NEW_IMAGE);
    expect(fleet.violations).toEqual([]);
  });

  it("re-images a host whose lease expired when the pins change", async () => {
    const fleet = kevFleet();
    fleet.annotateLease(SPARE, request(fleet, 1));
    await run(fleet, CURRENT, leased(fleet, SPARE));
    fleet.advance(HOUR);
    await run(fleet, CURRENT, returned(fleet, SPARE));
    expect(requested(fleet, SPARE)).toBe(false);

    const updated = pins(NEW_IMAGE, NEW_BUNDLE);
    await run(fleet, updated, () =>
      [SPARE, FIRST, SECOND].every(
        (id) =>
          fleet.sim(id).image === NEW_IMAGE &&
          fleet.host(id).status?.rollout?.result === "Succeeded",
      ),
    );
    expect(fleet.sim(SPARE).resets).toBe(2);
  });

  it("tries a default request once after a lease that was not preemptible", async () => {
    const fleet = kevFleet();
    fleet.annotateLease(SPARE, { ...request(fleet, 1), preemptible: false });
    await run(fleet, CURRENT, leased(fleet, SPARE));
    fleet.advance(HOUR);
    await run(fleet, CURRENT, returned(fleet, SPARE));

    fleet.placeTraining(SPARE);
    fleet.annotateLease(SPARE, request(fleet));
    await run(fleet, CURRENT, failed(fleet, SPARE));
    const attempt = fleet.host(SPARE).status?.rollout;
    await run(fleet, CURRENT, () => false, createMetrics(), 20);

    expect(fleet.host(SPARE).status?.rollout).toEqual(attempt);
    expect(requested(fleet, SPARE)).toBe(false);
  });

  it("wipes a leased host before it goes to a new holder", async () => {
    const fleet = kevFleet();
    fleet.annotateLease(SPARE, request(fleet));
    await run(fleet, CURRENT, leased(fleet, SPARE));

    fleet.annotateLease(SPARE, { ...request(fleet), holder: "someone-else" });
    await run(
      fleet,
      CURRENT,
      () => fleet.host(SPARE).status?.lease?.holder === "someone-else",
    );

    expect(fleet.sim(SPARE).resets).toBe(1);
    expect(fleet.node(SPARE).spec?.unschedulable).toBe(true);
  });

  it("hands a preemptible lease back when a model replica has nowhere else to run", async () => {
    const fleet = kevFleet();
    fleet.annotateLease(SPARE, request(fleet, 12));
    await run(fleet, CURRENT, leased(fleet, SPARE));

    scale(fleet, "kev", 3);
    await run(fleet, CURRENT, returned(fleet, SPARE));

    expect(fleet.sim(SPARE).resets).toBe(1);
    expect(fleet.host(SPARE).status?.rollout?.lease?.holder).toBe(
      "research-agent",
    );
    expectInPool(fleet, SPARE);
    await run(fleet, CURRENT, () => fleet.ready("kev") === 3);
    expect(fleet.podsOn(SPARE)).toHaveLength(1);

    // The holder's request is removed, so it is not leased again.
    expect(requested(fleet, SPARE)).toBe(false);
    await run(fleet, CURRENT, () => false, createMetrics(), 20);
    expect(fleet.host(SPARE).status?.lease).toBeUndefined();
  });

  it("keeps a lease marked not preemptible however long a replica waits", async () => {
    const fleet = kevFleet();
    fleet.annotateLease(SPARE, { ...request(fleet, 12), preemptible: false });
    await run(fleet, CURRENT, leased(fleet, SPARE));

    scale(fleet, "kev", 3);
    await run(fleet, CURRENT, () => false, createMetrics(), 60);

    expect(fleet.host(SPARE).status?.lease).toBeDefined();
    expect(fleet.host(SPARE).status?.rollout?.kind).toBe("lease");
    expect(fleet.sim(SPARE).resets).toBe(0);
    expect(fleet.ready("kev")).toBe(2);
  });

  it("keeps a leased host cordoned when its return cannot run, and reports it due since the return began", async () => {
    const fleet = kevFleet();
    const metrics = createMetrics();
    fleet.annotateLease(SPARE, request(fleet));
    await run(fleet, CURRENT, leased(fleet, SPARE), metrics);

    fleet.place("kev", SPARE);
    fleet.annotateLease(SPARE);
    await run(
      fleet,
      CURRENT,
      () => fleet.host(SPARE).status?.rollout?.result === "Failed",
      metrics,
    );
    fleet.advance(HOUR);
    await run(fleet, CURRENT, () => false, metrics, 2);

    expect(
      await metrics.registry.getSingleMetricAsString(
        "gradiated_gpu_fleet_lease_until_timestamp_seconds",
      ),
    ).toContain(
      `{instance_id="${SPARE}",holder="research-agent"} ${Date.parse(fleet.host(SPARE).status!.rollout!.startedAt) / 1000}`,
    );

    expect(fleet.host(SPARE).status).toMatchObject({
      lease: { holder: "research-agent" },
      rollout: {
        kind: "return",
        lastError: "A model pod runs on the leased host",
      },
    });
    expect(fleet.node(SPARE).spec?.unschedulable).toBe(true);
    expect(fleet.sim(SPARE).resets).toBe(0);
  });

  it("does not wipe a returning host while any pod runs on it", async () => {
    const fleet = kevFleet();
    fleet.annotateLease(SPARE, request(fleet));
    await run(fleet, CURRENT, leased(fleet, SPARE));

    fleet.placeTraining(SPARE);
    const job = fleet.podsOn(SPARE)[0]!;
    delete job.metadata.annotations["gradiated.com/workload-kind"];
    fleet.annotateLease(SPARE);
    await run(fleet, CURRENT, failed(fleet, SPARE));

    expect(fleet.host(SPARE).status?.rollout).toMatchObject({
      kind: "return",
      lastError: "A pod runs on the leased host",
    });
    expect(fleet.sim(SPARE).resets).toBe(0);
    expect(fleet.node(SPARE).spec?.unschedulable).toBe(true);
  });

  it("leaves a leased host alone during a fleet rollout, returns it even while that rollout waits for room, and returns it on the new pins", async () => {
    const fleet = kevFleet();
    fleet.annotateLease(SPARE, request(fleet, 12));
    await run(fleet, CURRENT, leased(fleet, SPARE));

    // With the spare leased, kev has no room to move, so the rollout blocks.
    const updated = pins(NEW_IMAGE, NEW_BUNDLE);
    await run(
      fleet,
      updated,
      () => fleet.host(FIRST).status?.rollout?.result === "Blocked",
    );

    expect(fleet.sim(SPARE)).toMatchObject({ image: OLD_IMAGE, resets: 0 });
    expect(fleet.host(SPARE).status?.lease).toBeDefined();

    fleet.annotateLease(SPARE);
    await run(fleet, updated, () =>
      [SPARE, FIRST, SECOND].every(
        (id) =>
          fleet.sim(id).image === NEW_IMAGE &&
          fleet.host(id).status?.rollout?.result === "Succeeded",
      ),
    );

    expect(fleet.host(SPARE).status?.rollout?.kind).toBe("return");
    expect(fleet.sim(SPARE)).toMatchObject({ state: "enrolled", resets: 1 });
    for (const id of [SPARE, FIRST, SECOND]) expectInPool(fleet, id);
    expect(fleet.ready("kev")).toBe(2);
    expect(fleet.violations).toEqual([]);
  });
});

describe("fleet metrics for the GPU fleet dashboard", () => {
  const value = async (metrics: Metrics, name: string, labels: string) => {
    const text = await metrics.registry.getSingleMetricAsString(name);
    const line = text
      .split("\n")
      .find((row) => row.startsWith(`${name}{${labels}}`));
    return line === undefined ? undefined : Number(line.split(" ").pop());
  };
  const state = async (metrics: Metrics, id: string) => {
    const text = await metrics.registry.getSingleMetricAsString(
      "gradiated_gpu_fleet_host_gpus",
    );
    return text.match(
      new RegExp(`instance_id="${id}",gpu_product="[^"]+",state="([a-z_]+)"`),
    )?.[1];
  };

  it("reports each host's state, the GPUs its workloads use, a lease's holder and purpose, and how it ended", async () => {
    const fleet = kevFleet();
    const metrics = createMetrics();
    await run(fleet, CURRENT, () => false, metrics, 3);

    expect(await state(metrics, SPARE)).toBe("in_pool");
    expect(await state(metrics, FIRST)).toBe("in_pool");
    expect(
      await value(
        metrics,
        "gradiated_gpu_fleet_host_workload_gpus",
        `instance_id="${FIRST}",workload="kev",kind="serving"`,
      ),
    ).toBe(1);
    expect(
      await value(
        metrics,
        "gradiated_gpu_fleet_host_workload_gpus",
        `instance_id="${SPARE}",workload="kev",kind="serving"`,
      ),
    ).toBeUndefined();

    const lease = request(fleet);
    fleet.annotateLease(FIRST, lease);
    await run(
      fleet,
      CURRENT,
      () => fleet.host(FIRST).status?.rollout?.kind === "lease",
      metrics,
    );
    await run(fleet, CURRENT, () => false, metrics, 1);
    expect(await state(metrics, FIRST)).toBe("leasing");

    await run(fleet, CURRENT, leased(fleet, FIRST), metrics);
    await run(fleet, CURRENT, () => false, metrics, 1);
    expect(await state(metrics, FIRST)).toBe("leased");
    // Its replica moved to the spare host.
    expect(
      await value(
        metrics,
        "gradiated_gpu_fleet_host_workload_gpus",
        `instance_id="${SPARE}",workload="kev",kind="serving"`,
      ),
    ).toBe(1);
    const since = Date.parse(fleet.host(FIRST).status!.lease!.since) / 1000;
    expect(
      await value(
        metrics,
        "gradiated_gpu_fleet_lease_started_timestamp_seconds",
        `instance_id="${FIRST}",holder="research-agent",purpose="SFT sweep on private data",preemptible="true"`,
      ),
    ).toBe(since);
    expect(
      await value(
        metrics,
        "gradiated_gpu_fleet_lease_events_total",
        `event="granted"`,
      ),
    ).toBe(1);

    fleet.annotateLease(FIRST);
    await run(
      fleet,
      CURRENT,
      () => fleet.host(FIRST).status?.rollout?.kind === "return",
      metrics,
    );
    await run(fleet, CURRENT, () => false, metrics, 1);
    expect(await state(metrics, FIRST)).toBe("returning");

    await run(fleet, CURRENT, returned(fleet, FIRST), metrics);
    await run(fleet, CURRENT, () => false, metrics, 1);
    expect(
      await value(
        metrics,
        "gradiated_gpu_fleet_lease_events_total",
        `event="released"`,
      ),
    ).toBe(1);
    expect(
      await value(
        metrics,
        "gradiated_gpu_fleet_lease_started_timestamp_seconds",
        `instance_id="${FIRST}",holder="research-agent",purpose="SFT sweep on private data",preemptible="true"`,
      ),
    ).toBeUndefined();
  });

  it("counts an expired, a preempted and a refused lease", async () => {
    const expiring = kevFleet();
    const metrics = createMetrics();
    expiring.annotateLease(SPARE, request(expiring, 1));
    await run(expiring, CURRENT, leased(expiring, SPARE), metrics);
    expiring.advance(HOUR);
    await run(expiring, CURRENT, returned(expiring, SPARE), metrics);
    expect(
      await value(
        metrics,
        "gradiated_gpu_fleet_lease_events_total",
        `event="expired"`,
      ),
    ).toBe(1);

    const wanted = kevFleet();
    wanted.annotateLease(SPARE, request(wanted, 12));
    await run(wanted, CURRENT, leased(wanted, SPARE), metrics);
    scale(wanted, "kev", 3);
    await run(wanted, CURRENT, returned(wanted, SPARE), metrics);
    expect(
      await value(
        metrics,
        "gradiated_gpu_fleet_lease_events_total",
        `event="preempted"`,
      ),
    ).toBe(1);

    const refused = kevFleet();
    refused.annotateLease(SPARE, { ...request(refused), until: "tomorrow" });
    await run(refused, CURRENT, failed(refused, SPARE), metrics);
    expect(
      await value(
        metrics,
        "gradiated_gpu_fleet_lease_events_total",
        `event="failed"`,
      ),
    ).toBe(1);
  });
});
