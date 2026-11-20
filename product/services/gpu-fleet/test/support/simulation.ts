import {
  claimInstanceName,
  instanceTailnet,
  ENROLL_COMMAND,
  enrollmentPayloadSchema,
  releaseInstanceName,
  RunPodError,
  type RunPodClient,
  type RunSsh,
  type TailnetStatus,
} from "@gradiated/gpu-hosts";

import { DELETION_COST, PAUSED_REPLICAS } from "../../src/cluster.js";
import { uncordonIfReturned } from "../../src/drain.js";
import { createEnrollment } from "../../src/enroll.js";
import {
  GPU_HOSTS,
  LEASE_ANNOTATION,
  NODES,
  PODS,
  ROLLOUTS,
  SCALED_OBJECTS,
  type GpuHost,
} from "../../src/hosts.js";
import type { Observation } from "../../src/observe.js";
import type { Pins } from "../../src/pins.js";
import { fakeKubernetes } from "./kubernetes.js";
import { virtualKubeletStatus } from "./pods.js";

const IMAGE = (tag: string) =>
  `873716897517.dkr.ecr.us-east-1.amazonaws.com/gradiated/prod/inference:${tag}`;
export const OLD_IMAGE = IMAGE("gpu-base-v2");
export const NEW_IMAGE = IMAGE("gpu-base-v3");
export const OLD_BUNDLE = "a".repeat(64);
export const NEW_BUNDLE = "b".repeat(64);
const SSH_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHN5bnRoZXRpYw==";
const DOMAIN = "tail186117.ts.net";

export const pins = (image: string, sha256: string): Pins => ({
  image,
  imageDigest: `sha256:${(image === NEW_IMAGE ? "3" : "2").repeat(64)}`,
  hostBundle: { sha256, baseId: image === NEW_IMAGE ? "v3" : "v2" },
});

export type HostSpec = {
  instanceId: string;
  podId: string;
  gpus: number;
  image?: string;
  bundle?: string;
  enrolled?: boolean;
  // A RunPod volume, which survives a re-image.
  volumeInGb?: number;
  hasAttachedVolumes?: boolean;
  // An EC2 instance, whose podId is its instance ID, instead of a RunPod pod.
  provider?: "aws";
};

type Device = {
  nodeId: string;
  name: string;
  hostname: string;
  addresses: string[];
  tags: string[];
  created: string;
  connectedToControl: boolean;
  lastSeen?: string;
};

type Host = HostSpec & {
  state:
    "enrolled" | "pulling" | "booting" | "bootstrap" | "promoting" | "silent";
  image: string;
  bundle: string;
  failed: string;
  outage: boolean;
  desiredStatus: string;
  lastStartedAt: string;
  env: Record<string, string>;
  bootstrapIp?: string;
  inferenceKey?: string;
  enrolledBundle?: string;
  enrollFails?: string;
  rejects: Set<string>;
  resets: number;
  // The operator's ping fails for its own reason: the host itself is fine.
  pingError?: string;
  // The egress path to the host is broken; the host and its device are fine.
  egressDown?: boolean;
  // How long RunPod takes to pull a new image before the container starts.
  pullFor?: number;
  pulledAt?: number;
  // The next update fails: with an HTTP status, or a lost connection without
  // one; applied says whether RunPod made the change anyway.
  updateFails?: { status?: number; applied: boolean };
};

type Model = { name: string; gpus: number; replicas: number };
const TRAINING: Model = { name: "training", gpus: 1, replicas: 0 };

/**
 * One cluster and its GPU hosts, advanced in ticks. Each tick, KEDA applies a
 * paused replica count, ReplicaSets add or remove pods (unscheduled, then not
 * Ready, then lowest deletion cost first), the scheduler places pods on
 * schedulable Ready nodes with free GPUs, pods become Ready a tick later, and
 * the controller applies each host's rollout bundle in place. Hosts re-imaged
 * through RunPod lose their container, join the tailnet as gpu-bootstrap-<pod>
 * with their single-use key, run the real enrollment contract over "SSH", and
 * re-authenticate as gpu-<id>, where Tailscale renames a taken name to -1.
 */
export const simulateFleet = (hosts: HostSpec[], models: Model[]) => {
  const kube = fakeKubernetes();
  let clock = Date.parse("2026-10-22T12:00:00Z");
  const now = () => new Date(clock);
  const devices = new Map<string, Device>();
  const keys = new Map<
    string,
    { key: string; tag: string; used: boolean; revoked: boolean }
  >();
  const sims = new Map<string, Host>();
  // Pods held not Ready, as a model still loading.
  const notReady = new Set<string>();
  const violations: string[] = [];
  const paused = new Set<string>();
  let next = 1;
  let podSerial = 0;

  const label = (device: Device) => device.name.split(".")[0]!;
  const offline = (device: Device) => {
    if (device.connectedToControl) device.lastSeen = now().toISOString();
    device.connectedToControl = false;
  };
  const join = (hostname: string, tag: string) => {
    let name = hostname;
    for (let n = 1; [...devices.values()].some((d) => label(d) === name); n++)
      name = `${hostname}-${n}`;
    const device: Device = {
      nodeId: `n${next}`,
      name: `${name}.${DOMAIN}`,
      hostname,
      addresses: [`100.64.0.${next + 10}`],
      tags: [tag],
      created: now().toISOString(),
      connectedToControl: true,
    };
    next++;
    devices.set(device.nodeId, device);
    return device;
  };
  const mint = (tag: string) => {
    const id = `k${next++}`;
    const key = `tskey-auth-${id}`;
    keys.set(id, { key, tag, used: false, revoked: false });
    return { key, id };
  };
  const consume = (key: string | undefined, tag: string) => {
    const entry = [...keys.values()].find((item) => item.key === key);
    if (!entry || entry.used || entry.revoked || entry.tag !== tag)
      return false;
    entry.used = true;
    return true;
  };
  const inference = (host: Host) =>
    [...devices.values()].find(
      (d) =>
        d.hostname === `gpu-${host.instanceId}` &&
        d.tags.includes("tag:gpu-inference") &&
        d.connectedToControl,
    );

  for (const spec of hosts) {
    const host: Host = {
      ...spec,
      state: spec.enrolled === false ? "silent" : "enrolled",
      image: spec.image ?? OLD_IMAGE,
      bundle: spec.bundle ?? OLD_BUNDLE,
      failed: "",
      outage: false,
      desiredStatus: "RUNNING",
      lastStartedAt: new Date(clock - 86_400_000).toISOString(),
      env: {},
      rejects: new Set(),
      resets: 0,
    };
    sims.set(spec.podId, host);
    if (host.state === "enrolled")
      join(`gpu-${spec.instanceId}`, "tag:gpu-inference");
    kube.seed(GPU_HOSTS, {
      apiVersion: "fleet.gradiated.com/v1alpha1",
      kind: "GpuHost",
      metadata: {
        name: `gpu-${spec.instanceId}`,
        creationTimestamp: new Date(clock - 86_400_000).toISOString(),
      },
      spec: {
        instanceId: spec.instanceId,
        provider:
          spec.provider === "aws"
            ? {
                name: "aws",
                accountId: "111122223333",
                region: "us-east-1",
                availabilityZone: "us-east-1b",
                ec2InstanceId: spec.podId,
              }
            : { name: "runpod", accountId: "user_test", podId: spec.podId },
        inventory: {
          gpuProduct: "B300",
          gpuCount: spec.gpus,
          cpu: 64,
          memoryGiB: 896,
        },
        managementSecret: {
          key: `gradiated/prod/platform/gpu-host/${spec.instanceId}`,
        },
      },
      ...(host.state === "enrolled" && {
        status: {
          phase: "Ready",
          observed: {
            reachable: true,
            lastSeen: new Date(clock - 60_000).toISOString(),
          },
        },
      }),
    });
    kube.seed(NODES, {
      metadata: { name: `gpu-${spec.instanceId}` },
      spec: {},
      status: { conditions: [{ type: "Ready", status: "True" }] },
    });
  }
  for (const model of models) {
    kube.seed(ROLLOUTS, {
      metadata: { name: model.name },
      spec: { replicas: model.replicas },
    });
    kube.seed(SCALED_OBJECTS, {
      metadata: { name: model.name, annotations: {} },
      spec: { minReplicaCount: model.replicas },
    });
  }

  const sim = (instanceId: string) =>
    [...sims.values()].find((h) => h.instanceId === instanceId)!;
  const reachable = (host: Host) =>
    host.state === "enrolled" && !host.outage && Boolean(inference(host));
  const objects = (collection: string) =>
    [...kube.objects.entries()]
      .filter(([key]) => key.slice(0, key.lastIndexOf("/")) === collection)
      .map(([key, item]) => ({ key, item: item as Record<string, any> }));

  // Each pod asks for its model's GPUs, as the real Rollouts do.
  const containers = (gpus: number) => [
    { resources: { limits: { "nvidia.com/gpu": String(gpus) } } },
  ];
  const addPod = (model: string, node?: string, ready = false) => {
    const name = `${model}-${++podSerial}`;
    const gpus = models.find((m) => m.name === model)!.gpus;
    kube.seed(PODS, {
      metadata: {
        name,
        labels: { "app.kubernetes.io/name": model },
        ownerReferences: [{ kind: "ReplicaSet", name: `${model}-rs` }],
        annotations: ready
          ? { "gradiated.com/qualified-runtime": `${name}:1` }
          : {},
        creationTimestamp: now().toISOString(),
      },
      spec: { ...(node && { nodeName: node }), containers: containers(gpus) },
      status: node
        ? virtualKubeletStatus(ready)
        : { phase: "Pending", conditions: [] },
    });
    return name;
  };
  const place = (model: string, instanceId: string) =>
    addPod(model, `gpu-${instanceId}`, true);
  // A training job: a bare pod, not owned by a ReplicaSet, using one GPU.
  const placeTraining = (instanceId: string) => {
    const name = `training-${++podSerial}`;
    kube.seed(PODS, {
      metadata: {
        name,
        labels: { "app.kubernetes.io/name": TRAINING.name },
        annotations: { "gradiated.com/workload-kind": "training" },
        creationTimestamp: now().toISOString(),
      },
      spec: {
        nodeName: `gpu-${instanceId}`,
        containers: containers(TRAINING.gpus),
      },
      status: virtualKubeletStatus(true),
    });
    return name;
  };
  // The container is replaced by a fresh one with no tailnet identity.
  const wipe = (instanceId: string) => {
    const host = sim(instanceId);
    host.state = "silent";
    host.lastStartedAt = now().toISOString();
    for (const d of devices.values())
      if (
        d.hostname === `gpu-${host.instanceId}` ||
        d.hostname === `gpu-bootstrap-${host.podId}`
      )
        offline(d);
  };

  const ready = (model: string) =>
    objects(PODS).filter(
      ({ item }) =>
        item.metadata.labels["app.kubernetes.io/name"] === model &&
        !item.metadata.deletionTimestamp &&
        item.status.conditions.some(
          (c: any) => c.type === "Ready" && c.status === "True",
        ),
    ).length;

  const tick = () => {
    clock += 30_000;

    for (const host of sims.values()) {
      if (host.state === "pulling" && clock >= host.pulledAt!) {
        host.state = "booting";
        host.lastStartedAt = now().toISOString();
      }
      if (
        host.state === "booting" &&
        consume(host.env.GRADIATED_TAILSCALE_BOOTSTRAP_KEY, "tag:gpu-bootstrap")
      ) {
        host.bootstrapIp = join(
          `gpu-bootstrap-${host.podId}`,
          "tag:gpu-bootstrap",
        ).addresses[0]!;
        host.state = "bootstrap";
      } else if (
        host.state === "promoting" &&
        consume(host.inferenceKey, "tag:gpu-inference")
      ) {
        for (const d of devices.values())
          if (d.addresses.includes(host.bootstrapIp ?? "")) offline(d);
        join(`gpu-${host.instanceId}`, "tag:gpu-inference");
        host.bundle = host.enrolledBundle!;
        host.state = "enrolled";
      }
      for (const d of devices.values())
        if (
          d.hostname === `gpu-${host.instanceId}` &&
          host.state === "enrolled" &&
          d === inference(host)
        ) {
          if (host.outage) offline(d);
          else d.connectedToControl = true;
        }
    }

    for (const { item } of objects(GPU_HOSTS)) {
      const host = sim(item.spec.instanceId);
      const bundle = item.status?.rollout?.bundle?.sha256;
      if (
        !bundle ||
        !reachable(host) ||
        bundle === host.bundle ||
        bundle === host.failed
      )
        continue;
      if (host.rejects.has(bundle)) host.failed = bundle;
      else host.bundle = bundle;
    }

    for (const { key, item } of objects(NODES)) {
      const host = sim(item.metadata.name.slice(4));
      kube.objects.set(key, {
        ...item,
        status: {
          conditions: [
            { type: "Ready", status: reachable(host) ? "True" : "False" },
          ],
        },
      } as never);
    }

    // KEDA holds a paused count; once unpaused it scales back to what its
    // triggers ask for, here the ScaledObject's minimum.
    for (const { item } of objects(SCALED_OBJECTS)) {
      const name = item.metadata.name as string;
      const count = item.metadata.annotations?.[PAUSED_REPLICAS];
      const rollout = kube.objects.get(`${ROLLOUTS}/${name}`)!;
      if (count !== undefined) {
        rollout.spec = { replicas: Number(count) };
        paused.add(name);
      } else if (paused.delete(name))
        rollout.spec = { replicas: item.spec.minReplicaCount };
    }

    for (const { key, item } of objects(PODS))
      if (item.metadata.deletionTimestamp) kube.objects.delete(key);

    for (const model of models) {
      const replicas = (
        kube.objects.get(`${ROLLOUTS}/${model.name}`)!.spec as {
          replicas: number;
        }
      ).replicas;
      const pods = objects(PODS).filter(
        ({ item }) =>
          item.metadata.labels["app.kubernetes.io/name"] === model.name,
      );
      for (let i = pods.length; i < replicas; i++) addPod(model.name);
      const rank = ({ item }: { item: any }) => [
        item.spec.nodeName ? 1 : 0,
        item.status.conditions.some(
          (c: any) => c.type === "Ready" && c.status === "True",
        )
          ? 1
          : 0,
        Number(item.metadata.annotations?.[DELETION_COST] ?? 0),
      ];
      const victims = [...pods]
        .sort((a, b) => {
          const [x, y] = [rank(a), rank(b)];
          return x[0]! - y[0]! || x[1]! - y[1]! || x[2]! - y[2]!;
        })
        .slice(0, Math.max(0, pods.length - replicas));
      for (const { item } of victims)
        item.metadata.deletionTimestamp = now().toISOString();
    }

    const used = (node: string) =>
      objects(PODS)
        .filter(({ item }) => item.spec.nodeName === node)
        .reduce(
          (sum, { item }) =>
            sum +
            (
              models.find(
                (m) =>
                  m.name === item.metadata.labels["app.kubernetes.io/name"],
              ) ?? TRAINING
            ).gpus,
          0,
        );
    for (const { item } of objects(PODS)) {
      const model =
        models.find(
          (m) => m.name === item.metadata.labels["app.kubernetes.io/name"],
        ) ?? TRAINING;
      if (item.spec.nodeName) {
        const node = kube.objects.get(`${NODES}/${item.spec.nodeName}`) as any;
        const isReady =
          node.status.conditions[0].status === "True" &&
          !item.metadata.deletionTimestamp &&
          !notReady.has(item.metadata.name);
        item.status = virtualKubeletStatus(isReady);
        if (isReady)
          item.metadata.annotations["gradiated.com/qualified-runtime"] ??=
            `${item.metadata.name}:1`;
        continue;
      }
      const target = objects(NODES).find(
        ({ item: node }) =>
          !node.spec?.unschedulable &&
          node.status.conditions[0].status === "True" &&
          sim(node.metadata.name.slice(4)).gpus - used(node.metadata.name) >=
            model.gpus,
      );
      if (target) {
        item.spec = { ...item.spec, nodeName: target.item.metadata.name };
        item.status = virtualKubeletStatus(false);
      } else if (
        !item.status.conditions.some((c: any) => c.type === "PodScheduled")
      )
        item.status.conditions.push({
          type: "PodScheduled",
          status: "False",
          reason: "Unschedulable",
          lastTransitionTime: now().toISOString(),
        });
    }

    for (const model of models)
      if (ready(model.name) < model.replicas)
        violations.push(
          `${now().toISOString()}: ${model.name} had ${ready(model.name)} Ready replicas`,
        );
  };

  const runpod = {
    pod: async (podId: string) => {
      const host = sims.get(podId)!;
      return {
        id: podId,
        consumerUserId: "user_test",
        machineId: `machine-${podId}`,
        gpuCount: host.gpus,
        vcpuCount: 64,
        desiredStatus: host.desiredStatus,
        imageName: host.image,
        lastStartedAt: host.lastStartedAt,
        env: { ...host.env },
        volumeInGb: host.volumeInGb ?? 0,
        hasAttachedVolumes: host.hasAttachedVolumes ?? false,
        machine: { dataCenterId: "US-TX-1", gpuTypeId: "NVIDIA B300" },
      };
    },
    // RunPod shows the new image at once; the container starts once it is
    // pulled.
    update: async (podId: string, body: Record<string, unknown>) => {
      const host = sims.get(podId)!;
      const fails = host.updateFails;
      delete host.updateFails;
      if (!fails || fails.applied) {
        host.image = body.imageName as string;
        host.env = body.env as Record<string, string>;
        host.resets++;
        if (host.pullFor) {
          host.state = "pulling";
          host.pulledAt = clock + host.pullFor;
        } else {
          host.state = "booting";
          host.lastStartedAt = now().toISOString();
        }
        // The old container's devices drop off with it.
        for (const d of devices.values())
          if (
            d.hostname === `gpu-${host.instanceId}` ||
            d.hostname === `gpu-bootstrap-${host.podId}`
          )
            offline(d);
      }
      if (fails)
        throw fails.status
          ? new RunPodError(
              fails.status,
              `RunPod PATCH failed: ${fails.status}`,
            )
          : new Error("socket hang up");
    },
    start: async (podId: string) => {
      sims.get(podId)!.desiredStatus = "RUNNING";
    },
  } as unknown as RunPodClient;

  const status = async (): Promise<TailnetStatus> => ({
    Peer: Object.fromEntries(
      [...devices.values()].map((d) => [
        d.nodeId,
        {
          HostName: d.hostname,
          Created: d.created,
          TailscaleIPs: d.addresses,
          Tags: d.tags,
          Online: d.connectedToControl,
          sshHostKeys: [SSH_KEY],
        },
      ]),
    ),
  });

  const run: RunSsh = async (target, command, input) => {
    const host = [...sims.values()].find(
      (h) => h.state === "bootstrap" && h.bootstrapIp === target.host,
    );
    if (!host || command !== ENROLL_COMMAND)
      throw new Error("Tailnet connection to the GPU pod failed");
    if (host.enrollFails) throw new Error(host.enrollFails);

    const payload = enrollmentPayloadSchema.parse(JSON.parse(input ?? ""));
    host.inferenceKey = payload.auth_key;
    host.enrolledBundle = payload.host_bundle.sha256;
    host.state = "promoting";
    return JSON.stringify({
      version: 1,
      tailscale_ip: host.bootstrapIp,
      gpu_count: host.gpus,
      gpu_product: "B300",
      cpu: 57,
      memory_gib: 880,
      promotion: true,
    });
  };

  const control = (async (
    input: string | URL | Request,
    init?: RequestInit,
  ) => {
    const { pathname } = new URL(String(input));
    const path = pathname.replace("/api/v2", "");
    if (path === "/oauth/token")
      return Response.json({ access_token: "token" });
    if (path === "/tailnet/-/devices")
      return Response.json({ devices: [...devices.values()] });
    const [, , id, action] = path.split("/");
    const device = devices.get(id ?? "");
    if (!device) return new Response(null, { status: 404 });
    if (init?.method === "DELETE") {
      devices.delete(device.nodeId);
      return new Response(null, { status: 200 });
    }
    if (action === "name") {
      const { name } = JSON.parse(String(init?.body)) as { name: string };
      if ([...devices.values()].some((d) => d !== device && label(d) === name))
        return new Response(null, { status: 409 });
      device.name = `${name}.${DOMAIN}`;
      return new Response(null, { status: 200 });
    }
    return new Response(null, { status: 400 });
  }) as typeof fetch;
  const credentials = async () => ({
    client_id: "id",
    client_secret: "secret",
  });

  const enrollment = createEnrollment({
    runpod,
    tailnet: { status, run },
    instanceTailnet: (instanceId) =>
      instanceTailnet(instanceId, control, credentials),
    bootstrapKey: async () => mint("tag:gpu-bootstrap"),
    inferenceKey: async () => mint("tag:gpu-inference"),
    revokeKey: async (_client, id) => {
      keys.get(id)!.revoked = true;
    },
    releaseName: (instanceId) =>
      releaseInstanceName(instanceId, control, credentials),
    claimName: (instanceId, since) =>
      claimInstanceName(instanceId, since, control, credentials),
    managementKey: async () => "m".repeat(40),
    bundleUrl: async (sha256) => `https://artifacts.example/${sha256}.tar.gz`,
    apiEndpoint: "100.64.0.1",
  });

  const ping = async (instanceId: string): Promise<Observation> => {
    const host = sim(instanceId);
    if (host.pingError)
      return { reachable: false, error: host.pingError, silent: false };
    if (host.egressDown)
      return {
        reachable: false,
        error: "The host agent is unreachable",
        silent: true,
      };
    return reachable(host)
      ? {
          reachable: true,
          instanceId,
          hostBundleSha256: host.bundle,
          previousHostBundleSha256: "",
          failedHostBundleSha256: host.failed,
          stagingFailedHostBundleSha256: "",
          trial: false,
        }
      : {
          reachable: false,
          error: "The host agent is unreachable",
          silent: true,
        };
  };

  // Records that the operator saw the host answer, as the reconcile loop does.
  // As the fleet pass does: report reachable hosts, and undo the drain's
  // cordon of a host that is active again.
  const observe = async () => {
    for (const { item } of objects(GPU_HOSTS)) {
      await uncordonIfReturned(kube.api, item as GpuHost);
      if (reachable(sim(item.spec.instanceId)))
        await kube.api.mergePatch(`${GPU_HOSTS}/${item.metadata.name}/status`, {
          status: {
            observed: { reachable: true, lastSeen: now().toISOString() },
          },
        });
    }
  };

  // Writes or, given undefined, removes a host's lease annotation, as
  // gradctl gpu lease does.
  const annotateLease = (instanceId: string, request?: object) => {
    const host = kube.objects.get(`${GPU_HOSTS}/gpu-${instanceId}`)! as {
      metadata: { annotations?: Record<string, string> };
    };
    const { [LEASE_ANNOTATION]: _, ...rest } = host.metadata.annotations ?? {};
    host.metadata.annotations = request
      ? { ...rest, [LEASE_ANNOTATION]: JSON.stringify(request) }
      : rest;
  };

  // Someone cordons the node by hand, with no marker.
  const cordonByHand = (instanceId: string) => {
    kube.objects.get(`${NODES}/gpu-${instanceId}`)!.spec = {
      unschedulable: true,
    };
  };

  return {
    kube,
    now,
    advance: (ms: number) => {
      clock += ms;
    },
    tick,
    observe,
    sim,
    sims,
    devices,
    keys,
    violations,
    runpod,
    enrollment,
    ping,
    place,
    placeTraining,
    wipe,
    ready,
    host: (instanceId: string) =>
      kube.read(`${GPU_HOSTS}/gpu-${instanceId}`) as GpuHost,
    cordonByHand,
    annotateLease,
    notReady,
    node: (instanceId: string) =>
      kube.read(`${NODES}/gpu-${instanceId}`) as {
        metadata: { annotations?: Record<string, string> };
        spec?: { unschedulable?: boolean };
      },
    scaledObject: (model: string) =>
      kube.read(`${SCALED_OBJECTS}/${model}`) as {
        metadata: { annotations?: Record<string, string> };
      },
    podsOn: (instanceId: string) =>
      objects(PODS)
        .filter(({ item }) => item.spec.nodeName === `gpu-${instanceId}`)
        .map(({ item }) => item),
  };
};

export type Simulation = ReturnType<typeof simulateFleet>;
