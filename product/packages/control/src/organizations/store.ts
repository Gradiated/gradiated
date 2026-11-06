import { and, asc, eq, sql, type SQL } from "drizzle-orm";
import { z } from "zod";

import {
  CurrentOrganizationSchema,
  EmailDomainSchema,
  OrganizationMetadataSchema,
  OrganizationNdaSchema,
  OrganizationOnboardingSchema,
  UpdateOrganizationSchema,
  UuidSchema,
  type OrganizationNda,
  type OrganizationOnboarding,
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

const organizationColumns = (userId: string) => ({
  id: organizations.id,
  name: organizations.name,
  status: organizations.status,
  role: customerRole(userId),
  defaultWorkspaceId: workspaces.id,
  autoJoinDomain: organizations.autoJoinDomain,
  onboardedAt: organizations.onboardedAt,
});

const MetadataRowSchema = z
  .object({ metadata: OrganizationMetadataSchema })
  .transform(({ metadata }) => metadata.onboarding ?? {});

const onboardingPath = sql`${organizations.metadata} -> 'onboarding'`;

export const createOrganizationStore = (database: ControlDatabase) => {
  const readOnboarding = async (organizationId: string) => {
    const [row] = await database
      .select({ metadata: organizations.metadata })
      .from(organizations)
      .where(eq(organizations.id, organizationId));

    return row ? MetadataRowSchema.parse(row) : undefined;
  };

  const mergeOnboarding = async (
    organizationId: string,
    patch: OrganizationOnboarding,
    condition: SQL,
  ) => {
    const value = JSON.stringify(OrganizationOnboardingSchema.parse(patch));
    const rows = await database
      .update(organizations)
      .set({
        metadata: sql`jsonb_set(${organizations.metadata}, '{onboarding}', coalesce(${onboardingPath}, '{}'::jsonb) || ${value}::jsonb)`,
        updatedAt: new Date(),
      })
      .where(and(eq(organizations.id, organizationId), condition))
      .returning({ metadata: organizations.metadata });

    return rows[0] ? MetadataRowSchema.parse(rows[0]) : undefined;
  };

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
    readOnboarding,

    async recordOnboardingNda(organizationId: string, nda: OrganizationNda) {
      const parsed = OrganizationNdaSchema.parse(nda);
      const recorded = await mergeOnboarding(
        organizationId,
        { nda: parsed },
        sql`(${onboardingPath} -> 'nda' ->> 'template_version') is distinct from ${parsed.template_version}`,
      );

      return recorded ?? readOnboarding(organizationId);
    },

    async submitOnboarding(
      organizationId: string,
      submission: Required<
        Pick<
          OrganizationOnboarding,
          "submitted_at" | "submitted_by" | "contact_channel"
        >
      >,
    ) {
      const submitted = await mergeOnboarding(
        organizationId,
        submission,
        sql`(${onboardingPath} ->> 'submitted_at') is null`,
      );
      if (submitted) return { submitted: true, onboarding: submitted };

      const onboarding = await readOnboarding(organizationId);

      return onboarding && { submitted: false, onboarding };
    },

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
