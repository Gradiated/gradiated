import { describe, expect, it } from "vitest";

import type { GpuHost } from "../src/hosts.js";
import { leaseRefusal, planHost, type HostFacts } from "../src/plan.js";
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

describe("leases", () => {
  const leasedHost = (until: string | undefined) => {
    const leased = host(ago(60));
    leased.status = {
      ...leased.status,
      lease: { holder: "agent", purpose: "sweep", since: ago(30) },
    };
    if (until)
      leased.metadata.annotations = {
        "fleet.gradiated.com/lease": JSON.stringify({
          holder: "agent",
          purpose: "sweep",
          until,
        }),
      };
    return leased;
  };

  it("leaves a leased host that stopped answering alone instead of recovering it", () => {
    const later = new Date(NOW.getTime() + 60 * 60_000).toISOString();
    const plan = planHost(
      facts({
        host: leasedHost(later),
        pod: pod({ lastStartedAt: ago(20) }),
      }),
      pins(NEW_IMAGE, NEW_BUNDLE),
      NOW,
    );

    expect(plan).toEqual({
      action: "wait",
      reason: `Leased to agent until ${later}: sweep`,
    });
  });

  it("returns a leased host once its lease is handed back or expires", () => {
    for (const until of [undefined, ago(1)])
      expect(
        planHost(
          facts({
            host: leasedHost(until),
            observation: answering(OLD_BUNDLE),
          }),
          pins(OLD_IMAGE, OLD_BUNDLE),
          NOW,
        ),
      ).toMatchObject({ action: "start", kind: "return" });
  });
});

describe("planning an AWS host", () => {
  const ec2 = (
    lastSeen?: string,
    created?: string,
    status: Partial<NonNullable<GpuHost["status"]>> = {},
  ) => {
    const base = host(lastSeen, created);
    return {
      ...base,
      spec: {
        ...base.spec,
        provider: {
          name: "aws",
          accountId: "111122223333",
          region: "us-east-1",
          availabilityZone: "us-east-1b",
          ec2InstanceId: "i-0123456789abcdef0",
        },
        inventory: { gpuProduct: "L4", gpuCount: 1, cpu: 3, memoryGiB: 12 },
      },
      status: { ...base.status, ...status },
    } as GpuHost;
  };
  const instance = (fields: Record<string, unknown> = {}) =>
    ({
      id: "i-0123456789abcdef0",
      accountId: "111122223333",
      state: "running",
      availabilityZone: "us-east-1b",
      instanceType: "g6.xlarge",
      imageId: "ami-0abc",
      tags: { "gradiated:managed": "gpu-fleet" },
      ...fields,
    }) as never;
  const { pod: _pod, ...withoutPod } = facts();
  const aws = (fields: {
    [K in keyof HostFacts]?: HostFacts[K] | undefined;
  }): HostFacts => ({
    ...withoutPod,
    instance: instance(),
    ...(fields as Partial<HostFacts>),
  });

  it("waits while it has no recorded image, which the pass then records", () => {
    expect(
      planHost(
        aws({ host: ec2(ago(1)), observation: answering(OLD_BUNDLE) }),
        next,
        NOW,
      ),
    ).toEqual({
      action: "wait",
      reason:
        "Recording the pinned image as the one the host was adopted under",
    });
  });

  it("re-images a host adopted under an earlier pin", () => {
    expect(
      planHost(
        aws({
          host: ec2(ago(1), undefined, { adoptedUnder: OLD_IMAGE }),
          observation: answering(OLD_BUNDLE),
        }),
        next,
        NOW,
      ),
    ).toEqual({
      action: "start",
      kind: "reimage",
      reason: `The host was adopted under ${OLD_IMAGE}, and the pinned image has changed`,
    });
  });

  it("updates the bundle in place on a host re-imaged onto the pinned image", () => {
    const reimaged = ec2(ago(1), undefined, { image: NEW_IMAGE });
    expect(
      planHost(
        aws({ host: reimaged, observation: answering(OLD_BUNDLE) }),
        next,
        NOW,
      ),
    ).toMatchObject({ action: "start", kind: "bundle" });
    expect(
      planHost(
        aws({ host: reimaged, observation: answering(NEW_BUNDLE) }),
        next,
        NOW,
      ),
    ).toEqual({ action: "none" });
  });

  it("changes nothing it cannot read from EC2", () => {
    expect(
      planHost(
        aws({
          host: ec2(ago(1), undefined, { adoptedUnder: OLD_IMAGE }),
          observation: answering(OLD_BUNDLE),
          instance: undefined,
        }),
        next,
        NOW,
      ),
    ).toEqual({
      action: "wait",
      reason: "The instance's state is unknown without EC2 access",
    });
  });

  it("enrolls an instance that never answered, and leaves a stopped one to a person", () => {
    const fresh = ec2(undefined, ago(60));
    expect(
      planHost(aws({ host: fresh, tailnet: { connected: false } }), next, NOW),
    ).toMatchObject({ action: "start", kind: "enroll" });
    expect(
      planHost(
        aws({
          host: fresh,
          tailnet: { connected: false },
          instance: instance({ state: "stopped" }),
        }),
        next,
        NOW,
      ),
    ).toEqual({
      action: "wait",
      reason: "The instance is stopped; starting it is a person's decision",
    });
  });

  it("enrolls a fresh EC2 host before its management key is mounted", () => {
    const unkeyed = aws({
      host: ec2(undefined, ago(60)),
      observation: {
        reachable: false,
        error: "The host management key is not mounted",
        silent: false,
        keyMissing: true,
      },
      tailnet: { connected: false },
      instance: instance({ instanceProfileArn: "arn:bootstrap" }),
    });
    expect(planHost(unkeyed, next, NOW)).toMatchObject({
      action: "start",
      kind: "enroll",
    });

    for (const facts of [
      { ...unkeyed, host: ec2(ago(20), ago(60)) },
      { ...unkeyed, instance: instance() },
      aws({ ...unkeyed, tailnet: undefined }),
      { ...unkeyed, tailnet: { connected: true } },
      { ...unkeyed, pods: 1 },
      { ...unkeyed, node: { ready: true, unschedulable: false } as never },
    ])
      expect(planHost(facts, next, NOW)).toMatchObject({ action: "wait" });
  });

  it("recovers a silent host only after its own rollout replaced its root volume", () => {
    expect(planHost(aws({ host: ec2(ago(60)) }), next, NOW)).toMatchObject({
      action: "wait",
      reason: expect.stringContaining("its root volume was not replaced"),
    });

    const replaced = ec2(ago(30), undefined, {
      rollout: {
        kind: "reimage",
        target: {
          image: NEW_IMAGE,
          bundle: { sha256: NEW_BUNDLE, baseId: "v3" },
        },
        step: "Join",
        result: "Failed",
        startedAt: ago(35),
        stepStartedAt: ago(29),
        reimageRequestedAt: ago(30),
        rootVolumeTask: "replacevol-1",
      },
    });
    expect(planHost(aws({ host: replaced }), next, NOW)).toMatchObject({
      action: "start",
      kind: "recover",
    });
  });

  it("refuses a lease on an instance with storage a re-image would not wipe", () => {
    const leased = ec2(ago(1), undefined, { adoptedUnder: NEW_IMAGE });
    leased.metadata.annotations = {
      "fleet.gradiated.com/lease": JSON.stringify({
        holder: "agent",
        purpose: "sweep",
        until: new Date(NOW.getTime() + 60 * 60_000).toISOString(),
      }),
    };
    const node = { ready: true, unschedulable: false } as never;
    const live = {
      host: leased,
      observation: answering(NEW_BUNDLE),
      node,
      instanceStorage: false,
    };

    // An EBS-only type, such as m7i.large, can be leased.
    expect(
      leaseRefusal(
        aws({ ...live, instance: instance({ instanceType: "m7i.large" }) }),
        NOW,
      ),
    ).toBeUndefined();
    // g6.xlarge has a 250 GB NVMe instance store, which survives a re-image.
    expect(leaseRefusal(aws({ ...live, instanceStorage: true }), NOW)).toBe(
      "the g6.xlarge instance type has an instance store, which a re-image would not wipe",
    );
    expect(
      leaseRefusal(aws({ ...live, instanceStorage: undefined }), NOW),
    ).toBe("EC2 could not tell whether the instance type has instance storage");
    expect(
      leaseRefusal(
        aws({ ...live, instance: instance({ blockDevices: 2 }) }),
        NOW,
      ),
    ).toBe(
      "the instance has an EBS volume besides its root, which a re-image would not wipe",
    );
    expect(leaseRefusal(aws({ ...live, instance: undefined }), NOW)).toBe(
      "EC2 could not be read",
    );
  });
});
