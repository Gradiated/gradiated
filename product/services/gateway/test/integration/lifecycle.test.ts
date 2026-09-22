import { describe, expect, it } from "vitest";

import { deferred, type RuntimeKind } from "./mock-runtimes/server.js";
import { entered, useCases } from "./support.js";

const { makeCase } = useCases();

describe.each(["kev", "vllm"] as RuntimeKind[])(
  "%s request lifecycle",
  (kind) => {
    it("rejects excess prepaid concurrency without dispatching", async () => {
      const instance = await makeCase(kind);
      const gates = [deferred(), deferred()];
      const plans = gates.map((gate) =>
        instance.runtimes[0]!.enqueue({ gate }),
      );
      const requests: Promise<Awaited<ReturnType<typeof instance.post>>>[] = [];
      try {
        for (const plan of plans) {
          requests.push(instance.post());
          await entered(plan);
        }
        const response = await instance.post();
        expect(response.status).toBe(429);
        expect(response.json().error.code).toBe("concurrency_exceeded");
        expect(instance.runtimes[0]!.calls).toHaveLength(2);
      } finally {
        for (const gate of gates) gate.resolve();
      }
      for (const request of requests) {
        const response = await request;
        expect(response.status).toBe(200);
        await instance.settled(response);
      }
      expect(await instance.settlements()).toHaveLength(2);
    });

    it("cancels on the deadline and releases admission", async () => {
      const instance = await makeCase(kind);
      const gate = deferred();
      instance.runtimes[0]!.enqueue({ gate });
      try {
        const response = await instance.post();
        expect(response.status).toBe(503);
        const properties = await instance.settled(response, "cancelled", 0);
        expect(
          (properties.outcome as Record<string, unknown>).cancellation_owner,
        ).toBe("server");
        expect(instance.runtimes[0]!.calls).toHaveLength(1);
      } finally {
        gate.resolve();
      }
      expect((await instance.post()).status).toBe(200);
    });

    it("withholds success and does not debit when settlement fails", async () => {
      const instance = await makeCase(kind);
      const gate = deferred();
      const plan = instance.runtimes[0]!.enqueue({ gate });
      let restore: Record<string, string> | undefined;
      const request = instance.post();
      try {
        await entered(plan); // Admission already succeeded.
        // The gateway creates the account hash when it first reads the account,
        // so capture it only once a request has reached admission.
        const account = await instance.redis.hGetAll(instance.accountKey);
        // An invalid account cannot be modified by the finalization Lua script.
        await instance.redis.hSet(
          instance.accountKey,
          "balance",
          "not-an-integer",
        );
        gate.resolve();
        const response = await request;
        expect(response.status).toBe(503);
        expect(response.json().error.code).toBe("finalization_unavailable");
        expect(await instance.settlements()).toEqual([]);
        const inflight = `inflight:{settlement-0}:${instance.organization}`;
        expect(await instance.redis.zRange(inflight, 0, -1)).toEqual([
          response.headers["x-generation-id"],
        ]);
        expect(await instance.redis.hGet(instance.accountKey, "balance")).toBe(
          "not-an-integer",
        );
        restore = account;
      } finally {
        gate.resolve();
        if (restore) await instance.redis.hSet(instance.accountKey, restore);
        // Deliberately failed settlement leaves an expiring lease, by design.
        // Clean up only this test tenant's lease after asserting that behaviour.
        await instance.redis.del(
          `inflight:{settlement-0}:${instance.organization}`,
        );
      }
    });
  },
);

it("gives independent tenants independent admission", async () => {
  const first = await makeCase("kev");
  const second = await makeCase("kev");
  const gates = [deferred(), deferred()];
  const plans = gates.map((gate) => first.runtimes[0]!.enqueue({ gate }));
  const requests: Promise<Awaited<ReturnType<typeof first.post>>>[] = [];
  try {
    for (const plan of plans) {
      requests.push(first.post());
      await entered(plan);
    }
    expect((await first.post()).status).toBe(429);
    const response = await second.post();
    expect(response.status).toBe(200);
    await second.settled(response);
  } finally {
    for (const gate of gates) gate.resolve();
  }
  for (const request of requests) {
    expect((await request).status).toBe(200);
  }
});
