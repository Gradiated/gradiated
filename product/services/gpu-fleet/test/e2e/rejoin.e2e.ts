import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import {
  createRunPodClient,
  socksConnector,
  sshRunner,
} from "@gradiated/gpu-hosts";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { createCluster } from "../../src/cluster.js";
import { createEnrollment } from "../../src/enroll.js";
import { GPU_HOSTS, NODES, type GpuHost } from "../../src/hosts.js";
import { createMetrics } from "../../src/metrics.js";
import { pingHost, type Observation } from "../../src/observe.js";
import { pinsSchema, type Pins } from "../../src/pins.js";
import { createRollouts } from "../../src/rollout.js";
import { fakeKubernetes } from "../support/kubernetes.js";
import {
  assets,
  docker,
  egressByName,
  headscaleNames,
  INFERENCE_TAG,
  startTailnet,
  type Tailnet,
} from "./tailnet.js";

// Headscale keeps a node through re-authentication, so Tailscale's new-device
// rule and -1 renaming are left to the stateful fake in the rollout tests.
const files = assets();
const INSTANCE = "019e0a00-0000-7000-8000-00000000e2e0";
const POD = "e2epod1";
const ECR =
  "873716897517.dkr.ecr.us-east-1.amazonaws.com/gradiated/prod/gpu-base";
const TOKEN = `e2e_${"m".repeat(40)}`;

describe.skipIf(!files)("a GPU host rejoining after a re-image", () => {
  let tailnet: Tailnet;
  let egress: Awaited<ReturnType<typeof egressByName>>;
  const keys = mkdtempSync(path.join(tmpdir(), "gpu-fleet-e2e-keys-"));
  const kube = fakeKubernetes();
  const podName = () => `${tailnet.network}-pod-${POD}`;
  const steps: string[] = [];

  // RunPod as the operator sees it: any update resets the pod and starts a
  // fresh container from the image with the new environment.
  const pod = {
    id: POD,
    consumerUserId: "user_e2e",
    machineId: "machine-e2e",
    gpuCount: 2,
    vcpuCount: 32,
    desiredStatus: "RUNNING",
    imageName: `${ECR}:gpu-base-inputs-${"0".repeat(64)}`,
    lastStartedAt: new Date().toISOString(),
    env: {} as Record<string, string>,
    machine: { dataCenterId: "E2E", gpuTypeId: "NVIDIA RTX PRO 6000" },
  };
  const boot = async () => {
    await docker("rm", "-f", podName()).catch(() => undefined);
    const environment = Object.entries({
      ...pod.env,
      RUNPOD_POD_ID: POD,
      GRADIATED_TAILSCALE_LOGIN_SERVER: "https://headscale",
    }).flatMap(([name, value]) => ["-e", `${name}=${value}`]);
    // Runtime tasks move themselves into pod cgroups, which needs a writable tree.
    await docker(
      "run",
      "-d",
      "--platform",
      "linux/amd64",
      "--privileged",
      "--network",
      tailnet.network,
      "--name",
      podName(),
      ...environment,
      files!.image,
    );
    pod.lastStartedAt = new Date().toISOString();
  };
  const runpod = createRunPodClient({
    apiKey: "e2e",
    userAgent: "gpu-fleet-e2e",
    fetch: (async (input: string | URL | Request, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      if (method === "GET")
        return Response.json({
          id: pod.id,
          status: pod.desiredStatus,
          image: pod.imageName,
          startedAt: pod.lastStartedAt,
          env: pod.env,
          mounts: {},
          dataCenterId: pod.machine.dataCenterId,
          gpu: {
            id: pod.machine.gpuTypeId,
            count: pod.gpuCount,
            vcpuCount: pod.vcpuCount,
          },
        });
      if (method === "PATCH") {
        const body = JSON.parse(String(init?.body)) as {
          image: string;
          env: Record<string, string>;
        };
        pod.imageName = body.image;
        pod.env = body.env;
        await boot();
        return new Response("");
      }
      return new Response(null, { status: 400 });
    }) as typeof fetch,
  });

  // Two pinned image versions; the fake RunPod boots the same test image for both.
  const pins = (version: "a" | "b"): Pins =>
    pinsSchema.parse({
      image: `${ECR}:gpu-base-inputs-${version.repeat(64)}`,
      imageDigest: `sha256:${version.repeat(64)}`,
      hostBundle: files!.hostBundle,
    });
  const host = () => kube.read(`${GPU_HOSTS}/gpu-${INSTANCE}`) as GpuHost;
  const ping = (): Promise<Observation> =>
    pingHost(INSTANCE, keys, () => egress.endpoint);
  const devices = async () =>
    (await tailnet.nodes()).filter(
      (node) =>
        node.name === `gpu-${INSTANCE}` ||
        node.given_name.startsWith(`gpu-${INSTANCE}`),
    );

  // One engine per pass, as after an operator restart or a change of leader:
  // every step resumes from GpuHost status alone.
  const converge = async (pinned: Pins, pause?: (step: string) => boolean) => {
    const enrollment = createEnrollment({
      runpod,
      tailnet: {
        status: tailnet.status,
        run: sshRunner(socksConnector("127.0.0.1", tailnet.socksPort)),
      },
      bootstrapKey: () => tailnet.mint("tag:gpu-bootstrap"),
      inferenceKey: () => tailnet.mint(INFERENCE_TAG),
      revokeKey: async (_client, id) => {
        await tailnet.expire(id);
      },
      ...headscaleNames(tailnet),
      managementKey: async () => TOKEN,
      bundleUrl: async (sha256) => `https://artifacts/${sha256}.tar.gz`,
      apiEndpoint: tailnet.sidecarAddress,
    });
    const deadline = Date.now() + 25 * 60_000;
    let paused = false;
    while (Date.now() < deadline) {
      const observation = await ping();
      // gpu-controller marks a host's Node Ready while its agent answers.
      await kube.api.mergePatch(`${NODES}/gpu-${INSTANCE}/status`, {
        status: {
          conditions: [
            { type: "Ready", status: observation.reachable ? "True" : "False" },
          ],
        },
      });
      if (observation.reachable)
        await kube.api.mergePatch(`${GPU_HOSTS}/gpu-${INSTANCE}/status`, {
          status: {
            observed: { reachable: true, lastSeen: new Date().toISOString() },
          },
        });
      const rollout = host().status?.rollout;
      if (rollout?.result === "Failed")
        throw new Error(
          `The rollout failed at ${rollout.step}: ${rollout.lastError}`,
        );
      const running = rollout?.result === "Running" ? rollout.step : undefined;
      if (running && steps.at(-1) !== running) steps.push(running);
      if (
        rollout?.result === "Succeeded" &&
        rollout.target.image === pinned.image &&
        observation.reachable &&
        observation.hostBundleSha256 === pinned.hostBundle.sha256
      )
        return;
      const step = running;
      // The operator is down for a while mid-rollout; the next one resumes.
      if (step && !paused && pause?.(step)) {
        paused = true;
        await new Promise((resolve) => setTimeout(resolve, 20_000));
      }
      await createRollouts({
        api: kube.api,
        cluster: createCluster(kube.api, () => undefined),
        ping,
        pins: async () => pinned,
        enrollment: async () => enrollment,
        modelStatuses: async () => new Map(),
        mode: "act",
        leading: () => true,
        identity: "gpu-fleet-e2e",
        log: () => undefined,
        metrics: createMetrics(),
        limits: { soakFor: 5_000 },
      }).pass();
      await new Promise((resolve) => setTimeout(resolve, 2_000));
    }
    throw new Error(`The host did not converge; steps: ${steps.join(", ")}`);
  };

  beforeAll(async () => {
    tailnet = await startTailnet(files!);
    egress = await egressByName(tailnet.socksPort, INSTANCE);
    writeFileSync(path.join(keys, INSTANCE), TOKEN);
    kube.seed(GPU_HOSTS, {
      apiVersion: "fleet.gradiated.com/v1alpha1",
      kind: "GpuHost",
      metadata: {
        name: `gpu-${INSTANCE}`,
        creationTimestamp: new Date(Date.now() - 86_400_000).toISOString(),
      },
      spec: {
        instanceId: INSTANCE,
        provider: { name: "runpod", accountId: "user_e2e", podId: POD },
        inventory: {
          gpuProduct: "RTX-PRO-6000",
          gpuCount: 2,
          cpu: 16,
          memoryGiB: 64,
        },
        managementSecret: {
          key: `gradiated/prod/platform/gpu-host/${INSTANCE}`,
        },
      },
    });
    kube.seed(NODES, {
      metadata: { name: `gpu-${INSTANCE}` },
      spec: {},
      status: { conditions: [{ type: "Ready", status: "False" }] },
    });
    // A new RunPod pod runs the base image before it has a bootstrap key.
    await boot();
  }, 300_000);

  afterAll(async () => {
    await egress?.close();
    await tailnet?.stop();
    rmSync(keys, { recursive: true, force: true });
  }, 120_000);

  let first: { address: string; container: string };

  it("enrolls a new host under its exact gpu-<id> name", async () => {
    await converge(pins("a"));
    expect(steps).toEqual(
      expect.arrayContaining([
        "Reimage",
        "Join",
        "Enroll",
        "Promote",
        "Verify",
        "Soak",
      ]),
    );
    const observation = await ping();
    expect(observation).toMatchObject({
      reachable: true,
      instanceId: INSTANCE,
    });
    const [device, ...others] = await devices();
    expect(others).toEqual([]);
    expect(device).toMatchObject({
      name: `gpu-${INSTANCE}`,
      given_name: `gpu-${INSTANCE}`,
    });
    expect(device!.tags).toEqual([INFERENCE_TAG]);
    first = {
      address: device!.ip_addresses.find((ip) => ip.includes("."))!,
      container: await docker("inspect", "--format", "{{.Id}}", podName()),
    };
  }, 1_800_000);

  it("rejoins under the same identity and name after a re-image, resuming after an operator restart", async () => {
    const spec = structuredClone(host().spec);
    steps.length = 0;
    await converge(
      pins("b"),
      (step) => step === "Enroll" || step === "Promote",
    );
    expect(steps).toEqual(
      expect.arrayContaining([
        "Reimage",
        "Join",
        "Enroll",
        "Promote",
        "Verify",
        "Soak",
      ]),
    );
    // A new container, so a new tailnet device; the old one was removed.
    expect(await docker("inspect", "--format", "{{.Id}}", podName())).not.toBe(
      first.container,
    );
    const [device, ...others] = await devices();
    expect(others).toEqual([]);
    expect(device).toMatchObject({
      name: `gpu-${INSTANCE}`,
      given_name: `gpu-${INSTANCE}`,
    });
    expect(device!.ip_addresses).not.toContain(first.address);
    // Reached by its unchanged MagicDNS name, gpu-<id>.tailnet.test.
    expect(await ping()).toMatchObject({
      reachable: true,
      instanceId: INSTANCE,
    });
    // Same identity; nothing in git or the GpuHost spec changed.
    expect(host().spec).toEqual(spec);
    expect(host().status?.rollout).toMatchObject({
      kind: "reimage",
      result: "Succeeded",
      target: { image: pins("b").image },
    });
    expect(host().status?.rollout?.keys).toBeUndefined();
  }, 1_800_000);
});
