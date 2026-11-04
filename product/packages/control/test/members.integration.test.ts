import { randomUUID } from "node:crypto";
import { eq } from "drizzle-orm";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import {
  apiKeys,
  invitations,
  organizationMembers,
} from "../src/db/schema/index.js";
import {
  createMemberService,
  type MemberService,
} from "../src/members/service.js";
import {
  createOrganizationService,
  type OrganizationService,
} from "../src/organizations/service.js";
import { createWorkspaceApiKeyService } from "../src/workspaces/service.js";
import { seedMember, seedUser, seedWorkspace } from "./support/fixtures.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";

describe("organization members and invitations", () => {
  let db: TestDatabase;
  let members: MemberService;
  let organizations: OrganizationService;

  beforeAll(async () => {
    db = await createTestDatabase();
    members = createMemberService(db.database);
    organizations = createOrganizationService(db.database);
  });
  afterAll(() => db.dispose());

  const addMember = async (
    organizationId: string,
    role: "admin" | "member",
  ) => {
    const userId = await seedUser(db.database);
    await db.database.insert(organizationMembers).values({
      organizationId,
      userId,
      role,
      status: "active",
    });

    return userId;
  };
  const invitee = async (email = `${randomUUID()}@acme.test`) => ({
    id: await seedUser(db.database, { email, emailVerified: true }),
    email,
    emailVerified: true,
  });

  it("lists members for every role and lets only admins change them", async () => {
    const { userId: admin, organizationId } = await seedMember(db.database, {
      role: "admin",
    });
    const member = await addMember(organizationId, "member");

    expect(await members.listMembers(member, organizationId)).toMatchObject([
      { userId: admin, role: "admin" },
      { userId: member, role: "member" },
    ]);
    await expect(
      members.updateMember(member, organizationId, admin, { role: "member" }),
    ).rejects.toMatchObject({ code: "forbidden" });

    expect(
      await members.updateMember(admin, organizationId, member, {
        role: "admin",
      }),
    ).toMatchObject({ userId: member, role: "admin" });
  });

  it("never lets an admin change or remove themselves", async () => {
    const { userId: admin, organizationId } = await seedMember(db.database, {
      role: "admin",
    });

    await expect(
      members.updateMember(admin, organizationId, admin, { role: "member" }),
    ).rejects.toMatchObject({ code: "forbidden" });
    await expect(
      members.removeMember(admin, organizationId, admin),
    ).rejects.toMatchObject({ code: "forbidden" });
  });

  it("revokes the playground key of a removed member", async () => {
    const {
      userId: admin,
      organizationId,
      workspaceId,
    } = await seedMember(db.database, { role: "admin" });
    const member = await addMember(organizationId, "member");
    const keys = createWorkspaceApiKeyService(db.database);
    const playground = await keys.createPlaygroundCredential(
      member,
      workspaceId,
    );
    const visible = await keys.createApiKey(member, workspaceId, {
      name: "Visible",
      expiresAt: null,
    });

    await members.removeMember(admin, organizationId, member);

    const revokedAt = async (id: string) =>
      (await db.database.select().from(apiKeys).where(eq(apiKeys.id, id)))[0]
        ?.revokedAt;
    expect(await revokedAt(playground.apiKeyId)).toBeInstanceOf(Date);
    expect(await revokedAt(visible.apiKey.id)).toBeNull();
  });

  it("removes another member", async () => {
    const { userId: admin, organizationId } = await seedMember(db.database, {
      role: "admin",
    });
    const member = await addMember(organizationId, "member");

    await members.removeMember(admin, organizationId, member);

    expect(
      (await members.listMembers(admin, organizationId)).map(
        (row) => row.userId,
      ),
    ).toEqual([admin]);
    await expect(
      members.removeMember(admin, organizationId, member),
    ).rejects.toMatchObject({ code: "not_found" });
  });

  it("hides members from outsiders", async () => {
    const { organizationId } = await seedMember(db.database, { role: "admin" });
    const outsider = await seedUser(db.database);

    await expect(
      members.listMembers(outsider, organizationId),
    ).rejects.toMatchObject({ code: "not_found" });
  });

  it("issues, re-issues, previews, revokes and accepts invitations", async () => {
    const { userId: admin, organizationId } = await seedMember(db.database, {
      role: "admin",
    });
    const person = await invitee();

    const [first] = await members.createInvitations(admin, organizationId, {
      emails: [person.email, ` ${person.email.toUpperCase()} `],
      role: "member",
    });
    const [again] = await members.createInvitations(admin, organizationId, {
      emails: [person.email],
      role: "admin",
    });

    expect(again?.invitation).toMatchObject({
      id: first?.invitation.id,
      email: person.email,
      role: "admin",
    });
    expect(await members.listInvitations(admin, organizationId)).toHaveLength(
      1,
    );
    expect(await members.previewInvitation(first!.token)).toEqual({
      status: "invalid",
    });
    expect(await members.previewInvitation(again!.token)).toMatchObject({
      status: "pending",
      organization_id: organizationId,
      email: person.email,
      role: "admin",
    });

    await expect(
      members.acceptInvitation(
        { ...person, email: "other@acme.test" },
        again!.token,
      ),
    ).rejects.toMatchObject({ code: "forbidden" });
    expect(await members.acceptInvitation(person, again!.token)).toEqual({
      organizationId,
    });
    expect(await members.listMembers(admin, organizationId)).toContainEqual(
      expect.objectContaining({ userId: person.id, role: "admin" }),
    );
    expect(await members.previewInvitation(again!.token)).toMatchObject({
      status: "accepted",
      organization_id: organizationId,
    });
    expect(await members.listInvitations(admin, organizationId)).toEqual([]);
  });

  it("refuses to invite existing members and lets members only read invitations", async () => {
    const { userId: admin, organizationId } = await seedMember(db.database, {
      role: "admin",
    });
    const member = await invitee();
    await db.database.insert(organizationMembers).values({
      organizationId,
      userId: member.id,
      role: "member",
      status: "active",
    });

    await expect(
      members.createInvitations(admin, organizationId, {
        emails: [member.email],
        role: "member",
      }),
    ).rejects.toMatchObject({ code: "conflict" });
    await expect(
      members.createInvitations(member.id, organizationId, {
        emails: ["new@acme.test"],
        role: "member",
      }),
    ).rejects.toMatchObject({ code: "forbidden" });
    expect(await members.listInvitations(member.id, organizationId)).toEqual(
      [],
    );
  });

  it("rejects revoked and expired invitations and reports expiry in the preview", async () => {
    const { userId: admin, organizationId } = await seedMember(db.database, {
      role: "admin",
    });
    const revoked = await invitee();
    const expired = await invitee();
    const [revokedInvite, expiredInvite] = await members.createInvitations(
      admin,
      organizationId,
      { emails: [revoked.email, expired.email], role: "member" },
    );
    await members.revokeInvitation(
      admin,
      organizationId,
      revokedInvite!.invitation.id,
    );
    await db.database
      .update(invitations)
      .set({ expiresAt: new Date(Date.now() - 1000) })
      .where(eq(invitations.id, expiredInvite!.invitation.id));

    expect(await members.previewInvitation(revokedInvite!.token)).toEqual({
      status: "invalid",
    });
    expect(await members.previewInvitation(expiredInvite!.token)).toMatchObject(
      {
        status: "expired",
      },
    );
    for (const [user, issued] of [
      [revoked, revokedInvite],
      [expired, expiredInvite],
    ] as const)
      await expect(
        members.acceptInvitation(user, issued!.token),
      ).rejects.toMatchObject({ code: "not_found" });

    const resent = await members.resendInvitation(
      admin,
      organizationId,
      expiredInvite!.invitation.id,
    );
    expect(await members.acceptInvitation(expired, resent.token)).toEqual({
      organizationId,
    });
  });

  it("joins invited organizations at signup instead of creating a personal one", async () => {
    const { userId: admin, organizationId } = await seedMember(db.database, {
      role: "admin",
    });
    await seedWorkspace(db.database, { organizationId, isDefault: true });
    const person = await invitee();
    await members.createInvitations(admin, organizationId, {
      emails: [person.email],
      role: "member",
    });

    const organization = await organizations.ensureForNewUser(person);

    expect(organization).toMatchObject({ id: organizationId, role: "member" });
    expect(await organizations.listForUser(person.id)).toHaveLength(1);
    expect(await members.listInvitations(admin, organizationId)).toEqual([]);
  });

  it("hands a prepared workspace to an invited customer admin without creating another organization", async () => {
    const staffId = await seedUser(db.database);
    const prepared = await organizations.createForUser(
      staffId,
      "Prepared Customer",
    );
    const workspaceService = createWorkspaceApiKeyService(db.database);
    await workspaceService.updateWorkspace(
      staffId,
      prepared.defaultWorkspaceId,
      { name: "Customer Production" },
    );
    const email = `${randomUUID()}@customer.test`;
    await members.createInvitations(staffId, prepared.id, {
      emails: [email],
      role: "admin",
    });

    const person = await invitee(email);
    const joined = await organizations.ensureForNewUser(person);

    expect(joined).toMatchObject({
      id: prepared.id,
      role: "admin",
      onboardingCompleted: true,
    });
    expect(await organizations.listForUser(person.id)).toHaveLength(1);
    expect(
      await workspaceService.listWorkspaces(person.id, prepared.id, false),
    ).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: prepared.defaultWorkspaceId,
          name: "Customer Production",
        }),
      ]),
    );
  });

  it("accepts every pending invitation at signup", async () => {
    const person = await invitee();
    const organizationIds: string[] = [];
    for (const _ of [1, 2]) {
      const { userId: admin, organizationId } = await seedMember(db.database, {
        role: "admin",
      });
      await seedWorkspace(db.database, { organizationId, isDefault: true });
      await members.createInvitations(admin, organizationId, {
        emails: [person.email],
        role: "member",
      });
      organizationIds.push(organizationId);
    }

    await organizations.ensureForNewUser(person);

    expect(
      (await organizations.listForUser(person.id)).map((row) => row.id).sort(),
    ).toEqual(organizationIds.sort());
  });

  it("never lets concurrent demotions leave the organization without an admin", async () => {
    const { userId: first, organizationId } = await seedMember(db.database, {
      role: "admin",
    });
    const second = await addMember(organizationId, "admin");

    const results = await Promise.allSettled([
      members.updateMember(first, organizationId, second, { role: "member" }),
      members.updateMember(second, organizationId, first, { role: "member" }),
    ]);

    expect(
      results.filter((result) => result.status === "fulfilled"),
    ).toHaveLength(1);
    expect(
      (await members.listMembers(first, organizationId)).filter(
        (member) => member.role === "admin",
      ),
    ).toHaveLength(1);
  });

  it("stores roles written by older API versions as admin", async () => {
    const { organizationId } = await seedMember(db.database, { role: "admin" });
    const userId = await seedUser(db.database);

    await db.pool.query(
      "insert into organization_members (organization_id, user_id, role, status) values ($1, $2, 'owner', 'active')",
      [organizationId, userId],
    );

    expect(await members.listMembers(userId, organizationId)).toContainEqual(
      expect.objectContaining({ userId, role: "admin" }),
    );
  });
});
