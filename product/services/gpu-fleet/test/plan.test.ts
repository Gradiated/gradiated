import { describe, expect, it } from "vitest";

import type { GpuHost } from "../src/hosts.js";
import { planHost, type HostFacts } from "../src/plan.js";
import {
  NEW_BUNDLE,
  NEW_IMAGE,
  OLD_BUNDLE,
  OLD_IMAGE,
  pins,
} from "./support/simulation.js";

const NOW = new Date("2026-10-22T12:00:00Z");
const ago = (minutes: number) =>
  new Date(NOW.getTime() - minutes * 60_000).toISOString();
const ID = "01a0f19d-1ff3-7613-8cbf-81b693c0f0d4";

const host = (lastSeen?: string, created = ago(60 * 24)) =>
  ({
    metadata: { name: `gpu-${ID}`, uid: "u", creationTimestamp: created },
    spec: {
      instanceId: ID,
      provider: { name: "runpod", accountId: "a", podId: "pod1" },
      inventory: { gpuProduct: "B300", gpuCount: 4, cpu: 64, memoryGiB: 896 },
      managementSecret: { key: "k" },
    },
    ...(lastSeen && { status: { observed: { lastSeen } } }),
  }) as GpuHost;

const pod = (fields: Record<string, unknown> = {}) =>
  ({
    id: "pod1",
    consumerUserId: "a",
    machineId: "m",
    gpuCount: 4,
    vcpuCount: 64,
    desiredStatus: "RUNNING",
    imageName: OLD_IMAGE,
    lastStartedAt: ago(60 * 24),
    machine: {},
    ...fields,
  }) as never;

const answering = (bundle: string) => ({
  reachable: true as const,
  instanceId: ID,
  hostBundleSha256: bundle,
  previousHostBundleSha256: "",
  failedHostBundleSha256: "",
  stagingFailedHostBundleSha256: "",
  trial: false,
});
const silent = {
  reachable: false as const,
  error: "The host agent is unreachable",
  silent: true,
};

const facts = (
  fields: { [K in keyof HostFacts]?: HostFacts[K] | undefined } = {},
): HostFacts => ({
  host: host(ago(60)),
  observation: silent,
  pod: pod(),
  tailnet: { connected: false, lastSeen: ago(60) },
  servingPods: 0,
  trainingPods: 0,
  pods: 0,
  ...(fields as Partial<HostFacts>),
});

const current = pins(OLD_IMAGE, OLD_BUNDLE);
const next = pins(NEW_IMAGE, NEW_BUNDLE);

describe("planning a host that answers", () => {
  it("re-images a host on another image before touching its bundle", () => {
    const live = { host: host(ago(1)), observation: answering(OLD_BUNDLE) };
    expect(planHost(facts(live), next, NOW)).toMatchObject({
      action: "start",
      kind: "reimage",
    });
    expect(
      planHost(
        facts({ ...live, pod: pod({ imageName: NEW_IMAGE }) }),
        next,
        NOW,
      ),
    ).toMatchObject({ action: "start", kind: "bundle" });
    expect(
      planHost(
        facts({
          ...live,
          observation: answering(NEW_BUNDLE),
          pod: pod({ imageName: NEW_IMAGE }),
        }),
        next,
        NOW,
      ),
    ).toEqual({ action: "none" });
  });

  it("does not re-image a host running a training job", () => {
    expect(
      planHost(
        facts({
          host: host(ago(1)),
          observation: answering(OLD_BUNDLE),
          trainingPods: 1,
        }),
        next,
        NOW,
      ),
    ).toMatchObject({
      action: "wait",
      reason: expect.stringContaining("training job"),
    });
  });

  it("does nothing it cannot verify without RunPod", () => {
    const { pod: _pod, ...withoutPod } = facts({
      host: host(ago(1)),
      observation: answering(OLD_BUNDLE),
    });
    expect(planHost(withoutPod, next, NOW)).toMatchObject({ action: "wait" });
  });
});

describe("planning a host that does not answer", () => {
  // Each of these looks like a dead host from the operator's side alone.
  it.each([
    [
      "the management key is not mounted",
      {
        observation: {
          reachable: false as const,
          error: "The host management key is not mounted",
          silent: false,
        },
      },
    ],
    [
      "the host agent answered with an error",
      {
        observation: {
          reachable: false as const,
          error: "The host agent answered ping with 403",
          silent: false,
        },
      },
    ],
    [
      "the egress path is down but the device is connected",
      { tailnet: { connected: true } },
    ],
    [
      "the device is connected under a suffixed MagicDNS name",
      { tailnet: { connected: true, lastSeen: ago(90) } },
    ],
    ["Tailscale could not be read", { tailnet: undefined }],
  ])("never re-images when %s", (_case, fields) => {
    for (const target of [host(ago(60)), host(undefined, ago(60))])
      expect(
        planHost(
          facts({
            host: target,
            pod: pod({ lastStartedAt: ago(30) }),
            ...fields,
          }),
          current,
          NOW,
        ).action,
      ).toBe("wait");
  });

  it("waits out a provider network outage, however long: the container keeps running", () => {
    // Three RTX hosts on one RunPod machine were cut off for hours on 2026-10-22.
    const outage = facts({
      host: host(ago(5 * 60)),
      pod: pod({ lastStartedAt: ago(60 * 24 * 2) }),
      tailnet: { connected: false, lastSeen: ago(5 * 60) },
    });
    expect(planHost(outage, current, NOW)).toMatchObject({
      action: "wait",
      reason: expect.stringContaining("not been replaced"),
    });
  });

  it("does not treat a container that restarted and rejoined before losing its network as wiped", () => {
    // Status lastSeen can lag the last answer; the device's own contact with
    // control after the restart shows the container kept its identity.
    const rejoined = facts({
      host: host(ago(40)),
      pod: pod({ lastStartedAt: ago(38) }),
      tailnet: { connected: false, lastSeen: ago(30) },
    });
    expect(planHost(rejoined, current, NOW)).toMatchObject({ action: "wait" });
  });

  it("recovers a wiped container: restarted after the host went silent and never seen since", () => {
    expect(
      planHost(
        facts({ host: host(ago(60)), pod: pod({ lastStartedAt: ago(30) }) }),
        current,
        NOW,
      ),
    ).toMatchObject({ action: "start", kind: "recover" });
    expect(
      planHost(
        facts({
          host: host(ago(30)),
          pod: pod({ lastStartedAt: ago(30.5) }),
          tailnet: { connected: false, lastSeen: ago(30) },
        }),
        current,
        NOW,
      ),
    ).toMatchObject({ action: "start", kind: "recover" });
    expect(
      planHost(
        facts({ host: host(ago(60)), pod: pod({ lastStartedAt: ago(2) }) }),
        current,
        NOW,
      ),
    ).toMatchObject({ action: "wait" });
  });

  it("leaves a stopped pod to a person", () => {
    expect(
      planHost(
        facts({
          pod: pod({ desiredStatus: "EXITED", lastStartedAt: ago(30) }),
        }),
        current,
        NOW,
      ),
    ).toMatchObject({
      action: "wait",
      reason: expect.stringContaining("EXITED"),
    });
  });

  it("enrolls a GpuHost that has never answered once its grace period passes, unless its device came online", () => {
    const never = { connected: false };
    expect(
      planHost(
        facts({ host: host(undefined, ago(2)), tailnet: never }),
        current,
        NOW,
      ),
    ).toMatchObject({ action: "wait" });
    expect(
      planHost(
        facts({ host: host(undefined, ago(20)), tailnet: never }),
        current,
        NOW,
      ),
    ).toMatchObject({ action: "start", kind: "enroll" });
    expect(
      planHost(
        facts({
          host: host(undefined, ago(20)),
          tailnet: { connected: false, lastSeen: ago(5) },
        }),
        current,
        NOW,
      ),
    ).toMatchObject({ action: "wait" });
    // A device from before the GpuHost existed (a reused pod) does not count.
    expect(
      planHost(
        facts({
          host: host(undefined, ago(20)),
          tailnet: { connected: false, lastSeen: ago(60) },
        }),
        current,
        NOW,
      ),
    ).toMatchObject({ action: "start", kind: "enroll" });
  });
});
