import { describe, expect, it } from "vitest";

import { createCluster } from "../src/cluster.js";
import {
  createGrad,
  GRAD_HOLDER,
  parseGradConfig,
  unmetDemand,
  type GradConfig,
  type TrainerStatus,
  type Trainers,
  type WorkerTokens,
} from "../src/grad.js";
import { LEASE_ANNOTATION, ROLLOUTS, SCALED_OBJECTS } from "../src/hosts.js";
import { createMetrics, type Metrics } from "../src/metrics.js";
import { createRollouts } from "../src/rollout.js";
import {
  OLD_BUNDLE,
  OLD_IMAGE,
  pins,
  simulateFleet,
  type Simulation,
} from "./support/simulation.js";

const SPARE = "01a0f19d-1ff3-7613-8cbf-81b693c0f0d4";
const FIRST = "01a0fbf7-5276-700b-903b-7e04da150ed6";
const SECOND = "01a0fbf8-06fc-7658-96e1-ae72f7dba135";
const THIRD = "01a0fbf9-0a1b-7c2d-8e3f-4a5b6c7d8e9f";
const CURRENT = pins(OLD_IMAGE, OLD_BUNDLE);
const RUNTIME = "c".repeat(64);
const MINUTE = 60_000;

const enabled = (overrides: Record<string, string> = {}) =>
  parseGradConfig({
    GRAD_ENABLED: "true",
    GRAD_BUFFER_GPUS: "0",
    GRAD_MAX_HOSTS: "2",
    GRAD_GPU_PRODUCTS: "B300",
    GRAD_DRAIN_GRACE_SECONDS: "90",
    GRAD_PROMETHEUS_URL: "http://prometheus.monitoring:9090",
    GRAD_INTERNAL_URL: "http://grad-internal.training:8789",
    GRAD_SERVER_URL: "http://grad-worker.tail186117.ts.net:8788",
    GRAD_ORCHESTRATOR_KEY_FILE: "/var/run/secrets/grad/orchestrator-key",
    GRAD_TRAINER_RUNTIME: RUNTIME,
    ...overrides,
  });

// The host agent's trainers, one per GPU. A stopped trainer checkpoints and
// exits after `exitAfter`; a re-image removes them.
const fakeTrainers = (fleet: Simulation, exitAfter = 30_000) => {
  const hosts = new Map<
    string,
    {
      leaseId: string;
      token: string;
      gpus: number;
      stoppedAt?: number;
      resets: number;
    }
  >();
  const events: string[] = [];
  const current = (id: string) => {
    const entry = hosts.get(id);
    // The return's re-image wipes the trainers with everything else.
    if (entry && fleet.sim(id).resets !== entry.resets) hosts.delete(id);
    return hosts.get(id);
  };
  const trainers: Trainers = {
    status: async (host): Promise<TrainerStatus> => {
      const entry = current(host.spec.instanceId);
      if (!entry) return { leaseId: null, staged: true, workers: [] };
      const exited =
        entry.stoppedAt !== undefined &&
        fleet.now().getTime() - entry.stoppedAt >= exitAfter;
      return {
        leaseId: entry.leaseId,
        staged: true,
        workers: Array.from({ length: entry.gpus }, (_, gpu) => ({
          gpu: `GPU-${gpu}`,
          state: exited
            ? "exited"
            : entry.stoppedAt !== undefined
              ? "draining"
              : "running",
        })),
      };
    },
    start: async (host, request) => {
      const id = host.spec.instanceId;
      expect(fleet.podsOn(id)).toEqual([]);
      events.push(`start ${id}`);
      hosts.set(id, {
        leaseId: request.leaseId,
        token: request.token,
        gpus: host.spec.inventory.gpuCount,
        resets: fleet.sim(id).resets,
      });
      return trainers.status(host);
    },
    stop: async (host, grace) => {
      const entry = current(host.spec.instanceId);
      expect(grace).toBe(90);
      if (!entry || entry.stoppedAt !== undefined) return;
      events.push(`stop ${host.spec.instanceId}`);
      entry.stoppedAt = fleet.now().getTime();
    },
  };
  return { trainers, hosts, events };
};

const fakeTokens = (fleet: Simulation, events: string[]) => {
  const minted: {
    token: string;
    hostId: string;
    leaseId: string;
    gpuMemoryGb: number;
    expiresAt: Date;
    revoked: boolean;
  }[] = [];
  const tokens: WorkerTokens = {
    mint: async (input) => {
      const token = `gradwt_${String(minted.length).padStart(20, "0")}`;
      minted.push({ ...input, token, revoked: false });
      return token;
    },
    revoke: async (leaseId) => {
      events.push(`revoke ${leaseId} after ${fleet.sim(SPARE).resets} wipes`);
      const mine = minted.filter((entry) => entry.leaseId === leaseId);
      for (const entry of mine) entry.revoked = true;
      return mine.length;
    },
  };
  return { tokens, minted };
};

const gradFleet = (spares = [SPARE], serving = 1) => {
  const fleet = simulateFleet(
    [
      ...spares.map((instanceId, index) => ({
        instanceId,
        podId: `spare${index}pod0000`,
        gpus: 2,
      })),
      { instanceId: FIRST, podId: "zhimpngvqyotuj", gpus: serving },
      { instanceId: SECOND, podId: "dv31b4wrd2yc8n", gpus: serving },
    ],
    [{ name: "kev", gpus: 1, replicas: 2 }],
  );
  fleet.place("kev", FIRST);
  fleet.place("kev", SECOND);
  return fleet;
};

const setup = (
  fleet: Simulation,
  config: GradConfig = enabled(),
  demand: { jobs: number | undefined } = { jobs: 0 },
) => {
  const trainers = fakeTrainers(fleet);
  const tokens = fakeTokens(fleet, trainers.events);
  const metrics = createMetrics();
  const grad = createGrad({
    api: fleet.kube.api,
    cluster: createCluster(fleet.kube.api, () => undefined),
    config,
    demand: async () => {
      if (demand.jobs === undefined) throw new Error("no samples");
      return new Map([[80, demand.jobs]]);
    },
    trainers: trainers.trainers,
    tokens: tokens.tokens,
    mode: "act",
    leading: () => true,
    log: () => undefined,
    metrics,
    now: fleet.now,
  });
  return { grad, demand, metrics, ...trainers, ...tokens };
};

// Each pass uses a fresh rollout engine, so rollouts resume from GpuHost
// status alone; grad's demand windows live in its one instance.
const run = async (
  fleet: Simulation,
  grad: ReturnType<typeof createGrad>,
  until: () => boolean,
  passes = 400,
  metrics: Metrics = createMetrics(),
) => {
  for (let pass = 0; pass < passes && !until(); pass++) {
    const rollouts = createRollouts({
      api: fleet.kube.api,
      cluster: createCluster(fleet.kube.api, () => undefined),
      ping: fleet.ping,
      pins: async () => CURRENT,
      enrollment: async () => fleet.enrollment,
      modelStatuses: async () => new Map(),
      mode: "act",
      leading: () => true,
      identity: "gpu-fleet-a",
      log: () => undefined,
      metrics,
      now: fleet.now,
      limits: { soakFor: 60_000, unschedulable: 10 * MINUTE },
      grad,
    });
    await fleet.observe();
    await rollouts.pass().catch(() => undefined);
    fleet.tick();
  }
};

const request = (fleet: Simulation, id: string) => {
  const value = fleet.host(id).metadata.annotations?.[LEASE_ANNOTATION];
  return value ? (JSON.parse(value) as { holder: string }) : undefined;
};
const heldByGrad = (fleet: Simulation, id: string) => () =>
  fleet.host(id).status?.lease?.holder === GRAD_HOLDER;
const returned = (fleet: Simulation, id: string) => () =>
  fleet.host(id).status?.rollout?.kind === "return" &&
  fleet.host(id).status?.rollout?.result === "Succeeded";

const scale = (fleet: Simulation, model: string, replicas: number) => {
  fleet.kube.objects.get(`${ROLLOUTS}/${model}`)!.spec = { replicas };
  (
    fleet.kube.objects.get(`${SCALED_OBJECTS}/${model}`)!.spec as {
      minReplicaCount: number;
    }
  ).minReplicaCount = replicas;
};

describe("grad tenancy", () => {
  it("is off by default and hands back what grad holds when off", async () => {
    const config = parseGradConfig({});
    expect(config).toMatchObject({ enabled: false, maxHosts: 0 });

    const fleet = gradFleet();
    const { grad, minted } = setup(fleet, config, { jobs: 20 });
    await run(fleet, grad, () => false, 30);

    expect(request(fleet, SPARE)).toBeUndefined();
    expect(fleet.host(SPARE).status?.lease).toBeUndefined();
    expect(minted).toEqual([]);

    // A grad request left from when it was on is withdrawn; a person's is not.
    fleet.annotateLease(SPARE, {
      holder: GRAD_HOLDER,
      purpose: "grad training",
      until: new Date(fleet.now().getTime() + 60 * MINUTE).toISOString(),
    });
    fleet.annotateLease(FIRST, {
      holder: "research-agent",
      purpose: "SFT sweep",
      until: new Date(fleet.now().getTime() + 60 * MINUTE).toISOString(),
    });
    await run(fleet, grad, () => false, 1);
    expect(request(fleet, SPARE)).toBeUndefined();
    expect(request(fleet, FIRST)?.holder).toBe("research-agent");
  });

  it("needs its settings, a host cap and a GPU product to be enabled", () => {
    expect(() => parseGradConfig({ GRAD_ENABLED: "true" })).toThrow(
      /GRAD_PROMETHEUS_URL/,
    );
    expect(() => enabled({ GRAD_MAX_HOSTS: "0" })).toThrow(/GRAD_MAX_HOSTS/);
    expect(() => enabled({ GRAD_GPU_PRODUCTS: "" })).toThrow(
      /GRAD_GPU_PRODUCTS/,
    );
    expect(() => enabled({ GRAD_GPU_PRODUCTS: "A100" })).toThrow(
      /unknown GPU product/,
    );
    expect(enabled({ GRAD_GPU_PRODUCTS: "H100, B300" }).products).toEqual([
      "H100",
      "B300",
    ]);
  });

  it("leases a spare host on demand, wipes it, and runs a trainer per GPU under a lease token", async () => {
    const fleet = gradFleet();
    const { grad, demand, minted, hosts, metrics } = setup(fleet);
    demand.jobs = 2;

    // Demand must hold for two minutes before a host is taken.
    await run(fleet, grad, () => request(fleet, SPARE) !== undefined, 3);
    expect(request(fleet, SPARE)).toBeUndefined();
    await run(fleet, grad, () => request(fleet, SPARE) !== undefined, 10);
    expect(request(fleet, SPARE)).toMatchObject({
      holder: GRAD_HOLDER,
      preemptible: true,
    });

    await run(fleet, grad, heldByGrad(fleet, SPARE));
    // Serving to training is a switch: the host was re-imaged before grad got it.
    expect(fleet.sim(SPARE).resets).toBe(1);
    expect(fleet.node(SPARE).spec?.unschedulable).toBe(true);
    expect(fleet.ready("kev")).toBe(2);

    await run(fleet, grad, () => hosts.has(SPARE), 2);
    const since = Date.parse(fleet.host(SPARE).status!.lease!.since);
    expect(minted).toEqual([
      expect.objectContaining({
        hostId: SPARE,
        leaseId: `${SPARE}.${since}`,
        gpuMemoryGb: 288,
      }),
    ]);
    expect(minted[0]!.expiresAt.getTime()).toBeLessThanOrEqual(
      since + 24 * 60 * MINUTE,
    );
    expect(hosts.get(SPARE)).toMatchObject({
      leaseId: `${SPARE}.${since}`,
      token: minted[0]!.token,
      gpus: 2,
    });

    // Running trainers are left alone: no second token.
    await run(fleet, grad, () => false, 10);
    expect(minted).toHaveLength(1);
    expect(
      await metrics.registry.getSingleMetricAsString(
        "gradiated_gpu_fleet_grad_gpus",
      ),
    ).toContain('state="leased"} 2');
  });

  it("gives a grad host back at once when a model replica needs it: drain, revoke, wipe, return", async () => {
    const fleet = gradFleet();
    const { grad, demand, minted, hosts, events } = setup(fleet);
    demand.jobs = 2;
    await run(fleet, grad, () => hosts.has(SPARE));

    scale(fleet, "kev", 3);
    const pending = fleet.now().getTime();
    await run(fleet, grad, () => request(fleet, SPARE) === undefined, 10);
    // Thirty seconds, not the ten minutes a person's lease waits.
    expect(fleet.now().getTime() - pending).toBeLessThanOrEqual(2 * MINUTE);
    expect(events.at(-1)).toBe(`stop ${SPARE}`);

    await run(fleet, grad, returned(fleet, SPARE));
    const since = minted[0]!.leaseId;
    // The trainers stopped and the tokens were revoked before the re-image.
    expect(events).toEqual([
      `start ${SPARE}`,
      `stop ${SPARE}`,
      `revoke ${since} after 1 wipes`,
    ]);
    expect(minted.every((entry) => entry.revoked)).toBe(true);
    expect(fleet.sim(SPARE).resets).toBe(2);
    expect(fleet.host(SPARE).status?.lease).toBeUndefined();

    await run(fleet, grad, () => fleet.ready("kev") === 3, 60);
    expect(fleet.podsOn(SPARE)).toHaveLength(1);
    // The replica's host is not leased again while it serves.
    await run(fleet, grad, () => false, 20);
    expect(request(fleet, SPARE)).toBeUndefined();
    expect(fleet.violations).toEqual([]);
  });

  it("revokes nothing it cannot and still returns the host", async () => {
    const fleet = gradFleet();
    const idle = setup(fleet);
    idle.demand.jobs = 1;
    await run(fleet, idle.grad, () => idle.hosts.has(SPARE));
    idle.tokens.revoke = async () => {
      throw new Error("grad is down");
    };
    idle.demand.jobs = 0;

    // Idle for fifteen minutes, then handed back like any return.
    const metrics = createMetrics();
    await run(fleet, idle.grad, returned(fleet, SPARE), 80, metrics);
    expect(returned(fleet, SPARE)()).toBe(true);
    expect(
      await metrics.registry.getSingleMetricAsString(
        "gradiated_gpu_fleet_grad_events_total",
      ),
    ).toContain('event="token_revoke_failed"} 1');
    expect(fleet.sim(SPARE).resets).toBe(2);
    expect(fleet.node(SPARE).spec?.unschedulable).toBeFalsy();
  });

  it("keeps a host whose wipe failed during a grad lease cordoned, and wipes it again on the way back", async () => {
    const fleet = gradFleet();
    const { grad, demand, hosts } = setup(fleet);
    demand.jobs = 1;
    // RunPod accepts the re-image but never finishes pulling the image.
    fleet.sim(SPARE).pullFor = 10 * 60 * MINUTE;
    await run(
      fleet,
      grad,
      () => fleet.host(SPARE).status?.rollout?.result === "Failed",
    );

    expect(fleet.host(SPARE).status?.rollout).toMatchObject({
      kind: "lease",
      reimageRequestedAt: expect.any(String),
    });
    expect(fleet.node(SPARE).spec?.unschedulable).toBe(true);
    expect(fleet.host(SPARE).status?.lease?.holder).toBe(GRAD_HOLDER);
    expect(request(fleet, SPARE)).toBeUndefined();
    expect(hosts.has(SPARE)).toBe(false);

    demand.jobs = 0;
    delete fleet.sim(SPARE).pullFor;
    await run(fleet, grad, returned(fleet, SPARE));
    expect(fleet.host(SPARE).status?.lease).toBeUndefined();
    expect(fleet.node(SPARE).spec?.unschedulable).toBeFalsy();
    expect(hosts.has(SPARE)).toBe(false);
  });

  it("leases no more than GRAD_MAX_HOSTS hosts, one at a time", async () => {
    const fleet = gradFleet([
      SPARE,
      THIRD,
      "01a0fbfa-0a1b-7c2d-8e3f-4a5b6c7d8e9f",
    ]);
    const { grad, demand, hosts } = setup(fleet);
    demand.jobs = 20;

    await run(fleet, grad, () => hosts.size === 2, 200);
    await run(fleet, grad, () => false, 60);

    const ids = [SPARE, THIRD, "01a0fbfa-0a1b-7c2d-8e3f-4a5b6c7d8e9f"];
    expect(
      ids.filter((id) => request(fleet, id)?.holder === GRAD_HOLDER),
    ).toHaveLength(2);
    expect(hosts.size).toBe(2);
  });

  it("keeps the serving buffer and holds its leases while demand is unknown", async () => {
    // FIRST and SECOND each have one GPU free for serving.
    const fleet = gradFleet([SPARE], 2);
    const { grad, demand } = setup(fleet, enabled({ GRAD_BUFFER_GPUS: "3" }));
    demand.jobs = 4;
    await run(fleet, grad, () => false, 20);
    expect(request(fleet, SPARE)).toBeUndefined();

    const roomy = gradFleet([SPARE], 2);
    const second = setup(roomy, enabled({ GRAD_BUFFER_GPUS: "2" }));
    second.demand.jobs = 4;
    await run(roomy, second.grad, heldByGrad(roomy, SPARE));
    second.demand.jobs = undefined;
    await run(roomy, second.grad, () => false, 40);
    expect(heldByGrad(roomy, SPARE)()).toBe(true);
  });
});

describe("unmetDemand", () => {
  const host = (gpuProduct: string, gpuCount: number) =>
    ({ spec: { inventory: { gpuProduct, gpuCount } } }) as never;

  it("fills the largest memory classes first from GPUs big enough", () => {
    expect(unmetDemand(new Map([[80, 2]]), [host("H100", 2)])).toBeUndefined();
    expect(unmetDemand(new Map([[80, 3]]), [host("H100", 2)])).toEqual({
      memoryGb: 80,
      gpus: 1,
    });
    expect(
      unmetDemand(
        new Map([
          [80, 1],
          [141, 1],
        ]),
        [host("H100", 1), host("H200", 1)],
      ),
    ).toBeUndefined();
    expect(unmetDemand(new Map([[141, 1]]), [host("H100", 8)])).toEqual({
      memoryGb: 141,
      gpus: 1,
    });
    expect(unmetDemand(new Map([[80, 1]]), [host("L40S", 4)])).toEqual({
      memoryGb: 80,
      gpus: 1,
    });
  });
});
