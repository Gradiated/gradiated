import { describe, expect, it } from "vitest";

import { hostState, LEASE_ANNOTATION, type GpuHost } from "../src/hosts.js";

const host = (
  status: GpuHost["status"],
  extra: Partial<GpuHost["spec"]> = {},
  annotations?: Record<string, string>,
): GpuHost => ({
  metadata: { name: "gpu-h", uid: "u", ...(annotations && { annotations }) },
  spec: {
    instanceId: "01a0f19d-1ff3-7613-8cbf-81b693c0f0d4",
    provider: { name: "runpod", accountId: "a", podId: "p" },
    inventory: {
      gpuProduct: "NVIDIA B300",
      gpuCount: 4,
      cpu: 64,
      memoryGiB: 512,
    },
    managementSecret: { key: "k" },
    ...extra,
  },
  status,
});

const rollout = (kind: string, result: string) =>
  ({
    kind,
    result,
    target: { image: "i", hostBundle: "b" },
    step: "s",
    startedAt: "2026-11-09T00:00:00Z",
    stepStartedAt: "2026-11-09T00:00:00Z",
  }) as unknown as NonNullable<GpuHost["status"]>["rollout"];

const lease = {
  holder: "agent",
  purpose: "sweep",
  since: "2026-11-09T00:00:00Z",
};
const request = JSON.stringify({
  holder: "agent",
  purpose: "sweep",
  until: "2099-01-01T00:00:00Z",
  preemptible: true,
});

describe("host state", () => {
  it.each([
    ["in_pool", host({ phase: "Ready" })],
    [
      "reserved",
      host(
        { phase: "Ready" },
        { extraTaints: [{ key: "gradiated.com/reserved", value: "kimi-k31" }] },
      ),
    ],
    ["leasing", host({ phase: "Ready" }, {}, { [LEASE_ANNOTATION]: request })],
    ["leasing", host({ phase: "Ready", rollout: rollout("lease", "Running") })],
    [
      "leased",
      host({ phase: "Ready", lease, rollout: rollout("lease", "Succeeded") }),
    ],
    [
      "returning",
      host({ phase: "Ready", lease, rollout: rollout("return", "Running") }),
    ],
    [
      "degraded",
      host({ phase: "Ready", lease, rollout: rollout("return", "Failed") }),
    ],
    [
      "updating",
      host({ phase: "Ready", rollout: rollout("bundle", "Running") }),
    ],
    ["updating", host({ phase: "Pending" })],
    ["updating", host({ phase: "Draining" })],
    ["degraded", host({ phase: "Degraded" })],
    [
      "degraded",
      host({
        phase: "Degraded",
        lease,
        rollout: rollout("lease", "Succeeded"),
      }),
    ],
    [
      "degraded",
      host({ phase: "Degraded", rollout: rollout("bundle", "Running") }),
    ],
    ["updating", host(undefined)],
    ["updating", host({})],
  ] as const)("is %s", (expected, value) => {
    expect(hostState(value)).toBe(expected);
  });

  it("is cordoned when a person cordons a serving host, and still leased or updating otherwise", () => {
    const cordon = { unschedulable: true };
    expect(hostState(host({ phase: "Ready" }), cordon)).toBe("cordoned");
    expect(
      hostState(
        host(
          { phase: "Ready" },
          {
            extraTaints: [{ key: "gradiated.com/reserved", value: "kimi-k31" }],
          },
        ),
        cordon,
      ),
    ).toBe("cordoned");
    expect(
      hostState(
        host({ phase: "Ready", lease, rollout: rollout("lease", "Succeeded") }),
        cordon,
      ),
    ).toBe("leased");
    expect(
      hostState(
        host({ phase: "Ready", rollout: rollout("bundle", "Running") }),
        cordon,
      ),
    ).toBe("updating");
    expect(hostState(host({ phase: "Ready" }), { unschedulable: false })).toBe(
      "in_pool",
    );
  });
});
