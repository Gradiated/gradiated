import { randomUUID } from "node:crypto";

import type { LedgerCredit } from "@gradiated/control";
import type { RedisClientType } from "@gradiated/valkey";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { createOperationalBalanceReader } from "../src/operational-balance.js";
import { connectTestValkey } from "./support/valkey.js";

const seededAt = Date.parse("2026-10-28T12:00:00.000Z");

let client: RedisClientType;

beforeAll(async () => {
  client = await connectTestValkey();
});

afterAll(async () => {
  await client.close();
});

const credit = (amount: bigint, createdAt: number): LedgerCredit => ({
  id: randomUUID(),
  amount,
  createdAt: new Date(createdAt),
});

const seed = async (
  fields: Record<string, string>,
  applied: LedgerCredit[] = [],
) => {
  const organizationId = randomUUID();

  await client.hSet(`account:{settlement-0}:${organizationId}`, {
    balance: "1000",
    balance_seeded_at: String(seededAt),
    balance_seeded_id: randomUUID(),
    ...fields,
  });
  if (applied.length > 0) {
    await client.sAdd(
      `applied-balance-transactions:{settlement-0}:${organizationId}`,
      applied.map((entry) => entry.id),
    );
  }

  return organizationId;
};

describe("operational balance", () => {
  it("returns null when no gateway has seeded the account", async () => {
    const reader = createOperationalBalanceReader(client);

    await expect(
      reader(randomUUID(), async () => {
        throw new Error("The ledger must not be read.");
      }),
    ).resolves.toBeNull();
  });

  it("adds credits the gateway has not applied yet", async () => {
    const reader = createOperationalBalanceReader(client);
    const applied = credit(500n, seededAt + 1_000);
    const unapplied = credit(70n, seededAt + 2_000);
    const organizationId = await seed({}, [applied]);
    let since: Date | null = null;

    const balance = await reader(organizationId, async (from) => {
      since = from;

      return [applied, unapplied];
    });

    expect(balance).toBe(1_070n);
    expect(since).toEqual(new Date(seededAt - 30_000));
  });

  it("skips credits a legacy seed included up to its replay floor", async () => {
    const reader = createOperationalBalanceReader(client);
    const included = credit(500n, seededAt - 5_000);
    const later = credit(30n, seededAt + 1);
    const organizationId = await seed({
      balance_replay_floor_at: String(seededAt),
    });

    await expect(
      reader(organizationId, async () => [included, later]),
    ).resolves.toBe(1_030n);
  });
});
