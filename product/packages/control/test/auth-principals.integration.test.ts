import { randomUUID } from "node:crypto";

import { eq } from "drizzle-orm";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import {
  apiKeys,
  organizationMembers,
  users,
  workspaces,
} from "../src/db/schema/index.js";
import { apiKeyDigest } from "../src/workspaces/api-key-secret.js";
import { seedMember, seedUser, type MemberSeed } from "./support/fixtures.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";

type Principal = {
  key_hash: Buffer;
  api_key_id: string;
  workspace_id: string;
  org_id: string;
  org_slug: string;
  user_id: string | null;
  actor: string;
  role: string;
  status: string;
  scopes: string[] | null;
  expires_at: Date | null;
};

describe("auth_principals_v1", () => {
  let testDatabase: TestDatabase;

  beforeAll(async () => {
    testDatabase = await createTestDatabase();
  });

  afterAll(() => testDatabase.dispose());

  const seedKey = async (
    member: { userId: string; organizationId: string; workspaceId: string },
    fields: Partial<typeof apiKeys.$inferInsert> = {},
  ) => {
    const secret = `grad_${randomUUID()}`;
    const id = randomUUID();

    await testDatabase.database.insert(apiKeys).values({
      id,
      organizationId: member.organizationId,
      workspaceId: member.workspaceId,
      name: "Key",
      digest: apiKeyDigest(secret),
      createdBy: member.userId,
      ...fields,
    });

    return { id, secret };
  };

  const principal = async (secret: string): Promise<Principal | undefined> => {
    const { rows } = await testDatabase.pool.query<Principal>(
      "select * from auth_principals_v1 where key_hash = $1",
      [apiKeyDigest(secret)],
    );

    return rows[0];
  };

  const statusOf = async (seed: MemberSeed) => {
    const member = await seedMember(testDatabase.database, seed);
    const { secret } = await seedKey(member);

    return (await principal(secret))?.status;
  };

  it("describes an active member's key", async () => {
    const member = await seedMember(testDatabase.database, { role: "member" });
    const { id, secret } = await seedKey(member, {
      scopes: ["datasets:read"],
    });

    expect(await principal(secret)).toEqual({
      key_hash: apiKeyDigest(secret),
      api_key_id: id,
      workspace_id: member.workspaceId,
      org_id: member.organizationId,
      org_slug: expect.any(String),
      user_id: member.userId,
      actor: `key:${id}`,
      role: "member",
      status: "active",
      scopes: ["datasets:read"],
      expires_at: null,
    });
  });

  it("gives an admin's key the admin role and null scopes", async () => {
    const member = await seedMember(testDatabase.database, { role: "admin" });
    const { secret } = await seedKey(member);

    expect(await principal(secret)).toMatchObject({
      role: "admin",
      scopes: null,
    });
  });

  it.each<[string, MemberSeed]>([
    [
      "a suspended organization",
      { role: "admin", organization: { status: "suspended" } },
    ],
    ["an archived workspace", { role: "admin", workspace: { archived: true } }],
    ["a suspended member", { role: "admin", memberStatus: "suspended" }],
  ])("is never active for %s", async (_name, seed) => {
    expect(await statusOf(seed)).toBe("suspended");
  });

  it("is not active once the creator leaves the organization", async () => {
    const member = await seedMember(testDatabase.database, { role: "admin" });
    const { secret } = await seedKey(member);

    await testDatabase.database
      .delete(organizationMembers)
      .where(eq(organizationMembers.userId, member.userId));

    expect(await principal(secret)).toMatchObject({
      role: "member",
      status: "suspended",
    });
  });

  it("treats verified staff as an active admin, as the API does", async () => {
    const member = await seedMember(testDatabase.database, { role: "member" });
    const staffId = await seedUser(testDatabase.database, {
      emailVerified: true,
    });
    await testDatabase.database
      .update(users)
      .set({ isStaff: true })
      .where(eq(users.id, staffId));
    const { secret } = await seedKey({ ...member, userId: staffId });

    expect(await principal(secret)).toMatchObject({
      role: "admin",
      status: "active",
    });
  });

  it.each<[string, Partial<typeof apiKeys.$inferInsert>]>([
    ["revoked", { revokedAt: new Date() }],
    ["hidden", { hidden: true }],
    [
      "expired",
      {
        createdAt: new Date(Date.now() - 120_000),
        expiresAt: new Date(Date.now() - 60_000),
      },
    ],
  ])("has no row for a %s key", async (_name, fields) => {
    const member = await seedMember(testDatabase.database, { role: "admin" });
    const { secret } = await seedKey(member, fields);

    expect(await principal(secret)).toBeUndefined();
  });

  it("keeps an unexpired key with its expiry", async () => {
    const member = await seedMember(testDatabase.database, { role: "admin" });
    const expiresAt = new Date(Date.now() + 3_600_000);
    const { secret } = await seedKey(member, { expiresAt });

    expect((await principal(secret))?.expires_at).toEqual(expiresAt);
  });

  it("has no row for a distribution channel's key", async () => {
    const member = await seedMember(testDatabase.database, {
      role: "admin",
      organization: { kind: "distribution_channel" },
    });
    const { secret } = await seedKey(member);

    expect(await principal(secret)).toBeUndefined();
  });

  it("follows a workspace archived after the key was made", async () => {
    const member = await seedMember(testDatabase.database, { role: "admin" });
    const { secret } = await seedKey(member);

    await testDatabase.database
      .update(workspaces)
      .set({ archivedAt: new Date() })
      .where(eq(workspaces.id, member.workspaceId));

    expect((await principal(secret))?.status).toBe("suspended");
  });

  describe("grad_auth_reader", () => {
    const asReader = async (statement: string) => {
      const client = await testDatabase.pool.connect();

      try {
        await client.query("begin");
        await client.query("set local role grad_auth_reader");
        return await client.query(statement);
      } finally {
        await client.query("rollback");
        client.release();
      }
    };

    it("reads the view", async () => {
      await expect(
        asReader("select count(*) from auth_principals_v1"),
      ).resolves.toMatchObject({ rowCount: 1 });
    });

    it.each(["api_keys", "organizations", "workspaces", "users"])(
      "cannot read %s",
      async (table) => {
        await expect(asReader(`select 1 from ${table}`)).rejects.toThrow(
          /permission denied/,
        );
      },
    );

    it("has only SELECT on the view", async () => {
      const { rows } = await testDatabase.pool.query(
        `select table_name as table, privilege_type as privilege
         from information_schema.role_table_grants
         where grantee = 'grad_auth_reader'`,
      );

      expect(rows).toEqual([
        { table: "auth_principals_v1", privilege: "SELECT" },
      ]);
    });
  });
});
