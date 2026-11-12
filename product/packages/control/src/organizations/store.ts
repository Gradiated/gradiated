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
import {
  customerAccess,
  customerRole,
  activeCustomerOrganization,
} from "../access.js";
import { ControlServiceError } from "../errors.js";
import { isTakenOrganizationSlug, requireChangeableSlug } from "./slugs.js";

const OrganizationRecordSchema = CurrentOrganizationSchema.pick({
  id: true,
  name: true,
  slug: true,
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

const organizationColumns = (userId: string) => ({
  id: organizations.id,
  name: organizations.name,
  slug: organizations.slug,
  status: organizations.status,
  role: customerRole(userId),
  defaultWorkspaceId: workspaces.id,
  autoJoinDomain: organizations.autoJoinDomain,
  onboardedAt: organizations.onboardedAt,
});

export const createOrganizationStore = (database: ControlDatabase) => {
  const listForUser = async (
    userId: string,
    organizationId?: string,
    page?: { search: string; limit: number; offset: number },
  ) => {
    const query = database
      .select(organizationColumns(userId))
      .from(organizations)
      .leftJoin(
        organizationMembers,
        and(
          eq(organizations.id, organizationMembers.organizationId),
          eq(organizationMembers.userId, userId),
        ),
      )
      .innerJoin(
        workspaces,
        and(
          eq(workspaces.organizationId, organizations.id),
          eq(workspaces.isDefault, true),
        ),
      )
      .where(
        and(
          customerAccess({ userId, organizationId }),
          !organizationId && !page
            ? and(
                eq(organizationMembers.userId, userId),
                eq(organizationMembers.status, "active"),
              )
            : undefined,
          page?.search
            ? sql`strpos(lower(${organizations.name}), lower(${page.search})) > 0`
            : undefined,
        ),
      )
      .orderBy(asc(organizations.createdAt), asc(organizations.id));
    const rows = page
      ? await query.limit(page.limit).offset(page.offset)
      : organizationId
        ? await query.limit(1)
        : await query;

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
              activeCustomerOrganization,
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
        .transaction(async (transaction) => {
          const [current] = await transaction
            .select({ slug: organizations.slug })
            .from(organizations)
            .where(eq(organizations.id, organizationId))
            .for("update");
          if (update.slug !== undefined && update.slug !== current?.slug)
            await requireChangeableSlug(
              transaction,
              organizationId,
              update.slug,
            );

          await transaction
            .update(organizations)
            .set({
              name: update.name,
              slug: update.slug,
              autoJoinDomain: update.auto_join_domain,
              onboardedAt: update.onboarding_completed
                ? sql`coalesce(${organizations.onboardedAt}, now())`
                : undefined,
              updatedAt: new Date(),
            })
            .where(eq(organizations.id, organizationId));
        })
        .catch((error: unknown) => {
          if (isTakenOrganizationSlug(error))
            throw new ControlServiceError(
              "conflict",
              "Another organization already uses this slug.",
              error,
            );
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
