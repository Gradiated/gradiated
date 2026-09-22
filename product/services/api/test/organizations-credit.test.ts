import { describe, expect, it } from "vitest";

import {
  SIGNUP_CREDIT_NANO_USD,
  createOrganizationService,
} from "@gradiated/control";
import type { ControlDatabase } from "@gradiated/control";

type CapturedInsert = { table: string; values: Record<string, unknown> };
type CapturedUpdate = { table: string; set: Record<string, unknown> };

function chainable(resolve: () => unknown): unknown {
  const proxy: unknown = new Proxy(() => undefined, {
    get: (_target, property) => {
      if (property === "then") {
        return (
          onFulfilled: (value: unknown) => unknown,
          onRejected: (reason: unknown) => unknown,
        ) => Promise.resolve(resolve()).then(onFulfilled, onRejected);
      }
      if (property === "catch") {
        return (onRejected: (reason: unknown) => unknown) =>
          Promise.resolve(resolve()).catch(onRejected);
      }
      return () => proxy;
    },
  });
  return proxy;
}

function recordingDatabase() {
  const inserts: CapturedInsert[] = [];
  const updates: CapturedUpdate[] = [];
  const tableName = (table: unknown): string => {
    const name = Object.getOwnPropertySymbols(table as object)
      .map((symbol) => (table as Record<symbol, unknown>)[symbol])
      .find((value) => typeof value === "string");
    return typeof name === "string" ? name : "unknown";
  };

  const database = {
    select: () => chainable(() => []),
    transaction: (callback: (tx: unknown) => Promise<unknown>) =>
      callback({
        insert: (table: unknown) => ({
          values: (values: Record<string, unknown>) => {
            inserts.push({ table: tableName(table), values });
            return Promise.resolve();
          },
        }),
        update: (table: unknown) => ({
          set: (set: Record<string, unknown>) => ({
            where: () => {
              updates.push({ table: tableName(table), set });
              return Promise.resolve();
            },
          }),
        }),
      }),
  } as unknown as ControlDatabase;

  return { database, inserts, updates };
}

describe("organization signup credit", () => {
  it("grants the signup credit when bootstrapping a new user's organization", async () => {
    const { database, inserts, updates } = recordingDatabase();
    const service = createOrganizationService(database);

    await service.ensurePersonalForUser("user-1");

    const organization = inserts.find(
      (entry) => entry.table === "organizations",
    );
    const credit = inserts.find(
      (entry) => entry.table === "balance_transactions",
    );
    expect(organization).toBeDefined();
    expect(credit).toBeDefined();
    expect(credit?.values.amount).toBe(SIGNUP_CREDIT_NANO_USD);
    expect(credit?.values.sourceType).toBe("operator");
    expect(credit?.values.sourceId).toBe(
      `signup-grant:${String(organization?.values.id)}`,
    );
    expect(credit?.values.createdBy).toBe("user-1");
    expect(credit?.values.type).toBe("credit");

    const balanceUpdate = updates.find(
      (entry) => entry.table === "billing_accounts",
    );
    expect(balanceUpdate?.set.balance).toBe(SIGNUP_CREDIT_NANO_USD);
  });

  it("does not grant a credit when the console creates an additional organization", async () => {
    const { database, inserts, updates } = recordingDatabase();
    const service = createOrganizationService(database);

    await service.createForUser("user-1", "Second org");

    expect(
      inserts.find((entry) => entry.table === "balance_transactions"),
    ).toBeUndefined();
    expect(updates).toHaveLength(0);
  });

  it("does not grant a second credit when the user already has an organization", async () => {
    const existing = {
      id: "0198ae59-294a-73a9-9d2f-962449d34226",
      name: "Personal",
      status: "active" as const,
      role: "owner" as const,
      defaultWorkspaceId: "0198ae5a-2529-7c1a-801b-dc9d5f876a94",
    };
    const { database, inserts } = recordingDatabase();
    (database as unknown as { select: () => unknown }).select = () =>
      chainable(() => [existing]);
    const service = createOrganizationService(database);

    const result = await service.ensurePersonalForUser("user-1");

    expect(result.id).toBe(existing.id);
    expect(inserts).toHaveLength(0);
  });
});
