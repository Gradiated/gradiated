import { eq } from "drizzle-orm";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import {
  organizationMembers,
  organizations as organizationTable,
  billingAccounts,
  balanceTransactions,
  workspaces,
} from "../src/db/schema/index.js";
import {
  createOrganizationService,
  SIGNUP_CREDIT_NANO_USD,
  type OrganizationService,
} from "../src/organizations/service.js";
import {
  billingAccountRow,
  ledgerRows,
  seedOrganization,
  seedUser,
  seedWorkspace,
} from "./support/fixtures.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";

describe("organization bootstrap", () => {
  let testDatabase: TestDatabase;
  let organizations: OrganizationService;

  beforeAll(async () => {
    testDatabase = await createTestDatabase();
    organizations = createOrganizationService(testDatabase.database);
  });

  afterAll(() => testDatabase.dispose());

  const rowsFor = async (organizationId: string) => {
    const { database } = testDatabase;
    const [members, defaultWorkspaces, account, credits] = await Promise.all([
      database
        .select()
        .from(organizationMembers)
        .where(eq(organizationMembers.organizationId, organizationId)),
      database
        .select()
        .from(workspaces)
        .where(eq(workspaces.organizationId, organizationId)),
      billingAccountRow(database, organizationId),
      ledgerRows(database, organizationId),
    ]);

    return { members, workspaces: defaultWorkspaces, account, credits };
  };

  it("creates a personal organization with one signup credit", async () => {
    const userId = await seedUser(testDatabase.database);

    const organization = await organizations.ensurePersonalForUser(userId);
    const rows = await rowsFor(organization.id);

    expect(organization).toMatchObject({
      name: "Personal",
      status: "active",
      role: "owner",
    });
    expect(rows.members).toMatchObject([
      { userId, role: "owner", status: "active" },
    ]);
    expect(rows.workspaces).toMatchObject([
      { id: organization.defaultWorkspaceId, isDefault: true },
    ]);
    expect(rows.account).toMatchObject({
      mode: "prepaid",
      balance: SIGNUP_CREDIT_NANO_USD,
    });
    expect(rows.credits).toMatchObject([
      {
        type: "credit",
        amount: SIGNUP_CREDIT_NANO_USD,
        balanceAfter: SIGNUP_CREDIT_NANO_USD,
        sourceType: "operator",
        sourceId: `signup-grant:${organization.id}`,
        createdBy: userId,
      },
    ]);
  });

  it("returns the existing organization without a second credit", async () => {
    const userId = await seedUser(testDatabase.database);

    const first = await organizations.ensurePersonalForUser(userId);
    const second = await organizations.ensurePersonalForUser(userId);

    expect(second.id).toBe(first.id);
    expect((await rowsFor(first.id)).credits).toHaveLength(1);
  });

  it("rolls back the entire bootstrap when its final signup credit insert fails", async () => {
    const userId = await seedUser(testDatabase.database);
    const snapshot = async () =>
      Promise.all([
        testDatabase.database.select().from(organizationTable),
        testDatabase.database.select().from(organizationMembers),
        testDatabase.database.select().from(workspaces),
        testDatabase.database.select().from(billingAccounts),
        testDatabase.database.select().from(balanceTransactions),
      ]);
    const before = await snapshot();
    await testDatabase.pool.query(`
      create function reject_signup_credit() returns trigger language plpgsql as $$
      begin
        if new.source_id like 'signup-grant:%' then
          raise exception 'Injected signup credit failure';
        end if;
        return new;
      end;
      $$;
      create trigger reject_signup_credit before insert on balance_transactions
        for each row execute function reject_signup_credit();
    `);
    try {
      await expect(
        organizations.ensurePersonalForUser(userId),
      ).rejects.toMatchObject({
        cause: { code: "P0001" },
      });
      expect(await snapshot()).toEqual(before);
      expect(await organizations.listForUser(userId)).toEqual([]);
    } finally {
      await testDatabase.pool.query(
        "drop trigger reject_signup_credit on balance_transactions; drop function reject_signup_credit()",
      );
    }

    const retried = await organizations.ensurePersonalForUser(userId);
    const rows = await rowsFor(retried.id);
    expect(rows.members).toHaveLength(1);
    expect(rows.workspaces).toHaveLength(1);
    expect(rows.account?.balance).toBe(SIGNUP_CREDIT_NANO_USD);
    expect(rows.credits).toHaveLength(1);
  });

  it("creates an additional organization without a credit", async () => {
    const userId = await seedUser(testDatabase.database);

    const organization = await organizations.createForUser(userId, "Team");
    const rows = await rowsFor(organization.id);

    expect(organization).toMatchObject({
      kind: "customer",
      name: "Team",
      role: "owner",
    });
    expect(rows.credits).toEqual([]);
    expect(rows.account).toMatchObject({ mode: "prepaid", balance: 0n });
  });

  it("lists only active memberships of customer organizations", async () => {
    const { database } = testDatabase;
    const userId = await seedUser(database);
    const organizationWithDefault = async (
      seed: Parameters<typeof seedOrganization>[1],
    ) => {
      const organizationId = await seedOrganization(database, seed);
      await seedWorkspace(database, { organizationId, isDefault: true });

      return organizationId;
    };

    const visible = await organizationWithDefault({
      members: [{ userId, role: "billing" }],
    });
    await organizationWithDefault({
      members: [{ userId, role: "owner", status: "suspended" }],
    });
    await organizationWithDefault({
      kind: "distribution_channel",
      members: [{ userId, role: "owner" }],
    });

    expect(await organizations.listForUser(userId)).toMatchObject([
      { id: visible, role: "billing", status: "active" },
    ]);
  });
});
