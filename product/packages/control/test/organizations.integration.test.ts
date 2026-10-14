import { randomUUID } from "node:crypto";
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
  seedMember,
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
      {
        id: organization.defaultWorkspaceId,
        isDefault: true,
        traceCaptureEnabled: true,
        traceRetentionDays: 180,
        defaultJudgeModel: "openai/gpt-6.1-sol",
      },
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

describe("organization settings", () => {
  let db: TestDatabase;
  let service: OrganizationService;
  beforeAll(async () => {
    db = await createTestDatabase();
    service = createOrganizationService(db.database);
  });
  afterAll(() => db.dispose());

  it.each(["owner", "admin"] as const)(
    "lets %s rename an organization and returns its current role",
    async (role) => {
      const { userId, organizationId } = await seedMember(db.database, {
        role,
      });
      await seedWorkspace(db.database, { organizationId, isDefault: true });

      const updated = await service.updateForUser(userId, organizationId, {
        name: "  Research team  ",
      });
      expect(updated).toMatchObject({
        id: organizationId,
        name: "Research team",
        role,
      });
      expect(
        (await service.listForUser(userId)).find(
          (row) => row.id === organizationId,
        )?.name,
      ).toBe("Research team");
    },
  );
  it.each(["member", "billing"] as const)(
    "prevents %s from renaming",
    async (role) => {
      const { userId, organizationId } = await seedMember(db.database, {
        role,
      });
      await seedWorkspace(db.database, { organizationId, isDefault: true });

      const before = await service.listForUser(userId);
      await expect(
        service.updateForUser(userId, organizationId, { name: "Denied" }),
      ).rejects.toMatchObject({ code: "forbidden" });
      expect(await service.listForUser(userId)).toEqual(before);
    },
  );
  it("hides organizations from outsiders and rejects suspended organizations", async () => {
    const { userId, organizationId } = await seedMember(db.database, {
      role: "owner",
      organization: { status: "suspended" },
    });
    const outsider = await seedUser(db.database);
    await expect(
      service.updateForUser(outsider, organizationId, { name: "Denied" }),
    ).rejects.toMatchObject({ code: "not_found" });
    await expect(
      service.updateForUser(userId, organizationId, { name: "Denied" }),
    ).rejects.toMatchObject({ code: "forbidden" });
  });
  it("rejects blank names without persisting them", async () => {
    const { userId, organizationId } = await seedMember(db.database, {
      role: "owner",
    });
    await seedWorkspace(db.database, { organizationId, isDefault: true });

    const before = await service.listForUser(userId);
    await expect(
      service.updateForUser(userId, organizationId, { name: "   " }),
    ).rejects.toThrow();
    expect(await service.listForUser(userId)).toEqual(before);
  });
});

describe("organization onboarding and domain auto-join", () => {
  let db: TestDatabase;
  let service: OrganizationService;
  beforeAll(async () => {
    db = await createTestDatabase();
    service = createOrganizationService(db.database);
  });
  afterAll(() => db.dispose());

  const companyUser = async (domain: string, emailVerified = true) => {
    const email = `${randomUUID()}@${domain}`;
    const id = await seedUser(db.database, { email, emailVerified });

    return { id, email, emailVerified };
  };
  const uniqueDomain = () => `acme-${randomUUID()}.com`;

  it("marks signup organizations for onboarding and created ones as onboarded", async () => {
    const userId = await seedUser(db.database);

    const personal = await service.ensurePersonalForUser(userId);
    const created = await service.createForUser(userId, "Team");

    expect(personal).toMatchObject({
      onboardingCompleted: false,
      autoJoinDomain: null,
    });
    expect(
      (await service.listForUser(userId)).find((row) => row.id === created.id),
    ).toMatchObject({ onboardingCompleted: true });
  });

  it("completes onboarding with a name and the owner's company domain", async () => {
    const domain = uniqueDomain();
    const owner = await companyUser(domain);
    const personal = await service.ensurePersonalForUser(owner.id);

    const updated = await service.updateForUser(owner.id, personal.id, {
      name: "Acme",
      auto_join_domain: domain,
      onboarding_completed: true,
    });

    expect(updated).toMatchObject({
      name: "Acme",
      autoJoinDomain: domain,
      onboardingCompleted: true,
    });

    const updatedAgain = await service.updateForUser(owner.id, personal.id, {
      auto_join_domain: null,
    });
    expect(updatedAgain).toMatchObject({
      autoJoinDomain: null,
      onboardingCompleted: true,
    });
  });

  it.each([
    ["another company's domain", true, "other.example"],
    ["an unverified email domain", false, undefined],
  ])("refuses %s", async (_label, emailVerified, requested) => {
    const domain = uniqueDomain();
    const owner = await companyUser(domain, emailVerified);
    const personal = await service.ensurePersonalForUser(owner.id);

    await expect(
      service.updateForUser(owner.id, personal.id, {
        auto_join_domain: requested ?? domain,
      }),
    ).rejects.toMatchObject({ code: "forbidden" });
  });

  it("refuses personal email domains", async () => {
    const owner = await companyUser("gmail.com");
    const personal = await service.ensurePersonalForUser(owner.id);

    await expect(
      service.updateForUser(owner.id, personal.id, {
        auto_join_domain: "gmail.com",
      }),
    ).rejects.toMatchObject({ code: "forbidden" });
  });

  it("lets only one organization claim a domain", async () => {
    const domain = uniqueDomain();
    const first = await companyUser(domain);
    const second = await companyUser(domain);
    const firstOrganization = await service.ensurePersonalForUser(first.id);
    const secondOrganization = await service.ensurePersonalForUser(second.id);
    await service.updateForUser(first.id, firstOrganization.id, {
      auto_join_domain: domain,
    });

    await expect(
      service.updateForUser(second.id, secondOrganization.id, {
        auto_join_domain: domain,
      }),
    ).rejects.toMatchObject({ code: "conflict" });
  });

  it("adds verified signups at a claimed domain as members instead of creating a personal organization", async () => {
    const domain = uniqueDomain();
    const owner = await companyUser(domain);
    const acme = await service.ensurePersonalForUser(owner.id);
    await service.updateForUser(owner.id, acme.id, {
      name: "Acme",
      auto_join_domain: domain,
      onboarding_completed: true,
    });
    const teammate = await companyUser(domain);

    const joined = await service.ensureForNewUser(teammate);

    expect(joined).toMatchObject({
      id: acme.id,
      name: "Acme",
      role: "member",
      onboardingCompleted: true,
    });
    expect(await service.listForUser(teammate.id)).toHaveLength(1);
    expect(await service.ensureForNewUser(teammate)).toMatchObject({
      id: acme.id,
    });
  });

  it("creates a personal organization for unverified or unclaimed domains", async () => {
    const domain = uniqueDomain();
    const owner = await companyUser(domain);
    const acme = await service.ensurePersonalForUser(owner.id);
    await service.updateForUser(owner.id, acme.id, {
      auto_join_domain: domain,
    });
    const unverified = await companyUser(domain, false);
    const elsewhere = await companyUser(uniqueDomain());

    for (const user of [unverified, elsewhere]) {
      const organization = await service.ensureForNewUser(user);

      expect(organization).toMatchObject({
        name: "Personal",
        role: "owner",
        onboardingCompleted: false,
      });
    }
  });
});
