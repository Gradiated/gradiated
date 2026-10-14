import { and, asc, eq, sql } from "drizzle-orm";
import { z } from "zod";

import {
  CurrentOrganizationSchema,
  EmailDomainSchema,
  UpdateOrganizationSchema,
  UuidSchema,
  type UpdateOrganization,
} from "@gradiated/contracts";
import type { ControlDatabase } from "../db/client.js";
import {
  organizations,
  organizationMembers,
  users,
  workspaces,
} from "../db/schema/index.js";
import { activeCustomerMember } from "../access.js";
import { ControlServiceError } from "../errors.js";

const OrganizationRecordSchema = CurrentOrganizationSchema.pick({
  id: true,
  name: true,
  status: true,
  role: true,
})
  .extend({
    defaultWorkspaceId: UuidSchema,
    autoJoinDomain: EmailDomainSchema.nullable(),
    onboardedAt: z.date().nullable(),
  })
  .transform(({ onboardedAt, ...organization }) => ({
    ...organization,
    onboardingCompleted: onboardedAt !== null,
  }));

const SignupEmailSchema = z.object({
  email: z.email(),
  emailVerified: z.boolean(),
});

const organizationColumns = {
  id: organizations.id,
  name: organizations.name,
  status: organizations.status,
  role: organizationMembers.role,
  defaultWorkspaceId: workspaces.id,
  autoJoinDomain: organizations.autoJoinDomain,
  onboardedAt: organizations.onboardedAt,
};

export const createOrganizationStore = (database: ControlDatabase) => {
  const listForUser = async (userId: string, organizationId?: string) => {
    const rows = await database
      .select(organizationColumns)
      .from(organizationMembers)
      .innerJoin(
        organizations,
        eq(organizations.id, organizationMembers.organizationId),
      )
      .innerJoin(
        workspaces,
        and(
          eq(workspaces.organizationId, organizations.id),
          eq(workspaces.isDefault, true),
        ),
      )
      .where(activeCustomerMember({ userId, organizationId }))
      .orderBy(asc(organizations.createdAt), asc(organizations.id));

    return rows.map((row) => OrganizationRecordSchema.parse(row));
  };

  return {
    listForUser,

    async findUser(userId: string) {
      const [user] = await database
        .select({ email: users.email, emailVerified: users.emailVerified })
        .from(users)
        .where(eq(users.id, userId));

      return user ? SignupEmailSchema.parse(user) : undefined;
    },

    async joinByDomain(userId: string, domain: string) {
      return database.transaction(async (transaction) => {
        const [organization] = await transaction
          .select({ id: organizations.id })
          .from(organizations)
          .where(
            and(
              eq(organizations.autoJoinDomain, domain),
              eq(organizations.kind, "customer"),
              eq(organizations.status, "active"),
            ),
          )
          .for("share");
        if (!organization) return undefined;

        const now = new Date();
        await transaction
          .insert(organizationMembers)
          .values({
            organizationId: organization.id,
            userId,
            role: "member",
            status: "active",
            createdAt: now,
            updatedAt: now,
          })
          .onConflictDoNothing();

        return organization.id;
      });
    },

    async update(
      userId: string,
      organizationId: string,
      input: UpdateOrganization,
    ) {
      const update = UpdateOrganizationSchema.parse(input);

      await database
        .update(organizations)
        .set({
          name: update.name,
          autoJoinDomain: update.auto_join_domain,
          onboardedAt: update.onboarding_completed
            ? sql`coalesce(${organizations.onboardedAt}, now())`
            : undefined,
          updatedAt: new Date(),
        })
        .where(eq(organizations.id, organizationId))
        .catch((error: unknown) => {
          if (isClaimedDomain(error))
            throw new ControlServiceError(
              "conflict",
              "Another organization already lets this email domain join automatically.",
              error,
            );
          throw error;
        });

      const [organization] = await listForUser(userId, organizationId);

      return organization;
    },
  };
};

const isClaimedDomain = (error: unknown): boolean => {
  if (!error || typeof error !== "object") return false;
  if (
    "code" in error &&
    error.code === "23505" &&
    "constraint" in error &&
    error.constraint === "organizations_auto_join_domain_unique"
  )
    return true;
  return (
    "cause" in error && error.cause !== error && isClaimedDomain(error.cause)
  );
};
