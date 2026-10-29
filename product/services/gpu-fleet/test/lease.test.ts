import { describe, expect, it } from "vitest";

import { createLease } from "../src/lease.js";
import { fakeKubernetes } from "./support/kubernetes.js";

const LEASES = "/apis/coordination.k8s.io/v1/namespaces/gpu-inference/leases";

describe("operator leadership", () => {
  const setup = () => {
    const cluster = fakeKubernetes();
    let time = new Date("2026-10-22T12:00:00Z");
    const replica = (identity: string) =>
      createLease({
        api: cluster.api,
        namespace: "gpu-inference",
        name: "gpu-fleet",
        identity,
        durationSeconds: 60,
        now: () => time,
      });
    return {
      cluster,
      replica,
      advance: (seconds: number) => {
        time = new Date(time.getTime() + seconds * 1000);
      },
    };
  };

  it("lets one replica lead and keeps it leading while it renews", async () => {
    const { cluster, replica, advance } = setup();
    const a = replica("gpu-fleet-a");
    const b = replica("gpu-fleet-b");

    expect(await a.acquire()).toBe(true);
    expect(await b.acquire()).toBe(false);
    advance(50);
    expect(await a.acquire()).toBe(true);
    advance(50);
    expect(await b.acquire()).toBe(false);
    expect(cluster.read(`${LEASES}/gpu-fleet`)?.spec).toMatchObject({
      holderIdentity: "gpu-fleet-a",
      leaseTransitions: 0,
    });
  });

  it("hands leadership to another replica when the leader stops renewing", async () => {
    const { cluster, replica, advance } = setup();
    const a = replica("gpu-fleet-a");
    const b = replica("gpu-fleet-b");
    await a.acquire();

    advance(61);
    expect(await b.acquire()).toBe(true);
    expect(await a.acquire()).toBe(false);
    expect(cluster.read(`${LEASES}/gpu-fleet`)?.spec).toMatchObject({
      holderIdentity: "gpu-fleet-b",
      leaseTransitions: 1,
    });
  });

  it("frees the lease on shutdown so another replica leads at once", async () => {
    const { replica } = setup();
    const a = replica("gpu-fleet-a");
    const b = replica("gpu-fleet-b");
    await a.acquire();
    await b.release();
    expect(await b.acquire()).toBe(false);

    await a.release();
    expect(await b.acquire()).toBe(true);
  });

  it("loses a race to take an expired lease instead of leading twice", async () => {
    const { cluster, replica, advance } = setup();
    await replica("gpu-fleet-a").acquire();
    advance(61);
    const b = replica("gpu-fleet-b");
    // gpu-fleet-c reads the expired lease, then gpu-fleet-b takes it before
    // gpu-fleet-c writes.
    const c = createLease({
      api: {
        ...cluster.api,
        replace: async (path, body) => {
          await b.acquire();
          return cluster.api.replace(path, body);
        },
      },
      namespace: "gpu-inference",
      name: "gpu-fleet",
      identity: "gpu-fleet-c",
      durationSeconds: 60,
      now: () => new Date("2026-10-22T12:01:01Z"),
    });

    expect(await c.acquire()).toBe(false);
    expect(cluster.read(`${LEASES}/gpu-fleet`)?.spec).toMatchObject({
      holderIdentity: "gpu-fleet-b",
    });
  });
});
