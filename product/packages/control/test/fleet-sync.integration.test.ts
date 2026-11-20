import { randomUUID } from "node:crypto";
import { eq } from "drizzle-orm";
import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";

import { instances } from "../src/db/schema/instances.js";
import {
  RETIRE_GRACE_MS,
  syncFleetInstances,
  type FleetHost,
} from "../src/instances/fleet-sync.js";
import { createInstanceService } from "../src/instances/service.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";

const host = (overrides: Partial<FleetHost> = {}): FleetHost => ({
  instanceId: randomUUID(),
  provider: "runpod",
  accountId: "user_test",
  providerInstanceId: randomUUID().slice(0, 14).replaceAll("-", "x"),
  sku: "8x B300",
  ...overrides,
});

// Late enough that rows created by the test are past the retirement grace.
const later = () => new Date(Date.now() + RETIRE_GRACE_MS + 60_000);

describe("instances follow the GPU fleet in Git", () => {
  let database: TestDatabase;
  const row = async (id: string) =>
    (
      await database.database
        .select()
        .from(instances)
        .where(eq(instances.id, id))
    )[0];

  beforeAll(async () => {
    database = await createTestDatabase();
  });
  beforeEach(async () => {
    await database.database.delete(instances);
  });
  afterAll(() => database.dispose());

  it("records missing hosts under their Git instance IDs, and a second pass changes nothing", async () => {
    const fleet = [host(), host()];
    const first = await syncFleetInstances(database.database, fleet);
    expect(first.inserted.sort()).toEqual(
      fleet.map((item) => item.instanceId).sort(),
    );
    expect(await row(fleet[0]!.instanceId)).toMatchObject({
      provider: "runpod",
      providerAccountId: "user_test",
      providerInstanceId: fleet[0]!.providerInstanceId,
      sku: "8x B300",
      retiredAt: null,
    });
    expect(
      await syncFleetInstances(database.database, fleet, { now: later() }),
    ).toEqual({
      inserted: [],
      restored: [],
      retired: [],
      updated: [],
      conflicts: [],
    });
  });

  it("retires an active row with no GpuHost and restores it when the host returns", async () => {
    const kept = host();
    const removed = host();
    await syncFleetInstances(database.database, [kept, removed]);

    const retired = await syncFleetInstances(database.database, [kept], {
      now: later(),
    });
    expect(retired.retired).toEqual([removed.instanceId]);
    expect((await row(removed.instanceId))?.retiredAt).toBeInstanceOf(Date);
    expect(
      (await syncFleetInstances(database.database, [kept], { now: later() }))
        .retired,
    ).toEqual([]);

    const restored = await syncFleetInstances(database.database, [
      kept,
      removed,
    ]);
    expect(restored.restored).toEqual([removed.instanceId]);
    expect((await row(removed.instanceId))?.retiredAt).toBeNull();
  });

  it("adopts a row ops-mcp registered under the same ID", async () => {
    const service = createInstanceService(database.database);
    const registered = await service.register({
      provider: "runpod",
      providerAccountId: "user_test",
      providerInstanceId: "registeredpod1",
      region: "EUR-IS-1",
      faultDomain: null,
      sku: "4x NVIDIA B300 SXM6 AC",
    });
    const result = await syncFleetInstances(database.database, [
      host({ instanceId: registered.id, providerInstanceId: "registeredpod1" }),
    ]);
    expect(result).toEqual({
      inserted: [],
      restored: [],
      retired: [],
      updated: [],
      conflicts: [],
    });
    expect(await row(registered.id)).toMatchObject({
      region: "EUR-IS-1",
      sku: "4x NVIDIA B300 SXM6 AC",
    });
  });

  it("records an EC2 host under its instance ID and zone fault domain", async () => {
    const ec2 = host({
      provider: "aws",
      accountId: "111122223333",
      providerInstanceId: "i-0123456789abcdef0",
      sku: "1x L4",
      region: "us-east-1",
      faultDomain: "aws:us-east-1b",
    });
    const result = await syncFleetInstances(database.database, [ec2, host()]);
    expect(result.inserted).toContain(ec2.instanceId);
    expect(await row(ec2.instanceId)).toMatchObject({
      provider: "aws",
      providerAccountId: "111122223333",
      providerInstanceId: "i-0123456789abcdef0",
      region: "us-east-1",
      faultDomain: "aws:us-east-1b",
      sku: "1x L4",
    });
  });

  it("fills the region of an existing row from the host and keeps a registered one when the host has none", async () => {
    const service = createInstanceService(database.database);
    const registered = await service.register({
      provider: "runpod",
      providerAccountId: "user_test",
      providerInstanceId: "registeredpod2",
      region: "EUR-IS-1",
      faultDomain: null,
      sku: "4x NVIDIA B300 SXM6 AC",
    });
    const ec2 = host({
      provider: "aws",
      accountId: "111122223333",
      providerInstanceId: "i-0fedcba9876543210",
      sku: "1x L4",
      faultDomain: "aws:us-east-1b",
    });
    await syncFleetInstances(database.database, [ec2]);
    expect((await row(ec2.instanceId))?.region).toBeNull();

    const runpod = host({
      instanceId: registered.id,
      providerInstanceId: "registeredpod2",
    });
    const fleet = [{ ...ec2, region: "us-east-1" }, runpod];
    expect(
      (await syncFleetInstances(database.database, fleet)).updated,
    ).toEqual([ec2.instanceId]);
    expect((await row(ec2.instanceId))?.region).toBe("us-east-1");
    expect((await row(registered.id))?.region).toBe("EUR-IS-1");
    expect(
      (await syncFleetInstances(database.database, fleet)).updated,
    ).toEqual([]);
  });

  it("reports a row that disagrees with Git and leaves it unchanged", async () => {
    const recorded = host();
    await syncFleetInstances(database.database, [recorded]);
    const moved = { ...recorded, providerInstanceId: "anotherpod1" };

    const result = await syncFleetInstances(database.database, [moved]);
    expect(result.conflicts).toEqual([
      {
        instanceId: recorded.instanceId,
        reason: `PostgreSQL records this instance as runpod instance ${recorded.providerInstanceId}`,
      },
    ]);
    expect((await row(recorded.instanceId))?.providerInstanceId).toBe(
      recorded.providerInstanceId,
    );
  });

  it("refuses to record a pod that another instance already holds", async () => {
    const recorded = host();
    await syncFleetInstances(database.database, [recorded]);
    const duplicate = host({ providerInstanceId: recorded.providerInstanceId });

    const result = await syncFleetInstances(database.database, [
      recorded,
      duplicate,
    ]);
    expect(result.conflicts).toEqual(
      expect.arrayContaining(
        [recorded, duplicate].map((item) => ({
          instanceId: item.instanceId,
          reason: `Several GpuHosts use runpod instance ${recorded.providerInstanceId}`,
        })),
      ),
    );
    expect(result.conflicts).toHaveLength(2);
    expect(await row(duplicate.instanceId)).toBeUndefined();
    expect((await row(recorded.instanceId))?.retiredAt).toBeNull();

    const alone = await syncFleetInstances(database.database, [duplicate]);
    expect(alone.conflicts).toEqual([
      {
        instanceId: duplicate.instanceId,
        reason: `PostgreSQL records runpod instance ${recorded.providerInstanceId} as instance ${recorded.instanceId}`,
      },
    ]);
    expect(await row(duplicate.instanceId)).toBeUndefined();
  });

  it("never writes the rows of hosts that share an instance ID in Git", async () => {
    const id = randomUUID();
    const healthy = host();
    const result = await syncFleetInstances(database.database, [
      host({ instanceId: id }),
      host({ instanceId: id }),
      healthy,
    ]);
    expect(result.inserted).toEqual([healthy.instanceId]);
    expect(result.conflicts.map((item) => item.instanceId)).toEqual([id, id]);
    expect(await row(id)).toBeUndefined();
  });

  it("leaves a newly registered row and other accounts' rows active", async () => {
    const service = createInstanceService(database.database);
    const fleet = [host()];
    await syncFleetInstances(database.database, fleet);
    const registered = await service.register({
      provider: "runpod",
      providerAccountId: "user_test",
      providerInstanceId: "notyetingit",
      region: null,
      faultDomain: null,
      sku: "1x RTX-PRO-6000",
    });
    const elsewhere = await service.register({
      provider: "runpod",
      providerAccountId: "another_account",
      providerInstanceId: "elsewherepod",
      region: null,
      faultDomain: null,
      sku: "1x RTX-PRO-6000",
    });

    expect(
      (await syncFleetInstances(database.database, fleet)).retired,
    ).toEqual([]);
    expect(
      (await syncFleetInstances(database.database, fleet, { now: later() }))
        .retired,
    ).toEqual([registered.id]);
    expect((await row(elsewhere.id))?.retiredAt).toBeNull();
  });

  it("retires a managed account's rows after its last host is removed", async () => {
    const kept = host();
    const removed = host({ accountId: "second_account" });
    await syncFleetInstances(database.database, [kept, removed]);
    const accounts = ["runpod/user_test", "runpod/second_account"];

    // Without the account list, the removed account falls out of scope.
    expect(
      (await syncFleetInstances(database.database, [kept], { now: later() }))
        .retired,
    ).toEqual([]);
    expect(
      (
        await syncFleetInstances(database.database, [kept], {
          now: later(),
          accounts,
        })
      ).retired,
    ).toEqual([removed.instanceId]);
    expect((await row(kept.instanceId))?.retiredAt).toBeNull();
  });

  it("records the host's fault domain and follows a change to it", async () => {
    const recorded = host({ faultDomain: "runpod:machinea" });
    await syncFleetInstances(database.database, [recorded]);
    expect((await row(recorded.instanceId))?.faultDomain).toBe(
      "runpod:machinea",
    );

    const moved = { ...recorded, faultDomain: "runpod:machineb" };
    expect(
      (await syncFleetInstances(database.database, [moved])).updated,
    ).toEqual([recorded.instanceId]);
    expect((await row(recorded.instanceId))?.faultDomain).toBe(
      "runpod:machineb",
    );
    const { faultDomain: _, ...unknown } = moved;
    expect(
      (await syncFleetInstances(database.database, [unknown])).updated,
    ).toEqual([]);
  });

  it("writes nothing when the caller loses leadership before commit", async () => {
    const fleet = [host()];
    await expect(
      syncFleetInstances(database.database, fleet, {
        beforeCommit: () => {
          throw new Error("The lease was lost");
        },
      }),
    ).rejects.toThrow("The lease was lost");
    expect(await row(fleet[0]!.instanceId)).toBeUndefined();
  });
});
