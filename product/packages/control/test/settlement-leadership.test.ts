import type { Pool, PoolClient, QueryResult } from "pg";
import { describe, expect, it, vi } from "vitest";

import { createGenerationSettlementStore } from "../src/settlement/postgres-store.js";
import { settlementPosting } from "./support/settlement.js";

type QueryReply = Partial<QueryResult> | Error;

const organizationId = "0198ad73-a200-7000-8000-000000000002";

const posting = (overrides: Parameters<typeof settlementPosting>[1] = {}) =>
  settlementPosting(organizationId, overrides);

const fakeClient = (replies: QueryReply[]) => {
  const statements: string[] = [];
  const release = vi.fn<(destroy?: Error | boolean) => void>();
  const query = vi.fn(async (statement: string | { text: string }) => {
    const text = typeof statement === "string" ? statement : statement.text;
    statements.push(text.trim().split(/\s+/)[0]?.toUpperCase() ?? "");

    const reply = replies.shift() ?? { rows: [] };
    if (reply instanceof Error) throw reply;

    return reply;
  });
  const pool = {
    connect: async () => ({ query, release }) as unknown as PoolClient,
  } as unknown as Pool;

  return { pool, query, release, statements };
};

const acquired = { rows: [{ acquired: true }] };

const lead = async (replies: QueryReply[]) => {
  const client = fakeClient([acquired, ...replies]);
  const leadership = await createGenerationSettlementStore(
    client.pool,
  ).tryAcquireLeadership();
  if (!leadership) throw new Error("The fake store granted no leadership.");

  return { ...client, leadership };
};

describe("settlement leadership connection handling", () => {
  it("returns the connection to the pool when another replica leads", async () => {
    const { pool, release } = fakeClient([{ rows: [{ acquired: false }] }]);

    expect(
      await createGenerationSettlementStore(pool).tryAcquireLeadership(),
    ).toBeNull();

    expect(release).toHaveBeenCalledExactlyOnceWith();
  });

  it("returns the connection to the pool after a clean unlock", async () => {
    const { leadership, release } = await lead([
      { rows: [{ unlocked: true }] },
    ]);

    await leadership.release();

    expect(release).toHaveBeenCalledExactlyOnceWith();
  });

  it("destroys the connection and rejects when the unlock query fails", async () => {
    const failure = new Error("connection reset");
    const { leadership, release } = await lead([failure]);

    await expect(leadership.release()).rejects.toBe(failure);

    expect(release).toHaveBeenCalledExactlyOnceWith(failure);
  });

  it("destroys the connection when the lock was not held", async () => {
    const { leadership, release } = await lead([
      { rows: [{ unlocked: false }] },
    ]);

    await expect(leadership.release()).rejects.toThrow("was not held");

    expect(release).toHaveBeenCalledExactlyOnceWith(expect.any(Error));
  });

  it("destroys the connection when the lock query fails", async () => {
    const failure = new Error("connection reset");
    const { pool, release } = fakeClient([failure]);

    await expect(
      createGenerationSettlementStore(pool).tryAcquireLeadership(),
    ).rejects.toBe(failure);

    expect(release).toHaveBeenCalledExactlyOnceWith(failure);
  });

  it("reports both errors when the rollback fails and then destroys the connection", async () => {
    const postingFailure = new Error("lock timeout");
    const rollbackFailure = new Error("connection reset");
    const { leadership, release, statements } = await lead([
      { rows: [] },
      postingFailure,
      rollbackFailure,
    ]);

    await expect(leadership.postSettlement(posting())).rejects.toMatchObject({
      errors: [{ cause: postingFailure }, rollbackFailure],
    });
    await leadership.release();

    expect(statements).toEqual(["SELECT", "BEGIN", "SELECT", "ROLLBACK"]);
    expect(release).toHaveBeenCalledExactlyOnceWith(rollbackFailure);
  });

  it("refuses further work on the connection after a failed rollback", async () => {
    const rollbackFailure = new Error("connection reset");
    const { leadership, query } = await lead([
      { rows: [] },
      new Error("lock timeout"),
      rollbackFailure,
    ]);
    await expect(leadership.postSettlement(posting())).rejects.toBeInstanceOf(
      AggregateError,
    );
    query.mockClear();

    const unusable = { cause: rollbackFailure };
    await expect(leadership.postSettlement(posting())).rejects.toMatchObject(
      unusable,
    );
    await expect(
      leadership.getBillingOrganizationIds([organizationId]),
    ).rejects.toMatchObject(unusable);
    await expect(
      leadership.getExistingSourceIds(["source"]),
    ).rejects.toMatchObject(unusable);
    await expect(
      leadership.getLatestSettlementPeriodStart(),
    ).rejects.toMatchObject(unusable);

    expect(query).not.toHaveBeenCalled();
  });

  it.each([{ totalCharge: 0n }, { totalCharge: -5n }, { generationCount: 0n }])(
    "rejects a non-positive posting %o before any query",
    async (values) => {
      const { leadership, query } = await lead([]);
      query.mockClear();

      await expect(leadership.postSettlement(posting(values))).rejects.toThrow(
        "positive charge",
      );

      expect(query).not.toHaveBeenCalled();
    },
  );
});
