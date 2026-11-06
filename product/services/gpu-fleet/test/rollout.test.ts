import { describe, expect, it } from "vitest";

import {
  clusterPod,
  createCluster,
  PAUSED_REPLICAS,
  ROLLOUT_CORDON,
} from "../src/cluster.js";
import { CORDONED_BY } from "../src/drain.js";
import type { Enrollment } from "../src/enroll.js";
import {
  GPU_HOSTS,
  NODES,
  PODS,
  RETRY_ANNOTATION,
  type Rollout,
} from "../src/hosts.js";
import type { Kubernetes } from "../src/kubernetes.js";
import { createMetrics, type Metrics } from "../src/metrics.js";
import type { Pins } from "../src/pins.js";
import { createRollouts, type RolloutDependencies } from "../src/rollout.js";
import {
  NEW_BUNDLE,
  NEW_IMAGE,
  OLD_BUNDLE,
  OLD_IMAGE,
  pins,
  simulateFleet,
  type Simulation,
} from "./support/simulation.js";
import { virtualKubeletPod } from "./support/pods.js";

const SPARE = "01a0f19d-1ff3-7613-8cbf-81b693c0f0d4";
const FIRST = "01a0fbf7-5276-700b-903b-7e04da150ed6";
const SECOND = "01a0fbf8-06fc-7658-96e1-ae72f7dba135";
const HOSTS = [SPARE, FIRST, SECOND];

const LIMITS = { soakFor: 60_000, unschedulable: 120_000 };

const engine = (
  fleet: Simulation,
  pinned: Pins,
  overrides: Partial<RolloutDependencies> = {},
) => {
  const events: Record<string, unknown>[] = [];
  const rollouts = createRollouts({
    api: fleet.kube.api,
    cluster: createCluster(fleet.kube.api, (event) => events.push(event)),
    ping: fleet.ping,
    pins: async () => pinned,
    enrollment: async () => fleet.enrollment,
    modelStatuses: async () => new Map(),
    mode: "act",
    leading: () => true,
    identity: "gpu-fleet-a",
    log: (event) => events.push(event),
    metrics: createMetrics(),
    now: fleet.now,
    limits: LIMITS,
    ...overrides,
  });
  return { rollouts, events };
};

// Each pass uses a fresh engine, so every step must resume from GpuHost status
// alone, as after an operator restart or a change of leader.
const run = async (
  fleet: Simulation,
  pinned: Pins,
  until: () => boolean,
  overrides: Partial<RolloutDependencies> = {},
  passes = 400,
) => {
  const events: Record<string, unknown>[] = [];
  for (let pass = 0; pass < passes && !until(); pass++) {
    const { rollouts, events: passEvents } = engine(fleet, pinned, overrides);
    await fleet.observe();
    // As in main.ts, a failed pass is logged and the next one tries again.
    await rollouts.pass().catch((error: Error) => {
      if (error.message === "The lease was lost") throw error;
      events.push({ event: "pass_failed", error: error.message });
    });
    events.push(...passEvents);
    fleet.tick();
  }
  return events;
};

const kevFleet = () => {
  const fleet = simulateFleet(
    [
      { instanceId: SPARE, podId: "yzno396wdsidu4", gpus: 1 },
      { instanceId: FIRST, podId: "zhimpngvqyotuj", gpus: 1 },
      { instanceId: SECOND, podId: "dv31b4wrd2yc8n", gpus: 1 },
    ],
    [{ name: "kev", gpus: 1, replicas: 2 }],
  );
  fleet.place("kev", FIRST);
  fleet.place("kev", SECOND);
  return fleet;
};

const rollout = (fleet: Simulation, id: string) =>
  fleet.host(id).status?.rollout;
const allSucceeded = (fleet: Simulation) => () =>
  HOSTS.every((id) => rollout(fleet, id)?.result === "Succeeded");
const started = (events: Record<string, unknown>[]) =>
  events
    .filter((event) => event.event === "gpu_rollout_started")
    .map((event) => event.instance_id);

const expectRolledOut = (fleet: Simulation) => {
  for (const id of HOSTS) {
    expect(fleet.sim(id)).toMatchObject({
      image: NEW_IMAGE,
      bundle: NEW_BUNDLE,
      state: "enrolled",
      resets: 1,
    });
    expect(fleet.node(id).spec?.unschedulable).toBeFalsy();
    expect(fleet.node(id).metadata.annotations?.[CORDONED_BY]).toBeUndefined();
  }
  expect(fleet.violations).toEqual([]);
  expect(fleet.ready("kev")).toBe(2);
  expect(
    fleet.scaledObject("kev").metadata.annotations?.[PAUSED_REPLICAS],
  ).toBeUndefined();
  // Every key minted along the way is revoked, used or not.
  expect([...fleet.keys.values()].every((key) => key.revoked)).toBe(true);
  const names = [...fleet.devices.values()]
    .filter((device) => device.connectedToControl)
    .map((device) => device.name)
    .sort();
  expect(names).toEqual(
    HOSTS.map((id) => `gpu-${id}.tail186117.ts.net`).sort(),
  );
};

describe("rolling re-image", () => {
  it("re-images the spare first, moves each host's pods before touching it, and never drops a replica", async () => {
    const fleet = kevFleet();

    const events = await run(
      fleet,
      pins(NEW_IMAGE, NEW_BUNDLE),
      allSucceeded(fleet),
    );

    expect(started(events)).toEqual([SPARE, FIRST, SECOND]);
    expectRolledOut(fleet);
    for (const id of HOSTS)
      expect(rollout(fleet, id)).toMatchObject({
        kind: "reimage",
        result: "Succeeded",
        bundle: { sha256: NEW_BUNDLE },
      });
  });

  it("blocks without draining when there is no room, holds the fleet, and waits for capacity to change", async () => {
    const fleet = simulateFleet(
      [
        { instanceId: FIRST, podId: "zhimpngvqyotuj", gpus: 1 },
        { instanceId: SECOND, podId: "dv31b4wrd2yc8n", gpus: 1 },
      ],
      [{ name: "kev", gpus: 1, replicas: 2 }],
    );
    fleet.place("kev", FIRST);
    fleet.place("kev", SECOND);
    const metrics = createMetrics();
    const pinned = pins(NEW_IMAGE, NEW_BUNDLE);

    await run(
      fleet,
      pinned,
      () => rollout(fleet, FIRST)?.result === "Blocked",
      {
        metrics,
      },
    );
    const blockedAt = fleet.kube.calls.length;
    const events = await run(fleet, pinned, () => false, { metrics }, 40);

    expect(rollout(fleet, FIRST)).toMatchObject({
      result: "Blocked",
      lastError: "No capacity for a replacement kev replica",
    });
    // Nothing else starts, and the blocked host is not drained again while
    // nothing has changed.
    expect(started(events)).toEqual([]);
    expect(rollout(fleet, SECOND)).toBeUndefined();
    expect(
      fleet.kube.calls
        .slice(blockedAt)
        .filter(
          (call) => call.method === "PATCH" && call.path.startsWith(NODES),
        ),
    ).toEqual([]);
    expect(fleet.sim(FIRST)).toMatchObject({ image: OLD_IMAGE, resets: 0 });
    expect(fleet.node(FIRST).spec?.unschedulable).not.toBe(true);
    expect(
      fleet.scaledObject("kev").metadata.annotations?.[PAUSED_REPLICAS],
    ).toBeUndefined();
    expect(fleet.host(SECOND).status?.plan).toContain(
      `Held: waiting for capacity for gpu-${FIRST}`,
    );
    expect(
      await metrics.registry.getSingleMetricAsString(
        "gradiated_gpu_fleet_rollout_blocked",
      ),
    ).toContain(
      `gradiated_gpu_fleet_rollout_blocked{instance_id="${FIRST}"} 1`,
    );
    expect(fleet.violations).toEqual([]);
  });

  it.each(["reservation", "selector", "affinity"])(
    "blocks before cordon or surge when the spare violates %s",
    async (constraint) => {
      const fleet = simulateFleet(
        [
          { instanceId: FIRST, podId: "serving", gpus: 8 },
          {
            instanceId: SECOND,
            podId: "reserved",
            gpus: 8,
            image: NEW_IMAGE,
            bundle: NEW_BUNDLE,
          },
        ],
        [{ name: "glm", gpus: 8, replicas: 1 }],
      );
      fleet.place("glm", FIRST);
      const node = fleet.kube.objects.get(
        `${NODES}/gpu-${SECOND}`,
      ) as unknown as {
        spec: { taints?: { key: string; value: string; effect: string }[] };
      };
      const pod = fleet.podsOn(FIRST)[0]!;
      if (constraint === "reservation")
        node.spec.taints = [
          {
            key: "gradiated.com/kimi-k31",
            value: "reserved",
            effect: "NoSchedule",
          },
        ];
      if (constraint === "selector")
        pod.spec.nodeSelector = { "gradiated.com/instance-id": FIRST };
      if (constraint === "affinity")
        pod.spec.affinity = {
          nodeAffinity: {
            requiredDuringSchedulingIgnoredDuringExecution: {
              nodeSelectorTerms: [
                {
                  matchExpressions: [
                    {
                      key: "gradiated.com/instance-id",
                      operator: "In",
                      values: [FIRST],
                    },
                  ],
                },
              ],
            },
          },
        };
      const baseline = fleet.kube.calls.length;
      await run(
        fleet,
        pins(NEW_IMAGE, NEW_BUNDLE),
        () => rollout(fleet, FIRST)?.result === "Blocked",
      );
      expect(rollout(fleet, FIRST)?.lastError).toBe(
        "No capacity for a replacement glm replica",
      );
      expect(fleet.node(FIRST).spec?.unschedulable).not.toBe(true);
      expect(
        fleet.scaledObject("glm").metadata.annotations?.[PAUSED_REPLICAS],
      ).toBeUndefined();
      expect(
        fleet.kube.calls
          .slice(baseline)
          .filter(
            (call) =>
              call.method === "PATCH" &&
              (call.path.startsWith(NODES) ||
                call.path.includes("scaledobjects")),
          ),
      ).toEqual([]);
      expect(
        fleet
          .podsOn(FIRST)
          .filter((item) =>
            item.status?.conditions?.some(
              (c: { type: string; status: string }) =>
                c.type === "Ready" && c.status === "True",
            ),
          ),
      ).toHaveLength(1);
      expect(fleet.sim(FIRST).resets).toBe(0);
      expect(fleet.violations).toEqual([]);
    },
  );

  it("retires one replica of an opted-in model when no host has room, never all of them", async () => {
    const fleet = simulateFleet(
      [
        { instanceId: FIRST, podId: "zhimpngvqyotuj", gpus: 1 },
        { instanceId: SECOND, podId: "dv31b4wrd2yc8n", gpus: 1 },
      ],
      [{ name: "kev", gpus: 1, replicas: 2 }],
    );
    fleet.place("kev", FIRST);
    fleet.place("kev", SECOND);

    const events = await run(
      fleet,
      pins(NEW_IMAGE, NEW_BUNDLE),
      () =>
        [FIRST, SECOND].every(
          (id) => rollout(fleet, id)?.result === "Succeeded",
        ) && fleet.ready("kev") === 2,
      { retireOnReimage: new Set(["kev"]) },
    );

    expect(started(events)).toEqual([FIRST, SECOND]);
    for (const id of [FIRST, SECOND]) {
      expect(fleet.sim(id)).toMatchObject({
        image: NEW_IMAGE,
        bundle: NEW_BUNDLE,
        state: "enrolled",
        resets: 1,
      });
      expect(fleet.node(id).spec?.unschedulable).toBeFalsy();
    }
    // One replica is down while its host is re-imaged; the other always serves.
    expect(fleet.violations.length).toBeGreaterThan(0);
    expect(
      fleet.violations.every((violation) =>
        violation.endsWith("kev had 1 Ready replicas"),
      ),
    ).toBe(true);
    expect(fleet.ready("kev")).toBe(2);
    expect(
      fleet.scaledObject("kev").metadata.annotations?.[PAUSED_REPLICAS],
    ).toBeUndefined();
  });

  it("does not retire the only replica of an opted-in model", async () => {
    const fleet = simulateFleet(
      [
        { instanceId: FIRST, podId: "zhimpngvqyotuj", gpus: 1 },
        { instanceId: SECOND, podId: "dv31b4wrd2yc8n", gpus: 1 },
      ],
      [
        { name: "kev", gpus: 1, replicas: 1 },
        { name: "glm", gpus: 1, replicas: 1 },
      ],
    );
    fleet.place("kev", FIRST);
    fleet.place("glm", SECOND);

    await run(
      fleet,
      pins(NEW_IMAGE, NEW_BUNDLE),
      () => rollout(fleet, FIRST)?.result === "Blocked",
      { retireOnReimage: new Set(["kev"]) },
    );

    expect(rollout(fleet, FIRST)).toMatchObject({
      result: "Blocked",
      lastError: "Retiring this host's kev replicas would leave none",
    });
    expect(fleet.sim(FIRST)).toMatchObject({ image: OLD_IMAGE, resets: 0 });
    expect(fleet.violations).toEqual([]);
    expect(fleet.ready("kev")).toBe(1);

    // Nothing changes, so the blocked host is not cordoned or retried again.
    const blockedAt = fleet.kube.calls.length;
    const events = await run(
      fleet,
      pins(NEW_IMAGE, NEW_BUNDLE),
      () => false,
      { retireOnReimage: new Set(["kev"]) },
      40,
    );
    expect(started(events)).toEqual([]);
    expect(
      fleet.kube.calls
        .slice(blockedAt)
        .filter(
          (call) => call.method === "PATCH" && call.path.startsWith(NODES),
        ),
    ).toEqual([]);
  });

  it("retries a blocked host only once its pods fit on another host", async () => {
    const fleet = simulateFleet(
      [
        {
          instanceId: SPARE,
          podId: "yzno396wdsidu4",
          gpus: 1,
          image: NEW_IMAGE,
          bundle: NEW_BUNDLE,
        },
        { instanceId: FIRST, podId: "zhimpngvqyotuj", gpus: 1 },
      ],
      [{ name: "kev", gpus: 1, replicas: 1 }],
    );
    fleet.place("kev", FIRST);
    fleet.placeTraining(SPARE);
    const pinned = pins(NEW_IMAGE, NEW_BUNDLE);
    await run(fleet, pinned, () => rollout(fleet, FIRST)?.result === "Blocked");

    // Pods come and go on the spare, but no GPU is freed.
    fleet.placeTraining(SPARE);
    const events = await run(fleet, pinned, () => false, {}, 60);
    expect(started(events)).toEqual([]);
    expect(rollout(fleet, FIRST)).toMatchObject({
      result: "Blocked",
      blockedCount: 1,
    });
    expect(fleet.host(FIRST).status?.plan).toBe(
      "Waiting: Blocked: No capacity for a replacement kev replica; retried once its pods fit on other hosts",
    );

    for (const pod of fleet.podsOn(SPARE))
      fleet.kube.objects.delete(`${PODS}/${pod.metadata.name}`);
    await run(
      fleet,
      pinned,
      () => rollout(fleet, FIRST)?.result === "Succeeded",
    );

    expect(fleet.sim(FIRST)).toMatchObject({ image: NEW_IMAGE, resets: 1 });
    expect(fleet.violations).toEqual([]);
  });

  it("keeps a reservation blocked until the serving workload tolerates it", async () => {
    const fleet = simulateFleet(
      [
        { instanceId: FIRST, podId: "serving", gpus: 8 },
        {
          instanceId: SECOND,
          podId: "reserved",
          gpus: 8,
          image: NEW_IMAGE,
          bundle: NEW_BUNDLE,
        },
      ],
      [{ name: "reserved-model", gpus: 8, replicas: 1 }],
    );
    fleet.place("reserved-model", FIRST);
    const node = fleet.kube.objects.get(
      `${NODES}/gpu-${SECOND}`,
    ) as unknown as {
      spec: { taints: { key: string; value: string; effect: string }[] };
    };
    const reservation = {
      key: "gradiated.com/kimi-k31",
      value: "reserved",
      effect: "NoSchedule",
    };
    node.spec.taints = [reservation];
    const pinned = pins(NEW_IMAGE, NEW_BUNDLE);
    await run(fleet, pinned, () => rollout(fleet, FIRST)?.result === "Blocked");
    const blockedCount = rollout(fleet, FIRST)?.blockedCount;
    await run(fleet, pinned, () => false, {}, 40);
    expect(rollout(fleet, FIRST)?.blockedCount).toBe(blockedCount);
    expect(fleet.sim(FIRST).resets).toBe(0);

    fleet.podsOn(FIRST)[0]!.spec.tolerations = [reservation];
    await run(
      fleet,
      pinned,
      () => rollout(fleet, FIRST)?.result === "Succeeded",
    );
    expect(fleet.sim(FIRST).resets).toBe(1);
    expect(fleet.node(SECOND).spec).toMatchObject({ taints: [reservation] });
    expect(fleet.violations).toEqual([]);
  });

  it.each([false, true])(
    "honors required hostname anti-affinity with a matching destination resident=%s",
    async (occupied) => {
      const fleet = simulateFleet(
        [
          { instanceId: FIRST, podId: "serving", gpus: 4 },
          {
            instanceId: SECOND,
            podId: "spare",
            gpus: 8,
            image: NEW_IMAGE,
            bundle: NEW_BUNDLE,
          },
        ],
        [{ name: "glm", gpus: 4, replicas: occupied ? 2 : 1 }],
      );
      fleet.place("glm", FIRST);
      if (occupied) fleet.place("glm", SECOND);
      for (const id of [FIRST, SECOND]) {
        const node = fleet.kube.objects.get(
          `${NODES}/gpu-${id}`,
        ) as unknown as { metadata: { labels: Record<string, string> } };
        node.metadata.labels = { "kubernetes.io/hostname": `gpu-${id}` };
      }
      fleet.podsOn(FIRST)[0]!.spec.affinity = {
        podAntiAffinity: {
          requiredDuringSchedulingIgnoredDuringExecution: [
            {
              topologyKey: "kubernetes.io/hostname",
              labelSelector: {
                matchLabels: { "app.kubernetes.io/name": "glm" },
              },
            },
          ],
        },
      };
      await run(
        fleet,
        pins(NEW_IMAGE, NEW_BUNDLE),
        () =>
          rollout(fleet, FIRST)?.result ===
          (occupied ? "Blocked" : "Succeeded"),
      );
      expect(rollout(fleet, FIRST)?.result).toBe(
        occupied ? "Blocked" : "Succeeded",
      );
      expect(fleet.sim(FIRST).resets).toBe(occupied ? 0 : 1);
      expect(fleet.violations).toEqual([]);
    },
  );

  it("assigns a constrained equal-size replica before a flexible replica", async () => {
    const fleet = simulateFleet(
      [
        { instanceId: FIRST, podId: "serving", gpus: 4 },
        {
          instanceId: SPARE,
          podId: "restricted",
          gpus: 2,
          image: NEW_IMAGE,
          bundle: NEW_BUNDLE,
        },
        {
          instanceId: SECOND,
          podId: "flexible",
          gpus: 2,
          image: NEW_IMAGE,
          bundle: NEW_BUNDLE,
        },
      ],
      [
        { name: "flexible", gpus: 2, replicas: 1 },
        { name: "restricted", gpus: 2, replicas: 1 },
      ],
    );
    fleet.place("flexible", FIRST);
    fleet.place("restricted", FIRST);
    const restricted = fleet
      .podsOn(FIRST)
      .find(
        (pod) => pod.metadata.labels["app.kubernetes.io/name"] === "restricted",
      )!;
    restricted.spec.nodeSelector = { pool: "restricted" };
    const node = fleet.kube.objects.get(`${NODES}/gpu-${SPARE}`) as unknown as {
      metadata: { labels: Record<string, string> };
    };
    node.metadata.labels = { pool: "restricted" };
    await run(
      fleet,
      pins(NEW_IMAGE, NEW_BUNDLE),
      () =>
        rollout(fleet, FIRST)?.step === "Surge" ||
        rollout(fleet, FIRST)?.result === "Blocked",
    );
    expect(rollout(fleet, FIRST)).toMatchObject({
      result: "Running",
      step: "Surge",
    });
    expect(fleet.violations).toEqual([]);
  });

  it("backtracks an initially valid GPU packing when later replicas cannot fit", async () => {
    const fleet = simulateFleet(
      [
        { instanceId: FIRST, podId: "serving", gpus: 8 },
        {
          instanceId: SPARE,
          podId: "four-slots",
          gpus: 4,
          image: NEW_IMAGE,
          bundle: NEW_BUNDLE,
        },
        {
          instanceId: SECOND,
          podId: "three-slots",
          gpus: 3,
          image: NEW_IMAGE,
          bundle: NEW_BUNDLE,
        },
      ],
      [
        { name: "wide", gpus: 3, replicas: 1 },
        { name: "pair", gpus: 2, replicas: 2 },
      ],
    );
    fleet.place("wide", FIRST);
    fleet.place("pair", FIRST);
    fleet.place("pair", FIRST);
    await run(
      fleet,
      pins(NEW_IMAGE, NEW_BUNDLE),
      () =>
        rollout(fleet, FIRST)?.step === "Surge" ||
        rollout(fleet, FIRST)?.result === "Blocked",
    );
    expect(rollout(fleet, FIRST)).toMatchObject({
      result: "Running",
      step: "Surge",
    });
    expect(fleet.sim(FIRST).resets).toBe(0);
    expect(fleet.violations).toEqual([]);
  });

  it("waits twice as long before each retry of a host that keeps blocking", async () => {
    const fleet = simulateFleet(
      [
        {
          instanceId: SPARE,
          podId: "yzno396wdsidu4",
          gpus: 1,
          image: NEW_IMAGE,
          bundle: NEW_BUNDLE,
        },
        { instanceId: FIRST, podId: "zhimpngvqyotuj", gpus: 1 },
      ],
      [{ name: "kev", gpus: 1, replicas: 1 }],
    );
    fleet.place("kev", FIRST);
    const pinned = pins(NEW_IMAGE, NEW_BUNDLE);
    const freeSpare = () => {
      for (const pod of fleet.podsOn(SPARE))
        fleet.kube.objects.delete(`${PODS}/${pod.metadata.name}`);
    };
    const waits: number[] = [];
    fleet.placeTraining(SPARE);
    for (let block = 1; block <= 3; block++) {
      await run(
        fleet,
        pinned,
        () => rollout(fleet, FIRST)?.blockedCount === block,
      );
      const blockedAt = Date.parse(rollout(fleet, FIRST)!.finishedAt!);
      // Room appears, and is taken again just after the retry starts.
      freeSpare();
      await run(
        fleet,
        pinned,
        () => rollout(fleet, FIRST)?.result === "Running",
      );
      waits.push(fleet.now().getTime() - blockedAt);
      fleet.placeTraining(SPARE);
    }

    expect(waits.map((wait) => Math.floor(wait / 60_000))).toEqual([5, 10, 20]);
  });

  it("halts the fleet when enrollment keeps failing, leaves the host cordoned and revokes its keys", async () => {
    const fleet = kevFleet();
    fleet.sim(SPARE).enrollFails =
      "Enrollment command exited with status 1 (ValueError)";
    const pinned = pins(NEW_IMAGE, NEW_BUNDLE);

    await run(fleet, pinned, () => rollout(fleet, SPARE)?.result === "Failed", {
      limits: { ...LIMITS, Enroll: 5 * 60_000 },
    });
    await run(fleet, pinned, () => false, {}, 20);

    expect(rollout(fleet, SPARE)).toMatchObject({
      result: "Failed",
      step: "Enroll",
    });
    expect(rollout(fleet, SPARE)?.lastError).toContain("status 1 (ValueError)");
    expect(fleet.node(SPARE).spec?.unschedulable).toBe(true);
    expect(rollout(fleet, FIRST)).toBeUndefined();
    expect(fleet.host(FIRST).status?.plan).toContain(
      `Held: the rollout on gpu-${SPARE} failed`,
    );
    expect([...fleet.keys.values()].every((key) => key.revoked)).toBe(true);
  });

  it("holds the fleet after a rollout fails on a healthy host", async () => {
    const fleet = kevFleet();
    const pinned = pins(NEW_IMAGE, NEW_BUNDLE);
    // The spare is re-imaged and healthy, but its soak outlasts the step's deadline.
    await run(fleet, pinned, () => rollout(fleet, SPARE)?.result === "Failed", {
      limits: { ...LIMITS, soakFor: 10 * 60_000, Soak: 5 * 60_000 },
    });
    const failed = rollout(fleet, SPARE);
    expect(failed?.lastError).toMatch(/^Soak did not finish/);

    await run(fleet, pinned, () => false, {}, 50);

    expect(rollout(fleet, SPARE)).toEqual(failed);
    expect(rollout(fleet, FIRST)).toBeUndefined();
    expect(rollout(fleet, SECOND)).toBeUndefined();
  });

  it("restarts a failed rollout only for a new retry annotation", async () => {
    const fleet = kevFleet();
    fleet.sim(SPARE).enrollFails = "Enrollment command exited with status 1";
    const pinned = pins(NEW_IMAGE, NEW_BUNDLE);
    await run(fleet, pinned, () => rollout(fleet, SPARE)?.result === "Failed", {
      limits: { ...LIMITS, Enroll: 5 * 60_000 },
    });

    delete fleet.sim(SPARE).enrollFails;
    await fleet.kube.api.mergePatch(`${GPU_HOSTS}/gpu-${SPARE}`, {
      metadata: { annotations: { [RETRY_ANNOTATION]: "1" } },
    });
    await run(
      fleet,
      pinned,
      () => rollout(fleet, SPARE)?.result === "Succeeded",
    );

    expect(rollout(fleet, SPARE)).toMatchObject({
      result: "Succeeded",
      retry: "1",
    });
    expect(fleet.sim(SPARE)).toMatchObject({
      image: NEW_IMAGE,
      state: "enrolled",
    });
  });

  it("keeps its own cordon through the fleet pass that uncordons returned hosts", async () => {
    const fleet = kevFleet();

    await run(fleet, pins(NEW_IMAGE, NEW_BUNDLE), () =>
      ["Drain", "Reimage", "Join"].includes(rollout(fleet, FIRST)?.step ?? ""),
    );
    await fleet.observe();

    expect(fleet.node(FIRST)).toMatchObject({
      metadata: { annotations: { [CORDONED_BY]: ROLLOUT_CORDON } },
      spec: { unschedulable: true },
    });
  });

  it("re-images a node someone else cordoned and leaves it cordoned", async () => {
    const fleet = simulateFleet(
      [
        { instanceId: SPARE, podId: "yzno396wdsidu4", gpus: 1 },
        { instanceId: FIRST, podId: "zhimpngvqyotuj", gpus: 1 },
        { instanceId: SECOND, podId: "dv31b4wrd2yc8n", gpus: 1 },
      ],
      [{ name: "kev", gpus: 1, replicas: 1 }],
    );
    fleet.place("kev", FIRST);
    fleet.cordonByHand(SECOND);

    await run(fleet, pins(NEW_IMAGE, NEW_BUNDLE), allSucceeded(fleet));

    expect(fleet.sim(SECOND)).toMatchObject({ image: NEW_IMAGE, resets: 1 });
    expect(fleet.node(SECOND).spec?.unschedulable).toBe(true);
    for (const id of [SPARE, FIRST])
      expect(fleet.node(id).spec?.unschedulable).toBeFalsy();
  });

  // Binds a pod to the host while the operator cordons it, after the
  // operator listed the host's pods.
  const bindDuringCordon = (fleet: Simulation, bind: () => void) => {
    const cluster = createCluster(fleet.kube.api, () => undefined);
    let bound = false;
    return {
      ...cluster,
      cordon: async (instanceId: string) => {
        if (!bound) bind();
        bound = true;
        return cluster.cordon(instanceId);
      },
    };
  };

  it("blocks when a training job binds to the host while it is cordoned", async () => {
    const fleet = kevFleet();
    const cluster = bindDuringCordon(fleet, () => fleet.placeTraining(SPARE));

    await run(
      fleet,
      pins(NEW_IMAGE, NEW_BUNDLE),
      () => rollout(fleet, SPARE)?.result === "Blocked",
      { cluster },
    );

    expect(rollout(fleet, SPARE)?.lastError).toBe(
      "A training job runs on the host",
    );
    expect(fleet.sim(SPARE).resets).toBe(0);
  });

  it("moves a serving pod that binds to the host while it is cordoned", async () => {
    const fleet = kevFleet();
    // The spare had nothing to move when the operator listed its pods.
    const cluster = bindDuringCordon(fleet, () => {
      const [pod] = fleet.podsOn(FIRST);
      pod!.spec.nodeName = `gpu-${SPARE}`;
    });

    await run(
      fleet,
      pins(NEW_IMAGE, NEW_BUNDLE),
      () => ![undefined, "Cordon"].includes(rollout(fleet, SPARE)?.step),
      { cluster },
    );

    expect(rollout(fleet, SPARE)?.step).toBe("Surge");
    expect(fleet.sim(SPARE).resets).toBe(0);
  });

  it("moves a serving pod that binds to the host after the cordon, before the wipe", async () => {
    const fleet = kevFleet();
    const pinned = pins(NEW_IMAGE, NEW_BUNDLE);
    await run(fleet, pinned, () => rollout(fleet, SPARE)?.step === "Reimage");

    const [pod] = fleet.podsOn(FIRST);
    pod!.spec.nodeName = `gpu-${SPARE}`;
    await run(fleet, pinned, () => rollout(fleet, SPARE)?.step !== "Reimage");

    expect(rollout(fleet, SPARE)?.step).toBe("Surge");
    expect(fleet.sim(SPARE).resets).toBe(0);
  });

  it("blocks when a training job binds to the host after the cordon, before the wipe", async () => {
    const fleet = kevFleet();
    const pinned = pins(NEW_IMAGE, NEW_BUNDLE);
    await run(fleet, pinned, () => rollout(fleet, SPARE)?.step === "Reimage");

    fleet.placeTraining(SPARE);
    await run(fleet, pinned, () => rollout(fleet, SPARE)?.result === "Blocked");

    expect(rollout(fleet, SPARE)?.lastError).toBe(
      "A training job runs on the host",
    );
    expect(fleet.sim(SPARE).resets).toBe(0);
  });

  it("never re-images a host running a training job, and still rolls the rest", async () => {
    const fleet = kevFleet();
    fleet.placeTraining(SPARE);

    await run(fleet, pins(NEW_IMAGE, NEW_BUNDLE), () =>
      [FIRST, SECOND].every((id) => rollout(fleet, id)?.result === "Succeeded"),
    );

    expect(fleet.sim(SPARE)).toMatchObject({ image: OLD_IMAGE, resets: 0 });
    expect(rollout(fleet, SPARE)).toBeUndefined();
    expect(fleet.host(SPARE).status?.plan).toContain("training job");
    expect(fleet.violations).toEqual([]);
  });
});

// The 2026-10-23 incident: every pod gpu-controller published failed to parse
// and was left out, so a serving host looked empty and was re-imaged at once.
describe("pods as the virtual kubelet publishes them", () => {
  const DEEPSEEK = "deepseek-5867b44cff-x2k9p";

  it("reads a serving pod with null condition and start times", () => {
    expect(
      clusterPod(virtualKubeletPod("deepseek", DEEPSEEK, `gpu-${FIRST}`)),
    ).toEqual({
      name: DEEPSEEK,
      uid: `${DEEPSEEK}-uid`,
      namespace: "gpu-inference",
      labels: { "app.kubernetes.io/name": "deepseek" },
      model: "deepseek",
      training: false,
      node: `gpu-${FIRST}`,
      ready: true,
      terminating: false,
      gpus: 4,
      qualifiedRuntime: `${DEEPSEEK}:1`,
      qualificationFailed: false,
    });
  });

  it("reads a qualification error only for the running container", () => {
    const pod = virtualKubeletPod(
      "kev",
      "kev-86bc8f5569-tkp42",
      `gpu-${FIRST}`,
      false,
    );
    const failed = (error: string) =>
      clusterPod({
        ...pod,
        metadata: {
          ...pod.metadata,
          annotations: { "gradiated.com/qualification-error": error },
        },
      })?.qualificationFailed;

    expect(failed("runpod://4242:2026-10-23T09:12:44Z")).toBe(true);
    expect(failed("runpod://4242:2026-10-22T08:00:00Z")).toBe(false);
    expect(clusterPod(pod)?.qualificationFailed).toBe(false);
  });

  it("resolves the catalog identity from annotations, including an explicit empty mapping", () => {
    const pod = virtualKubeletPod("kev", "kev-test", `gpu-${FIRST}`);
    const annotations = pod.metadata.annotations as Record<string, string>;
    annotations["gradiated.com/model-id"] = "private/kev";
    expect(clusterPod(pod)?.modelId).toBe("private/kev");

    annotations["gradiated.com/serving-model-id"] = "jaredpalmer/kev-9b";
    expect(clusterPod(pod)?.modelId).toBe("jaredpalmer/kev-9b");

    annotations["gradiated.com/serving-model-id"] = "";
    expect(clusterPod(pod)?.modelId).toBeUndefined();
  });

  // Three 8-GPU B300 hosts, each of the two serving hosts running one
  // DeepSeek and one GLM replica, as in production.
  const b300Fleet = () => {
    const fleet = simulateFleet(
      [
        { instanceId: SPARE, podId: "yzno396wdsidu4", gpus: 8 },
        { instanceId: FIRST, podId: "zhimpngvqyotuj", gpus: 8 },
        { instanceId: SECOND, podId: "dv31b4wrd2yc8n", gpus: 8 },
      ],
      [
        { name: "deepseek", gpus: 4, replicas: 2 },
        { name: "glm", gpus: 4, replicas: 2 },
      ],
    );
    for (const [model, name, id] of [
      ["deepseek", DEEPSEEK, FIRST],
      ["glm", "glm-7d9f8c6b5a-q4m2n", FIRST],
      ["deepseek", "deepseek-5867b44cff-h7v3c", SECOND],
      ["glm", "glm-7d9f8c6b5a-w8r5t", SECOND],
    ] as const)
      fleet.kube.seed(PODS, virtualKubeletPod(model, name, `gpu-${id}`));
    return fleet;
  };

  it("surges and drains a serving host before re-imaging it", async () => {
    const fleet = b300Fleet();
    // The pods left on each host when RunPod is asked to re-image it.
    const wiped = new Map<string, string[]>();
    const enrollment: Enrollment = {
      ...fleet.enrollment,
      reimage: async (host, image, key) => {
        wiped.set(
          host.spec.instanceId,
          fleet
            .podsOn(host.spec.instanceId)
            .map((pod) => pod.metadata.name as string),
        );
        return fleet.enrollment.reimage(host, image, key);
      },
    };

    const events = await run(
      fleet,
      pins(NEW_IMAGE, NEW_BUNDLE),
      allSucceeded(fleet),
      { enrollment: async () => enrollment },
    );

    const steps = events
      .filter(
        (event) =>
          event.event === "gpu_rollout_step" && event.instance_id === FIRST,
      )
      .map((event) => `${event.from} -> ${event.to}`);
    expect(steps.slice(0, 4)).toEqual([
      "Cordon -> Surge",
      "Surge -> Drain",
      "Drain -> Reimage",
      "Reimage -> Join",
    ]);
    expect(Object.fromEntries(wiped)).toEqual({
      [SPARE]: [],
      [FIRST]: [],
      [SECOND]: [],
    });
    expect(fleet.violations).toEqual([]);
    expect(fleet.ready("deepseek")).toBe(2);
    expect(fleet.ready("glm")).toBe(2);
  });

  it("re-images nothing while a pod on a host cannot be read", async () => {
    const fleet = kevFleet();
    const pinned = pins(NEW_IMAGE, NEW_BUNDLE);
    await run(fleet, pinned, () => rollout(fleet, SPARE)?.step === "Reimage");

    // A field the schema does not expect: a GPU count sent as a number.
    const pod = virtualKubeletPod(
      "glm",
      "glm-7d9f8c6b5a-q4m2n",
      `gpu-${SPARE}`,
    );
    (pod.spec.containers[0]!.resources.limits as Record<string, unknown>)[
      "nvidia.com/gpu"
    ] = 4;
    fleet.kube.seed(PODS, pod);
    const events = await run(fleet, pinned, () => false, {}, 20);

    expect(rollout(fleet, SPARE)).toMatchObject({
      step: "Reimage",
      result: "Running",
    });
    expect([...fleet.sims.values()].every((host) => host.resets === 0)).toBe(
      true,
    );
    expect(events).toContainEqual({
      event: "gpu_fleet_pod_unreadable",
      level: "warn",
      error: expect.stringContaining(
        "Pod glm-7d9f8c6b5a-q4m2n cannot be read: spec.containers.0.resources.limits.nvidia.com/gpu",
      ),
    });
    expect(events).toContainEqual(
      expect.objectContaining({ event: "pass_failed" }),
    );
  });
});

// The faults a crash, a lost leader or a flaky API cause between a side effect
// and the status write that records it.
describe("failures between steps", () => {
  const failingWrite = (
    api: Kubernetes,
    fail: (count: number, path: string, body: unknown) => boolean,
  ) => {
    let count = 0;
    return {
      ...api,
      mergePatch: async (path: string, body: unknown) => {
        if (
          path.startsWith(GPU_HOSTS) &&
          path.endsWith("/status") &&
          fail(++count, path, body)
        )
          throw new Error("Kubernetes PATCH returned 500");
        return api.mergePatch(path, body);
      },
    };
  };

  it("waits out a slow image pull after a restart instead of re-imaging again", async () => {
    const fleet = kevFleet();
    for (const id of HOSTS) fleet.sim(id).pullFor = 20 * 60_000;
    // The operator stops after RunPod accepts each re-image and before it
    // records the move to Join.
    const stopped = new Set<string>();
    const api = failingWrite(fleet.kube.api, (_count, path, body) => {
      const step = (body as { status?: { rollout?: Rollout } }).status?.rollout
        ?.step;
      if (step !== "Join" || stopped.has(path)) return false;
      stopped.add(path);
      return true;
    });

    await run(fleet, pins(NEW_IMAGE, NEW_BUNDLE), allSucceeded(fleet), {
      api,
      cluster: createCluster(api, () => undefined),
    });

    expectRolledOut(fleet);
  });

  it.each([
    ["a lost connection RunPod applied", { applied: true }],
    ["a lost connection RunPod did not apply", { applied: false }],
    ["a 5xx RunPod did not apply", { status: 503, applied: false }],
    ["a refusal", { status: 400, applied: false }],
  ])("re-images once after %s", async (_case, fails) => {
    const fleet = kevFleet();
    fleet.sim(SPARE).updateFails = fails;

    await run(fleet, pins(NEW_IMAGE, NEW_BUNDLE), allSucceeded(fleet));

    expectRolledOut(fleet);
  });

  it("revokes the key and asks again at once when RunPod refuses the re-image", async () => {
    const fleet = kevFleet();
    fleet.sim(SPARE).updateFails = { status: 400, applied: false };
    const begun = fleet.now().getTime();

    await run(
      fleet,
      pins(NEW_IMAGE, NEW_BUNDLE),
      () => fleet.sim(SPARE).resets === 1,
    );

    const [refused, sent] = [...fleet.keys.values()];
    expect(refused).toMatchObject({ used: false, revoked: true });
    expect(sent).toMatchObject({ revoked: false });
    expect(fleet.now().getTime() - begun).toBeLessThan(10 * 60_000);
  });

  it("does not re-image a host whose device reconnects before the wipe", async () => {
    const fleet = kevFleet();
    await fleet.observe();
    fleet.advance(5 * 60_000);
    fleet.wipe(SPARE);
    fleet.advance(15 * 60_000);
    const pinned = pins(OLD_IMAGE, OLD_BUNDLE);
    await run(fleet, pinned, () => rollout(fleet, SPARE)?.step === "Reimage");

    // The host's tailscaled is back; its agent has not answered yet.
    for (const device of fleet.devices.values())
      if (device.hostname === `gpu-${SPARE}`) device.connectedToControl = true;
    await run(fleet, pinned, () => rollout(fleet, SPARE)?.result === "Blocked");

    expect(rollout(fleet, SPARE)?.lastError).toBe(
      "The host is online again, so it is not re-imaged",
    );
    expect(fleet.sim(SPARE).resets).toBe(0);
  });

  it("does not cordon a host whose training job started after its rollout did", async () => {
    const fleet = kevFleet();
    const pinned = pins(NEW_IMAGE, NEW_BUNDLE);
    await run(fleet, pinned, () => rollout(fleet, SPARE)?.step === "Cordon");

    fleet.placeTraining(SPARE);
    await run(fleet, pinned, () => rollout(fleet, SPARE)?.result === "Blocked");

    expect(rollout(fleet, SPARE)?.lastError).toBe(
      "A training job runs on the host",
    );
    expect(fleet.sim(SPARE).resets).toBe(0);
    expect(fleet.node(SPARE).spec?.unschedulable).toBeFalsy();
  });

  // A full rolling re-image for every status write, so CI runners get 60 s.
  it("finishes after any single status write fails, without a second re-image or an unrevoked key", async () => {
    const clean = kevFleet();
    let writes = 0;
    const counting = failingWrite(clean.kube.api, () => {
      writes++;
      return false;
    });
    await run(clean, pins(NEW_IMAGE, NEW_BUNDLE), allSucceeded(clean), {
      api: counting,
      cluster: createCluster(counting, () => undefined),
    });

    for (let k = 1; k <= writes; k++) {
      const fleet = kevFleet();
      const api = failingWrite(fleet.kube.api, (count) => count === k);
      await run(fleet, pins(NEW_IMAGE, NEW_BUNDLE), allSucceeded(fleet), {
        api,
        cluster: createCluster(api, () => undefined),
      });
      expect(
        HOSTS.map((id) => rollout(fleet, id)?.result),
        `status write ${k} failing`,
      ).toEqual(["Succeeded", "Succeeded", "Succeeded"]);
      expectRolledOut(fleet);
    }
  }, 60_000);

  it("finishes the same rollout when status writes and provider calls keep failing along the way", async () => {
    const fleet = kevFleet();
    const api = failingWrite(fleet.kube.api, (count) => count % 5 === 0);
    let reads = 0;
    const flaky: Enrollment = {
      ...fleet.enrollment,
      pod: async (host) => {
        if (++reads % 7 === 0) throw new Error("RunPod GET failed: 502");
        return fleet.enrollment.pod(host);
      },
    };

    await run(
      fleet,
      pins(NEW_IMAGE, NEW_BUNDLE),
      allSucceeded(fleet),
      {
        api,
        cluster: createCluster(api, () => undefined),
        enrollment: async () => flaky,
      },
      800,
    );

    expectRolledOut(fleet);
  });

  it("does not start a second enrollment while another replica's may still run", async () => {
    const fleet = kevFleet();
    fleet.sim(SPARE).enrollFails = "the SSH session to the pod dropped";
    const pinned = pins(NEW_IMAGE, NEW_BUNDLE);
    await run(fleet, pinned, () =>
      Boolean(rollout(fleet, SPARE)?.enrollStartedAt),
    );
    expect(rollout(fleet, SPARE)?.enrollBy).toBe("gpu-fleet-a");
    delete fleet.sim(SPARE).enrollFails;
    const keys = fleet.keys.size;

    // Another leader takes over and leaves the first enrollment its time.
    await run(fleet, pinned, () => false, { identity: "gpu-fleet-b" }, 20);
    expect(fleet.keys.size).toBe(keys);
    expect(rollout(fleet, SPARE)?.step).toBe("Enroll");

    fleet.advance(31 * 60_000);
    await run(fleet, pinned, allSucceeded(fleet), {
      identity: "gpu-fleet-b",
      limits: { ...LIMITS, Enroll: 60 * 60_000 },
    });
    expectRolledOut(fleet);
  });

  it("writes nothing once the lease is lost", async () => {
    const fleet = kevFleet();
    const before = fleet.kube.calls.length;
    const { rollouts } = engine(fleet, pins(NEW_IMAGE, NEW_BUNDLE), {
      leading: () => false,
    });

    await expect(rollouts.pass()).rejects.toThrow("The lease was lost");

    const writes = fleet.kube.calls
      .slice(before)
      .filter((call) => call.method !== "GET" && call.method !== "LIST");
    expect(writes).toEqual([]);
  });

  it("waits while RunPod and Tailscale access is unavailable, then proceeds", async () => {
    const fleet = kevFleet();
    let available = false;
    const access = async () => (available ? fleet.enrollment : undefined);
    const pinned = pins(NEW_IMAGE, NEW_BUNDLE);

    await run(fleet, pinned, () => false, { enrollment: access }, 10);
    expect(HOSTS.map((id) => rollout(fleet, id))).toEqual([
      undefined,
      undefined,
      undefined,
    ]);
    expect(fleet.host(SPARE).status?.plan).toContain("without RunPod access");

    available = true;
    await run(fleet, pinned, allSucceeded(fleet), { enrollment: access });
    expectRolledOut(fleet);
  });
});

describe("in-place bundle update", () => {
  const bundleFleet = () => {
    const fleet = simulateFleet(
      [
        {
          instanceId: FIRST,
          podId: "zhimpngvqyotuj",
          gpus: 1,
          image: NEW_IMAGE,
        },
        {
          instanceId: SECOND,
          podId: "dv31b4wrd2yc8n",
          gpus: 1,
          image: NEW_IMAGE,
        },
      ],
      [{ name: "kev", gpus: 1, replicas: 1 }],
    );
    return { fleet, pod: fleet.place("kev", FIRST) };
  };

  it("updates a host on the pinned image without moving its pods", async () => {
    const { fleet, pod } = bundleFleet();

    await run(
      fleet,
      pins(NEW_IMAGE, NEW_BUNDLE),
      () => rollout(fleet, FIRST)?.result === "Succeeded",
    );

    expect(rollout(fleet, FIRST)).toMatchObject({
      kind: "bundle",
      result: "Succeeded",
    });
    expect(fleet.sim(FIRST)).toMatchObject({ bundle: NEW_BUNDLE, resets: 0 });
    expect(fleet.podsOn(FIRST).map((item) => item.metadata.name)).toEqual([
      pod,
    ]);
    expect(fleet.node(FIRST).spec?.unschedulable).toBeFalsy();
  });

  it("still updates bundles in place in observe mode", async () => {
    const { fleet } = bundleFleet();

    await run(
      fleet,
      pins(NEW_IMAGE, NEW_BUNDLE),
      () =>
        [FIRST, SECOND].every(
          (id) => rollout(fleet, id)?.result === "Succeeded",
        ),
      { mode: "observe" },
    );

    for (const id of [FIRST, SECOND])
      expect(fleet.sim(id)).toMatchObject({ bundle: NEW_BUNDLE, resets: 0 });
  });

  it("fails when a serving pod leaves the host during the update", async () => {
    const { fleet, pod } = bundleFleet();

    await run(
      fleet,
      pins(NEW_IMAGE, NEW_BUNDLE),
      () => rollout(fleet, FIRST)?.step === "Soak",
    );
    fleet.kube.objects.delete(`${PODS}/${pod}`);
    await run(
      fleet,
      pins(NEW_IMAGE, NEW_BUNDLE),
      () => rollout(fleet, FIRST)?.result === "Failed",
    );

    expect(rollout(fleet, FIRST)?.lastError).toBe(
      "A serving pod restarted or left the host during the bundle update",
    );
  });

  it("waits for every serving pod to be Ready before taking the baseline", async () => {
    const { fleet, pod } = bundleFleet();
    fleet.notReady.add(pod);
    const pinned = pins(NEW_IMAGE, NEW_BUNDLE);
    await run(fleet, pinned, () => rollout(fleet, FIRST)?.step === "Apply");

    await run(fleet, pinned, () => false, {}, 10);
    expect(rollout(fleet, FIRST)).toMatchObject({ step: "Apply" });
    expect(fleet.host(FIRST).status?.rollout?.bundle).toBeUndefined();

    fleet.notReady.delete(pod);
    await run(
      fleet,
      pinned,
      () => rollout(fleet, FIRST)?.result === "Succeeded",
    );
    const uid = fleet.podsOn(FIRST)[0]!.metadata.uid;
    expect(Object.keys(rollout(fleet, FIRST)?.baseline ?? {})).toEqual([uid]);
  });

  it("does not wait for a serving pod whose running container failed qualification", async () => {
    const { fleet, pod } = bundleFleet();
    fleet.notReady.add(pod);
    const item = fleet.kube.objects.get(`${PODS}/${pod}`) as any;
    item.metadata.annotations["gradiated.com/qualification-error"] =
      "runpod://4242:2026-10-23T09:12:44Z";

    await run(
      fleet,
      pins(NEW_IMAGE, NEW_BUNDLE),
      () => rollout(fleet, FIRST)?.result === "Succeeded",
    );

    expect(fleet.sim(FIRST)).toMatchObject({ bundle: NEW_BUNDLE });
    expect(rollout(fleet, FIRST)?.baseline).toEqual({});
  });

  it("updates past an unready unavailable model without qualification or pod restarts", async () => {
    const { fleet, pod } = bundleFleet();
    fleet.notReady.add(pod);
    const item = fleet.kube.objects.get(`${PODS}/${pod}`) as any;
    item.metadata.annotations["gradiated.com/model-id"] = "jaredpalmer/kev-9b";
    delete item.metadata.annotations["gradiated.com/qualified-runtime"];
    const events = await run(
      fleet,
      pins(NEW_IMAGE, NEW_BUNDLE),
      () => rollout(fleet, FIRST)?.result === "Succeeded",
      {
        modelStatuses: async () =>
          new Map([["jaredpalmer/kev-9b", "unavailable"]]),
      },
    );

    expect(rollout(fleet, FIRST)?.baseline).toEqual({});
    expect(fleet.sim(FIRST)).toMatchObject({ bundle: NEW_BUNDLE, resets: 0 });
    expect(fleet.podsOn(FIRST).map((item) => item.metadata.name)).toEqual([
      pod,
    ]);
    expect(events).toContainEqual({
      event: "gpu_bundle_unavailable_models_excluded",
      instance_id: FIRST,
      bundle: NEW_BUNDLE,
      pods: [{ uid: item.metadata.uid, model_id: "jaredpalmer/kev-9b" }],
    });
  });

  it.each(["available", "retired", undefined] as const)(
    "keeps waiting for an unready pod when its catalog status is %s",
    async (status) => {
      const { fleet, pod } = bundleFleet();
      fleet.notReady.add(pod);
      const item = fleet.kube.objects.get(`${PODS}/${pod}`) as any;
      item.metadata.annotations["gradiated.com/model-id"] =
        "jaredpalmer/kev-9b";
      const pinned = pins(NEW_IMAGE, NEW_BUNDLE);
      const overrides = {
        modelStatuses: async () =>
          new Map(status ? [["jaredpalmer/kev-9b", status]] : []),
      };
      await run(
        fleet,
        pinned,
        () => rollout(fleet, FIRST)?.step === "Apply",
        overrides,
      );
      await run(fleet, pinned, () => false, overrides, 10);

      expect(rollout(fleet, FIRST)?.step).toBe("Apply");
      expect(fleet.sim(FIRST).bundle).toBe(OLD_BUNDLE);
    },
  );

  it("leaves Apply unchanged if the catalog cannot be read, then retries the read", async () => {
    const { fleet, pod } = bundleFleet();
    fleet.notReady.add(pod);
    const item = fleet.kube.objects.get(`${PODS}/${pod}`) as any;
    item.metadata.annotations["gradiated.com/model-id"] = "jaredpalmer/kev-9b";
    const pinned = pins(NEW_IMAGE, NEW_BUNDLE);
    const overrides = {
      modelStatuses: async () => {
        throw new Error("catalog unavailable");
      },
    };
    await run(
      fleet,
      pinned,
      () => rollout(fleet, FIRST)?.step === "Apply",
      overrides,
    );
    await run(fleet, pinned, () => false, overrides, 10);
    expect(rollout(fleet, FIRST)).toMatchObject({
      step: "Apply",
      lastError: "catalog unavailable",
    });
    expect(fleet.sim(FIRST).bundle).toBe(OLD_BUNDLE);

    await run(
      fleet,
      pinned,
      () => rollout(fleet, FIRST)?.result === "Succeeded",
      {
        modelStatuses: async () =>
          new Map([["jaredpalmer/kev-9b", "unavailable"]]),
      },
    );
    expect(fleet.sim(FIRST)).toMatchObject({ bundle: NEW_BUNDLE, resets: 0 });
  });

  it("uses the serving model identity rather than the Rollout name or private identity", async () => {
    const { fleet, pod } = bundleFleet();
    fleet.notReady.add(pod);
    const item = fleet.kube.objects.get(`${PODS}/${pod}`) as any;
    item.metadata.annotations["gradiated.com/model-id"] = "private/kev";
    item.metadata.annotations["gradiated.com/serving-model-id"] =
      "jaredpalmer/kev-9b";
    const pinned = pins(NEW_IMAGE, NEW_BUNDLE);
    const overrides = {
      modelStatuses: async () =>
        new Map([
          ["private/kev", "available" as const],
          ["jaredpalmer/kev-9b", "unavailable" as const],
        ]),
    };
    await run(
      fleet,
      pinned,
      () => rollout(fleet, FIRST)?.result === "Succeeded",
      overrides,
    );
    expect(rollout(fleet, FIRST)?.baseline).toEqual({});
    expect(fleet.sim(FIRST).bundle).toBe(NEW_BUNDLE);
  });

  it("still protects a Ready unavailable model even with a qualification error", async () => {
    const { fleet, pod } = bundleFleet();
    const item = fleet.kube.objects.get(`${PODS}/${pod}`) as any;
    item.metadata.annotations["gradiated.com/model-id"] = "jaredpalmer/kev-9b";
    item.metadata.annotations["gradiated.com/qualification-error"] =
      "runpod://4242:2026-10-23T09:12:44Z";
    const pinned = pins(NEW_IMAGE, NEW_BUNDLE);
    const overrides = {
      modelStatuses: async () =>
        new Map([["jaredpalmer/kev-9b", "unavailable" as const]]),
    };
    await run(
      fleet,
      pinned,
      () => rollout(fleet, FIRST)?.step === "Soak",
      overrides,
    );
    expect(rollout(fleet, FIRST)?.baseline).toHaveProperty(item.metadata.uid);

    fleet.kube.objects.delete(`${PODS}/${pod}`);
    await run(
      fleet,
      pinned,
      () => rollout(fleet, FIRST)?.result === "Failed",
      overrides,
    );
    expect(rollout(fleet, FIRST)?.lastError).toBe(
      "A serving pod restarted or left the host during the bundle update",
    );
  });

  it("still waits for qualification of a Ready unavailable model", async () => {
    const { fleet, pod } = bundleFleet();
    const item = fleet.kube.objects.get(`${PODS}/${pod}`) as any;
    item.metadata.annotations["gradiated.com/model-id"] = "jaredpalmer/kev-9b";
    const pinned = pins(NEW_IMAGE, NEW_BUNDLE);
    const overrides = {
      modelStatuses: async () =>
        new Map([["jaredpalmer/kev-9b", "unavailable" as const]]),
    };
    await run(
      fleet,
      pinned,
      () => rollout(fleet, FIRST)?.step === "Apply",
      overrides,
    );
    delete item.metadata.annotations["gradiated.com/qualified-runtime"];
    await engine(fleet, pinned, overrides).rollouts.pass();
    expect(rollout(fleet, FIRST)?.step).toBe("Apply");
    expect(fleet.sim(FIRST).bundle).toBe(OLD_BUNDLE);
  });

  it("rechecks readiness after reading the catalog and protects a pod that became Ready", async () => {
    const { fleet, pod } = bundleFleet();
    fleet.notReady.add(pod);
    const item = fleet.kube.objects.get(`${PODS}/${pod}`) as any;
    item.metadata.annotations["gradiated.com/model-id"] = "jaredpalmer/kev-9b";
    const pinned = pins(NEW_IMAGE, NEW_BUNDLE);
    const overrides = {
      modelStatuses: async () => {
        fleet.notReady.delete(pod);
        await fleet.observe();
        return new Map([["jaredpalmer/kev-9b", "unavailable" as const]]);
      },
    };
    await run(
      fleet,
      pinned,
      () => rollout(fleet, FIRST)?.result === "Succeeded",
      overrides,
    );
    expect(rollout(fleet, FIRST)?.baseline).toHaveProperty(item.metadata.uid);
  });

  it("still waits when the qualification error names an earlier container", async () => {
    const { fleet, pod } = bundleFleet();
    fleet.notReady.add(pod);
    const item = fleet.kube.objects.get(`${PODS}/${pod}`) as any;
    item.metadata.annotations["gradiated.com/qualification-error"] =
      "runpod://4242:2026-10-22T08:00:00Z";
    const pinned = pins(NEW_IMAGE, NEW_BUNDLE);

    await run(fleet, pinned, () => rollout(fleet, FIRST)?.step === "Apply");
    await run(fleet, pinned, () => false, {}, 10);

    expect(rollout(fleet, FIRST)).toMatchObject({ step: "Apply" });
    expect(fleet.host(FIRST).status?.rollout?.bundle).toBeUndefined();
  });

  it("fails and holds the fleet when the host rejects the bundle", async () => {
    const { fleet } = bundleFleet();
    // The host without serving pods goes first.
    fleet.sim(SECOND).rejects.add(NEW_BUNDLE);
    const metrics: Metrics = createMetrics();

    await run(
      fleet,
      pins(NEW_IMAGE, NEW_BUNDLE),
      () => rollout(fleet, SECOND)?.result === "Failed",
      { metrics },
    );
    await run(fleet, pins(NEW_IMAGE, NEW_BUNDLE), () => false, { metrics }, 10);

    expect(rollout(fleet, SECOND)?.lastError).toBe(
      `The host rejected or rolled back bundle ${NEW_BUNDLE}`,
    );
    expect(rollout(fleet, FIRST)).toBeUndefined();
    expect(
      await metrics.registry.getSingleMetricAsString(
        "gradiated_gpu_host_update_failed",
      ),
    ).toContain(`gradiated_gpu_host_update_failed{instance_id="${SECOND}"} 1`);
  });
});

describe("hosts that stop answering", () => {
  it("waits out a provider network outage instead of re-imaging", async () => {
    const fleet = kevFleet();
    await fleet.observe();
    fleet.sim(FIRST).outage = true;
    fleet.tick();
    fleet.advance(5 * 60 * 60_000);

    await run(fleet, pins(OLD_IMAGE, OLD_BUNDLE), () => false, {}, 30);

    expect(rollout(fleet, FIRST)).toBeUndefined();
    expect(fleet.sim(FIRST).resets).toBe(0);
    expect(fleet.host(FIRST).status?.plan).toMatch(
      /^Waiting: Unreachable since .*; the container has not been replaced$/,
    );
  });

  it.each([
    [
      "the management key is not mounted",
      (fleet: Simulation) => {
        fleet.sim(SPARE).pingError = "The host management key is not mounted";
      },
    ],
    [
      "the egress path to the host is broken",
      (fleet: Simulation) => {
        fleet.sim(SPARE).egressDown = true;
      },
    ],
  ])("never re-images a running host when %s", async (_case, breakPing) => {
    const fleet = kevFleet();
    await fleet.observe();
    breakPing(fleet);
    fleet.advance(60 * 60_000);

    await run(fleet, pins(OLD_IMAGE, OLD_BUNDLE), () => false, {}, 30);

    expect(rollout(fleet, SPARE)).toBeUndefined();
    expect(fleet.sim(SPARE).resets).toBe(0);
  });

  it("re-enrolls a host whose container was wiped", async () => {
    const fleet = kevFleet();
    await fleet.observe();
    fleet.advance(5 * 60_000);
    fleet.wipe(SPARE);
    fleet.advance(15 * 60_000);

    await run(
      fleet,
      pins(OLD_IMAGE, OLD_BUNDLE),
      () => rollout(fleet, SPARE)?.result === "Succeeded",
    );

    expect(rollout(fleet, SPARE)).toMatchObject({
      kind: "recover",
      result: "Succeeded",
    });
    expect(fleet.sim(SPARE)).toMatchObject({ state: "enrolled", resets: 1 });
  });

  it("enrolls a new GpuHost that has never answered", async () => {
    const fleet = simulateFleet(
      [
        {
          instanceId: SPARE,
          podId: "yzno396wdsidu4",
          gpus: 4,
          enrolled: false,
          image: NEW_IMAGE,
        },
      ],
      [],
    );

    await run(
      fleet,
      pins(NEW_IMAGE, NEW_BUNDLE),
      () => rollout(fleet, SPARE)?.result === "Succeeded",
    );

    expect(rollout(fleet, SPARE)).toMatchObject({
      kind: "enroll",
      result: "Succeeded",
    });
    expect(fleet.sim(SPARE)).toMatchObject({
      state: "enrolled",
      bundle: NEW_BUNDLE,
    });
  });
});

describe("observe mode", () => {
  it("reports what it would re-image and changes nothing", async () => {
    const fleet = kevFleet();
    const before = fleet.kube.calls.length;

    await run(
      fleet,
      pins(NEW_IMAGE, NEW_BUNDLE),
      () => false,
      { mode: "observe" },
      10,
    );

    expect(fleet.host(SPARE).status?.plan).toBe(
      "Would reimage: The pod runs " + OLD_IMAGE + ", not the pinned image",
    );
    expect(rollout(fleet, SPARE)).toBeUndefined();
    expect([...fleet.sims.values()].every((host) => host.resets === 0)).toBe(
      true,
    );
    const writes = fleet.kube.calls
      .slice(before)
      .filter((call) => call.method !== "GET" && call.method !== "LIST");
    expect(writes.every((call) => call.path.endsWith("/status"))).toBe(true);
  });
});
