import { describe, expect, it } from "vitest";

import { entered, fillConcurrencyCap } from "./admission.js";
import { expectRejected } from "./assertions.js";
import { useCases } from "./case.js";
import { deferred } from "./eventually.js";
import { ORGANIZATION_CONCURRENCY_CAP } from "./gateway-process.js";
import { RUNTIME_KINDS } from "./mock-runtimes/server.js";

const { makeCase } = useCases();

describe.each(RUNTIME_KINDS)("%s request lifecycle", (kind) => {
  // Concurrency is a capacity limit, not a billing one: without the cap, one
  // invoiced tenant could hold unlimited generations and starve the fleet.
  it.each(["prepaid", "invoiced"] as const)(
    "rejects concurrency over the organization cap without dispatching (%s)",
    async (billingMode) => {
      const instance = await makeCase(kind);
      if (billingMode === "invoiced") {
        await instance.setTenant({ billingMode, balance: -1 });
      }

      const held = await fillConcurrencyCap(instance);
      try {
        expectRejected(await instance.post(), { code: "concurrency_exceeded" });
        expect(instance.runtimes[0]!.calls).toHaveLength(
          ORGANIZATION_CONCURRENCY_CAP,
        );
      } finally {
        held.release();
      }

      for (const request of held.requests) {
        const response = await request;
        expect(response.status).toBe(200);
        await instance.settled(response);
      }
      expect(await instance.settlements()).toHaveLength(
        ORGANIZATION_CONCURRENCY_CAP,
      );
    },
  );

  it("cancels on the deadline and releases admission", async () => {
    const instance = await makeCase(kind);
    const gate = deferred();
    instance.runtimes[0]!.enqueue({ gate });

    try {
      const response = await instance.post();

      expectRejected(response, { code: "runtime_unavailable" });
      const properties = await instance.settled(response, {
        status: "cancelled",
        charge: 0,
      });
      expect(properties.outcome).toMatchObject({
        cancellation_owner: "server",
      });
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
      await entered(plan);
      // The gateway creates the account hash when it first reads the account,
      // so capture it only once a request has reached admission.
      restore = await instance.redis.hGetAll(instance.accountKey);

      // The finalization Lua script cannot modify an invalid account.
      await instance.redis.hSet(
        instance.accountKey,
        "balance",
        "not-an-integer",
      );
      gate.resolve();

      const response = await request;
      expectRejected(response, { code: "finalization_unavailable" });
      expect(await instance.settlements()).toEqual([]);
      expect(await instance.redis.zRange(instance.inflightKey, 0, -1)).toEqual([
        response.headers["x-gradiated-generation-id"],
      ]);
      expect(await instance.redis.hGet(instance.accountKey, "balance")).toBe(
        "not-an-integer",
      );
    } finally {
      gate.resolve();
      if (restore) await instance.redis.hSet(instance.accountKey, restore);
      // Deliberately failed settlement leaves an expiring lease, by design.
      // Clean up only this test tenant's lease after asserting that behaviour.
      await instance.redis.del(instance.inflightKey);
    }
  });
});

it("gives independent tenants independent admission", async () => {
  const first = await makeCase("kev");
  const second = await makeCase("kev");

  const held = await fillConcurrencyCap(first);
  try {
    expectRejected(await first.post(), { code: "concurrency_exceeded" });

    const response = await second.post();

    expect(response.status).toBe(200);
    await second.settled(response);
  } finally {
    held.release();
  }

  for (const request of held.requests) {
    expect((await request).status).toBe(200);
  }
});
