import { eq } from "drizzle-orm";
import { afterAll, beforeAll, expect, it } from "vitest";

import {
  users,
  organizationMembers,
  organizations as organizationTable,
} from "../src/db/schema/index.js";
import { createOrganizationService } from "../src/organizations/service.js";
import { createMemberService } from "../src/members/service.js";
import { createWorkspaceApiKeyService } from "../src/workspaces/service.js";
import { seedUser } from "./support/fixtures.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";

let db: TestDatabase;
beforeAll(async () => {
  db = await createTestDatabase();
});
afterAll(() => db.dispose());

it("lets verified staff manage every customer organization without a membership and removes access on revocation", async () => {
  const organizations = createOrganizationService(db.database);
  const members = createMemberService(db.database);
  const workspaces = createWorkspaceApiKeyService(db.database);
  const owner = await seedUser(db.database);
  const staff = await seedUser(db.database);
  const customer = await organizations.createForUser(owner, "Customer");

  expect(await organizations.listForUser(staff)).toEqual([]);
  await expect(members.listMembers(staff, customer.id)).rejects.toMatchObject({
    code: "not_found",
  });

  await db.database
    .update(users)
    .set({ isStaff: true, emailVerified: true })
    .where(eq(users.id, staff));
  expect(await organizations.listForUser(staff)).toEqual([]);
  expect(await organizations.listForUser(staff, customer.id)).toEqual([
    expect.objectContaining({ id: customer.id, role: "admin" }),
  ]);
  expect(await members.listMembers(staff, customer.id)).toEqual([
    expect.objectContaining({ userId: owner }),
  ]);
  await workspaces.updateWorkspace(staff, customer.defaultWorkspaceId, {
    name: "Prepared",
  });
  expect(await workspaces.listWorkspaces(staff, customer.id, false)).toEqual([
    expect.objectContaining({ name: "Prepared" }),
  ]);
  await organizations.updateForUser(staff, customer.id, {
    name: "Customer updated",
  });
  await members.createInvitations(staff, customer.id, {
    emails: ["new@customer.test"],
    role: "admin",
  });
  expect(await members.listInvitations(staff, customer.id)).toHaveLength(1);
  expect(
    await db.database
      .select()
      .from(organizationMembers)
      .where(eq(organizationMembers.userId, staff)),
  ).toEqual([]);

  const other = await seedUser(db.database);
  await db.database.insert(organizationMembers).values({
    organizationId: customer.id,
    userId: other,
    role: "member",
    status: "active",
  });
  await members.updateMember(staff, customer.id, other, { role: "admin" });
  await members.removeMember(staff, customer.id, other);
  await expect(
    members.removeMember(staff, customer.id, owner),
  ).rejects.toMatchObject({ code: "conflict" });
  await expect(
    members.updateMember(staff, customer.id, owner, { role: "member" }),
  ).rejects.toMatchObject({ code: "conflict" });

  await db.database
    .update(organizationTable)
    .set({ status: "suspended" })
    .where(eq(organizationTable.id, customer.id));
  expect(await members.listMembers(staff, customer.id)).toHaveLength(1);
  await expect(
    workspaces.updateWorkspace(staff, customer.defaultWorkspaceId, {
      name: "Blocked",
    }),
  ).rejects.toMatchObject({ code: "forbidden" });

  await db.database
    .update(users)
    .set({ isStaff: false })
    .where(eq(users.id, staff));
  expect(await organizations.listForUser(staff)).toEqual([]);
  expect(await workspaces.listWorkspaces(staff, customer.id, false)).toEqual(
    [],
  );
  await expect(members.listMembers(staff, customer.id)).rejects.toMatchObject({
    code: "not_found",
  });
});

it("does not grant global organization access to unverified staff", async () => {
  const userId = await seedUser(db.database);
  await db.database
    .update(users)
    .set({ isStaff: true, emailVerified: false })
    .where(eq(users.id, userId));
  expect(
    await createOrganizationService(db.database).listForUser(userId),
  ).toEqual([]);
});

it("searches literal name substrings and paginates matching customer organizations in storage", async () => {
  const service = createOrganizationService(db.database);
  const owner = await seedUser(db.database);
  const staff = await seedUser(db.database);
  await db.database
    .update(users)
    .set({ isStaff: true, emailVerified: true })
    .where(eq(users.id, staff));
  const first = await service.createForUser(owner, "SearchFixture Alpha 100%");
  const second = await service.createForUser(owner, "SearchFixture Alpha_2");
  await service.createForUser(owner, "SearchFixture Beta");
  const page = { search: "SEARCHFIXTURE ALPHA", limit: 1, offset: 0 };
  expect(await service.listForUser(staff, undefined, page)).toEqual([
    expect.objectContaining({ id: first.id }),
  ]);
  expect(
    await service.listForUser(staff, undefined, { ...page, offset: 1 }),
  ).toEqual([expect.objectContaining({ id: second.id })]);
  expect(
    await service.listForUser(staff, undefined, { ...page, offset: 2 }),
  ).toEqual([]);
  expect(
    await service.listForUser(staff, undefined, { ...page, search: "%" }),
  ).toEqual([expect.objectContaining({ id: first.id })]);
  expect(
    await service.listForUser(staff, undefined, { ...page, search: "_" }),
  ).toEqual([expect.objectContaining({ id: second.id })]);
  expect(
    await service.listForUser(await seedUser(db.database), undefined, page),
  ).toEqual([]);
});

it("keeps staff bootstrap limited to memberships while providing bounded global list and detail queries", async () => {
  const service = createOrganizationService(db.database);
  const staff = await seedUser(db.database);
  const owner = await seedUser(db.database);
  await db.database
    .update(users)
    .set({ isStaff: true, emailVerified: true })
    .where(eq(users.id, staff));
  const own = await service.createForUser(staff, "BootstrapFixture Own");
  const external = await service.createForUser(
    owner,
    "BootstrapFixture External",
  );
  for (let index = 0; index < 22; index++)
    await service.createForUser(owner, `BootstrapFixture ${index}`);

  expect(await service.listForUser(staff)).toEqual([
    expect.objectContaining({ id: own.id }),
  ]);
  expect(await service.listForUser(staff, external.id)).toEqual([
    expect.objectContaining({ id: external.id, role: "admin" }),
  ]);
  expect(
    await service.listForUser(staff, undefined, {
      search: "BootstrapFixture",
      limit: 20,
      offset: 0,
    }),
  ).toHaveLength(20);
  expect(
    await service.listForUser(staff, undefined, {
      search: "BootstrapFixture",
      limit: 20,
      offset: 20,
    }),
  ).toHaveLength(4);

  await db.database
    .update(users)
    .set({ isStaff: false })
    .where(eq(users.id, staff));
  expect(await service.listForUser(staff)).toEqual([
    expect.objectContaining({ id: own.id }),
  ]);
  expect(await service.listForUser(staff, external.id)).toEqual([]);
});
