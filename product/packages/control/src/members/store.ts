import { and, asc, eq, gt, inArray, isNull, sql } from "drizzle-orm";
import { z } from "zod";
import { v7 as uuidv7 } from "uuid";

import {
  OrganizationRoleSchema,
  UuidSchema,
  type InvitationPreview,
} from "@gradiated/contracts";
import { activeCustomerOrganization } from "../access.js";
import type { ControlDatabase } from "../db/client.js";

type Transaction = Parameters<Parameters<ControlDatabase["transaction"]>[0]>[0];
import {
  apiKeys,
  invitations,
  organizationMembers,
  organizations,
  users,
  type OrganizationRole,
} from "../db/schema/index.js";
import { sha256Digest } from "../secrets.js";

const INVITATION_LIFETIME_MS = 7 * 24 * 60 * 60 * 1000;

const expiresAfter = (now: Date) =>
  new Date(now.getTime() + INVITATION_LIFETIME_MS);

const MemberRecordSchema = z.object({
  userId: UuidSchema,
  email: z.email(),
  role: OrganizationRoleSchema,
  joinedAt: z.date(),
});
export type MemberRecord = z.infer<typeof MemberRecordSchema>;

const InvitationRecordSchema = z.object({
  id: UuidSchema,
  organizationId: UuidSchema,
  email: z.email(),
  role: OrganizationRoleSchema,
  invitedByEmail: z.email(),
  expiresAt: z.date(),
  createdAt: z.date(),
});
export type InvitationRecord = z.infer<typeof InvitationRecordSchema>;

const InvitationTargetSchema = InvitationRecordSchema.extend({
  organizationName: z.string(),
  organizationActive: z.boolean(),
  acceptedAt: z.date().nullable(),
  revokedAt: z.date().nullable(),
});

const pending = sql`${invitations.acceptedAt} is null and ${invitations.revokedAt} is null`;

const memberColumns = {
  userId: organizationMembers.userId,
  email: users.email,
  role: organizationMembers.role,
  joinedAt: organizationMembers.createdAt,
};

const invitationColumns = {
  id: invitations.id,
  organizationId: invitations.organizationId,
  email: invitations.email,
  role: invitations.role,
  invitedByEmail: users.email,
  expiresAt: invitations.expiresAt,
  createdAt: invitations.createdAt,
};

const memberKey = (organizationId: string, userId: string) =>
  and(
    eq(organizationMembers.organizationId, organizationId),
    eq(organizationMembers.userId, userId),
  );

const pendingInvitation = (organizationId: string, invitationId: string) =>
  and(
    eq(invitations.organizationId, organizationId),
    eq(invitations.id, invitationId),
    pending,
  );

const invitationStatus = (
  target: z.infer<typeof InvitationTargetSchema>,
  now: Date,
): InvitationPreview["status"] => {
  if (!target.organizationActive || target.revokedAt) return "invalid";
  if (target.acceptedAt) return "accepted";

  return target.expiresAt <= now ? "expired" : "pending";
};

export const createMemberStore = (database: ControlDatabase) => {
  const selectMembers = () =>
    database
      .select(memberColumns)
      .from(organizationMembers)
      .innerJoin(users, eq(users.id, organizationMembers.userId));

  const selectInvitations = () =>
    database
      .select(invitationColumns)
      .from(invitations)
      .innerJoin(users, eq(users.id, invitations.createdBy));

  const findInvitation = async (
    organizationId: string,
    invitationId: string,
  ) => {
    const [row] = await selectInvitations().where(
      pendingInvitation(organizationId, invitationId),
    );

    return row ? InvitationRecordSchema.parse(row) : undefined;
  };

  // Locks every admin row in a fixed order so concurrent demotions serialize
  // and the second one sees that its actor is no longer an admin.
  const asAdmin = (
    organizationId: string,
    actorId: string,
    change: (transaction: Transaction) => Promise<unknown>,
  ) =>
    database.transaction(async (transaction) => {
      const admins = await transaction
        .select({ userId: organizationMembers.userId })
        .from(organizationMembers)
        .where(
          and(
            eq(organizationMembers.organizationId, organizationId),
            eq(organizationMembers.role, "admin"),
            eq(organizationMembers.status, "active"),
          ),
        )
        .orderBy(asc(organizationMembers.userId))
        .for("update");
      if (!admins.some((admin) => admin.userId === actorId)) return false;

      await change(transaction);

      return true;
    });

  return {
    async listMembers(organizationId: string) {
      const rows = await selectMembers()
        .where(
          and(
            eq(organizationMembers.organizationId, organizationId),
            eq(organizationMembers.status, "active"),
          ),
        )
        .orderBy(asc(organizationMembers.createdAt), asc(users.email));

      return rows.map((row) => MemberRecordSchema.parse(row));
    },

    async findMember(organizationId: string, userId: string) {
      const [row] = await selectMembers().where(
        and(
          memberKey(organizationId, userId),
          eq(organizationMembers.status, "active"),
        ),
      );

      return row ? MemberRecordSchema.parse(row) : undefined;
    },

    async findMemberEmails(organizationId: string, emails: string[]) {
      const rows = await selectMembers().where(
        and(
          eq(organizationMembers.organizationId, organizationId),
          inArray(sql`lower(${users.email})`, emails),
        ),
      );

      return rows.map((row) => row.email.toLowerCase());
    },

    async updateRole(
      organizationId: string,
      actorId: string,
      userId: string,
      role: OrganizationRole,
    ) {
      return asAdmin(organizationId, actorId, (transaction) =>
        transaction
          .update(organizationMembers)
          .set({
            role: OrganizationRoleSchema.parse(role),
            updatedAt: new Date(),
          })
          .where(memberKey(organizationId, userId)),
      );
    },

    async removeMember(
      organizationId: string,
      actorId: string,
      userId: string,
    ) {
      return asAdmin(organizationId, actorId, async (transaction) => {
        await transaction
          .delete(organizationMembers)
          .where(memberKey(organizationId, userId));

        // Admins cannot see playground keys, so removal revokes them.
        const revokedAt = new Date();
        await transaction
          .update(apiKeys)
          .set({ revokedAt, updatedAt: revokedAt })
          .where(
            and(
              eq(apiKeys.organizationId, organizationId),
              eq(apiKeys.createdBy, userId),
              eq(apiKeys.hidden, true),
              isNull(apiKeys.revokedAt),
            ),
          );
      });
    },

    async organizationName(organizationId: string) {
      const [row] = await database
        .select({ name: organizations.name })
        .from(organizations)
        .where(eq(organizations.id, organizationId));

      return row?.name;
    },

    async listInvitations(organizationId: string) {
      const rows = await selectInvitations()
        .where(and(eq(invitations.organizationId, organizationId), pending))
        .orderBy(asc(invitations.createdAt), asc(invitations.email));

      return rows.map((row) => InvitationRecordSchema.parse(row));
    },

    async upsertInvitation(input: {
      organizationId: string;
      email: string;
      role: OrganizationRole;
      tokenDigest: Buffer;
      createdBy: string;
      now: Date;
    }) {
      const values = {
        role: OrganizationRoleSchema.parse(input.role),
        tokenDigest: input.tokenDigest,
        expiresAt: expiresAfter(input.now),
        createdBy: input.createdBy,
        updatedAt: input.now,
      };
      const [row] = await database
        .insert(invitations)
        .values({
          ...values,
          id: uuidv7(),
          organizationId: input.organizationId,
          email: z.email().parse(input.email.trim().toLowerCase()),
          createdAt: input.now,
        })
        .onConflictDoUpdate({
          target: [invitations.organizationId, invitations.email],
          targetWhere: pending,
          set: values,
        })
        .returning({ id: invitations.id });

      return row && findInvitation(input.organizationId, row.id);
    },

    async reissueInvitation(
      organizationId: string,
      invitationId: string,
      tokenDigest: Buffer,
      now: Date,
    ) {
      await database
        .update(invitations)
        .set({ tokenDigest, expiresAt: expiresAfter(now), updatedAt: now })
        .where(pendingInvitation(organizationId, invitationId));

      return findInvitation(organizationId, invitationId);
    },

    async revokeInvitation(organizationId: string, invitationId: string) {
      const now = new Date();
      const revoked = await database
        .update(invitations)
        .set({ revokedAt: now, updatedAt: now })
        .where(pendingInvitation(organizationId, invitationId))
        .returning({ id: invitations.id });

      return revoked.length > 0;
    },

    async findByToken(token: string, now: Date) {
      const [row] = await database
        .select({
          ...invitationColumns,
          organizationName: organizations.name,
          organizationActive: sql<boolean>`(${activeCustomerOrganization})`,
          acceptedAt: invitations.acceptedAt,
          revokedAt: invitations.revokedAt,
        })
        .from(invitations)
        .innerJoin(users, eq(users.id, invitations.createdBy))
        .innerJoin(
          organizations,
          eq(organizations.id, invitations.organizationId),
        )
        .where(eq(invitations.tokenDigest, sha256Digest(token)));
      if (!row) return undefined;

      const target = InvitationTargetSchema.parse(row);

      return { ...target, status: invitationStatus(target, now) };
    },

    async accept(
      invitationId: string,
      userId: string,
      now: Date,
      token?: string,
    ) {
      return database.transaction(async (transaction) => {
        const [invitation] = await transaction
          .select({
            organizationId: invitations.organizationId,
            role: invitations.role,
          })
          .from(invitations)
          .where(
            and(
              eq(invitations.id, invitationId),
              pending,
              gt(invitations.expiresAt, now),
              token === undefined
                ? undefined
                : eq(invitations.tokenDigest, sha256Digest(token)),
            ),
          )
          .for("update");
        if (!invitation) return undefined;

        const joined = await transaction
          .insert(organizationMembers)
          .values({
            organizationId: invitation.organizationId,
            userId,
            role: invitation.role,
            status: "active",
            createdAt: now,
            updatedAt: now,
          })
          .onConflictDoNothing()
          .returning({ userId: organizationMembers.userId });
        if (!joined.length)
          return { organizationId: invitation.organizationId, joined: false };

        await transaction
          .update(invitations)
          .set({ acceptedAt: now, updatedAt: now })
          .where(eq(invitations.id, invitationId));

        return { organizationId: invitation.organizationId, joined: true };
      });
    },

    async pendingInvitationIdsForEmail(email: string, now: Date) {
      const rows = await database
        .select({ id: invitations.id })
        .from(invitations)
        .innerJoin(
          organizations,
          eq(organizations.id, invitations.organizationId),
        )
        .where(
          and(
            eq(invitations.email, email.trim().toLowerCase()),
            pending,
            gt(invitations.expiresAt, now),
            activeCustomerOrganization,
          ),
        )
        .orderBy(asc(invitations.createdAt));

      return rows.map((row) => row.id);
    },
  };
};
