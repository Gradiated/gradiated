import { describe, expect, it } from "vitest";

import { gpuHostSchema, type GpuHost } from "../src/hosts.js";
import { hostStatus } from "../src/status.js";
import { FIRST, gpuHost } from "./support/fleet.js";

const created = "2026-10-22T12:00:00.000Z";
const at = (seconds: number) => new Date(Date.parse(created) + seconds * 1000);
const host = (status?: GpuHost["status"]): GpuHost =>
  gpuHostSchema.parse({
    ...gpuHost(FIRST, "pod1"),
    metadata: {
      name: `gpu-${FIRST}`,
      uid: "uid-1",
      generation: 3,
      creationTimestamp: created,
    },
    status,
  });
const answering = {
  reachable: true as const,
  instanceId: FIRST,
  hostBundleSha256: "b".repeat(64),
};
const silent = {
  reachable: false as const,
  error: "The host agent is unreachable",
};
const condition = (status: GpuHost["status"], type: string) =>
  status?.conditions?.find((item) => item.type === type);

describe("GpuHost status", () => {
  it("is Ready with what the host reports once the agent answers", () => {
    const status = hostStatus(host(), { observation: answering }, at(10));
    expect(status).toMatchObject({
      observedGeneration: 3,
      phase: "Ready",
      observed: {
        reachable: true,
        lastSeen: at(10).toISOString(),
        hostBundleSha256: "b".repeat(64),
      },
    });
    expect(condition(status, "Ready")).toMatchObject({ status: "True" });
    expect(condition(status, "Degraded")).toMatchObject({ status: "False" });
  });

  it("is Pending for a new host until it answers, then Degraded after the grace period", () => {
    const fresh = hostStatus(host(), { observation: silent }, at(30));
    expect(fresh.phase).toBe("Pending");
    expect(condition(fresh, "Ready")).toMatchObject({ status: "Unknown" });

    const late = hostStatus(host(fresh), { observation: silent }, at(150));
    expect(late.phase).toBe("Degraded");
    expect(condition(late, "Degraded")).toMatchObject({
      status: "True",
      reason: "Unreachable",
      message: "The host agent is unreachable",
    });
  });

  it("rides out a short outage and keeps the last report", () => {
    const ready = hostStatus(host(), { observation: answering }, at(0));
    const blip = hostStatus(host(ready), { observation: silent }, at(60));
    expect(blip).toMatchObject({
      phase: "Ready",
      observed: {
        reachable: false,
        lastSeen: at(0).toISOString(),
        hostBundleSha256: "b".repeat(64),
      },
    });
    // The Ready condition has not flipped, so its transition time stands.
    expect(condition(blip, "Ready")?.lastTransitionTime).toBe(
      condition(ready, "Ready")?.lastTransitionTime,
    );

    const outage = hostStatus(host(blip), { observation: silent }, at(121));
    expect(outage.phase).toBe("Degraded");
    expect(condition(outage, "Ready")?.lastTransitionTime).toBe(
      at(121).toISOString(),
    );
  });

  it("reports a host answering for another instance", () => {
    const status = hostStatus(
      host(),
      { observation: { ...answering, instanceId: "someone-else" } },
      at(10),
    );
    expect(condition(status, "Degraded")).toMatchObject({
      status: "True",
      reason: "IdentityMismatch",
    });
  });

  it("puts a PostgreSQL conflict ahead of everything else", () => {
    const status = hostStatus(
      host(),
      {
        observation: answering,
        serviceError: "The egress Service could not be reconciled",
        conflict: "PostgreSQL records pod pod1 as instance other",
      },
      at(10),
    );
    expect(status.phase).toBe("Degraded");
    expect(condition(status, "Degraded")).toMatchObject({
      reason: "PostgresConflict",
      message: "PostgreSQL records pod pod1 as instance other",
    });
  });
});
