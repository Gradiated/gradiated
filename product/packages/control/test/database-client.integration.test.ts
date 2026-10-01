import { randomUUID } from "node:crypto";

import { eq } from "drizzle-orm";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { organizations } from "../src/db/schema/index.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";

describe("control database transactions with a single pooled connection", () => {
  let db: TestDatabase;

  beforeAll(async () => {
    // A leaked transaction cannot hide behind another available connection.
    db = await createTestDatabase(1);
  });
  afterAll(() => db.dispose());

  const organization = () => ({
    id: randomUUID(),
    name: "Transactional organization",
    kind: "customer" as const,
    status: "active" as const,
  });
  const stored = (id: string) =>
    db.database.select().from(organizations).where(eq(organizations.id, id));
  const session = async () =>
    (await db.pool.query<{ pid: number }>("select pg_backend_pid() as pid"))
      .rows[0]!.pid;

  it("rolls back a PostgreSQL error and reuses the connection for a successful transaction", async () => {
    const failed = organization();
    const pid = await session();

    await expect(
      db.database.transaction(async (tx) => {
        await tx.insert(organizations).values(failed);
        // A real constraint violation puts the session in an aborted transaction.
        await tx.insert(organizations).values(failed);
      }),
    ).rejects.toMatchObject({ cause: { code: "23505" } });

    expect(await stored(failed.id)).toEqual([]);
    const successful = organization();
    await db.database.transaction((tx) =>
      tx.insert(organizations).values(successful),
    );
    expect(await stored(successful.id)).toMatchObject([successful]);
    expect(await session()).toBe(pid);
    expect(db.pool.totalCount).toBe(1);
    expect(db.pool.waitingCount).toBe(0);
  });

  it("rolls back application failures and releases the connection", async () => {
    const failed = organization();
    const failure = new Error("Business operation failed after writing");
    const pid = await session();

    await expect(
      db.database.transaction(async (tx) => {
        await tx.insert(organizations).values(failed);
        throw failure;
      }),
    ).rejects.toBe(failure);

    expect(await stored(failed.id)).toEqual([]);
    expect(await session()).toBe(pid);
    expect(db.pool.idleCount).toBe(1);
  });
});
