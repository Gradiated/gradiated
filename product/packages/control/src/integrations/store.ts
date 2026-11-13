import { and, asc, eq, sql } from "drizzle-orm";
import { v7 as uuidv7 } from "uuid";
import { z } from "zod";

import {
  GithubInstallationIdSchema,
  GithubIntegrationSettingsSchema,
  IntegrationStatusSchema,
  SlackChannelIdSchema,
  SlackIntegrationSettingsSchema,
  UuidSchema,
  type GithubIntegrationSettings,
  type IntegrationStatus,
} from "@gradiated/contracts";
import type { ControlDatabase } from "../db/client.js";
import { integrations } from "../db/schema/index.js";

const recordFields = {
  id: UuidSchema,
  organizationId: UuidSchema,
  status: IntegrationStatusSchema,
  createdBy: UuidSchema,
  createdAt: z.date(),
  updatedAt: z.date(),
};

const SlackIntegrationRecordSchema = z.object({
  ...recordFields,
  provider: z.literal("slack"),
  externalId: SlackChannelIdSchema,
  settings: SlackIntegrationSettingsSchema,
});
const GithubIntegrationRecordSchema = z.object({
  ...recordFields,
  provider: z.literal("github"),
  externalId: GithubInstallationIdSchema,
  settings: GithubIntegrationSettingsSchema,
});
const IntegrationRecordSchema = z.discriminatedUnion("provider", [
  SlackIntegrationRecordSchema,
  GithubIntegrationRecordSchema,
]);

export type IntegrationRecord = z.infer<typeof IntegrationRecordSchema>;
export type SlackIntegrationRecord = z.infer<
  typeof SlackIntegrationRecordSchema
>;
export type GithubIntegrationRecord = z.infer<
  typeof GithubIntegrationRecordSchema
>;

const SlackInvitationSchema = SlackIntegrationSettingsSchema.pick({
  invited_email: true,
  invited_at: true,
});
export type SlackInvitationSettings = z.infer<typeof SlackInvitationSchema>;

const notRevoked = sql`${integrations.status} <> 'revoked'`;

const owned = (organizationId: string, integrationId: string) =>
  and(
    eq(integrations.organizationId, organizationId),
    eq(integrations.id, integrationId),
    notRevoked,
  );

const isUniqueViolation = (error: unknown): boolean => {
  if (!error || typeof error !== "object") return false;
  if ("code" in error && error.code === "23505") return true;

  return (
    "cause" in error && error.cause !== error && isUniqueViolation(error.cause)
  );
};

export const createIntegrationStore = (database: ControlDatabase) => {
  const parseSlack = (rows: unknown[]) =>
    rows[0] ? SlackIntegrationRecordSchema.parse(rows[0]) : undefined;

  return {
    async list(organizationId: string) {
      const rows = await database
        .select()
        .from(integrations)
        .where(and(eq(integrations.organizationId, organizationId), notRevoked))
        .orderBy(asc(integrations.createdAt), asc(integrations.id));

      return rows.map((row) => IntegrationRecordSchema.parse(row));
    },

    async findSlack(organizationId: string) {
      return parseSlack(
        await database
          .select()
          .from(integrations)
          .where(
            and(
              eq(integrations.organizationId, organizationId),
              eq(integrations.provider, "slack"),
              notRevoked,
            ),
          ),
      );
    },

    async insertSlack(input: {
      organizationId: string;
      channelId: string;
      channelName: string;
      createdBy: string;
      now: Date;
    }) {
      const values = SlackIntegrationRecordSchema.parse({
        id: uuidv7(),
        organizationId: input.organizationId,
        provider: "slack",
        externalId: input.channelId,
        status: "pending",
        settings: { schema_version: 1, channel_name: input.channelName },
        createdBy: input.createdBy,
        createdAt: input.now,
        updatedAt: input.now,
      });

      try {
        return parseSlack(
          await database.insert(integrations).values(values).returning(),
        );
      } catch (error) {
        if (isUniqueViolation(error)) return undefined;

        throw error;
      }
    },

    async claimSlackInvitation(input: {
      organizationId: string;
      integrationId: string;
      email: string;
      now: Date;
      availableAfter: Date;
    }) {
      const invitation = SlackInvitationSchema.required().parse({
        invited_email: input.email,
        invited_at: input.now.toISOString(),
      });

      return parseSlack(
        await database
          .update(integrations)
          .set({
            settings: sql`${integrations.settings} || ${JSON.stringify(invitation)}::jsonb`,
            updatedAt: input.now,
          })
          .where(
            and(
              owned(input.organizationId, input.integrationId),
              eq(integrations.provider, "slack"),
              sql`(${integrations.settings} ->> 'invited_at' is null or (${integrations.settings} ->> 'invited_at')::timestamptz <= ${input.availableAfter.toISOString()}::timestamptz)`,
            ),
          )
          .returning(),
      );
    },

    async restoreSlackInvitation(input: {
      organizationId: string;
      integrationId: string;
      claimedAt: string;
      previous: SlackInvitationSettings;
    }) {
      const previous = JSON.stringify(
        SlackInvitationSchema.parse(input.previous),
      );

      await database
        .update(integrations)
        .set({
          settings: sql`(${integrations.settings} - 'invited_email' - 'invited_at') || ${previous}::jsonb`,
          updatedAt: new Date(),
        })
        .where(
          and(
            owned(input.organizationId, input.integrationId),
            sql`${integrations.settings} ->> 'invited_at' = ${input.claimedAt}`,
          ),
        );
    },

    async setStatus(
      organizationId: string,
      integrationId: string,
      status: IntegrationStatus,
    ) {
      const rows = await database
        .update(integrations)
        .set({
          status: IntegrationStatusSchema.parse(status),
          updatedAt: new Date(),
        })
        .where(owned(organizationId, integrationId))
        .returning();

      return rows[0] ? IntegrationRecordSchema.parse(rows[0]) : undefined;
    },

    async upsertGithub(input: {
      organizationId: string;
      installationId: string;
      settings: GithubIntegrationSettings;
      createdBy: string;
      now: Date;
    }) {
      const values = GithubIntegrationRecordSchema.parse({
        id: uuidv7(),
        organizationId: input.organizationId,
        provider: "github",
        externalId: input.installationId,
        status: "active",
        settings: input.settings,
        createdBy: input.createdBy,
        createdAt: input.now,
        updatedAt: input.now,
      });
      const rows = await database
        .insert(integrations)
        .values(values)
        .onConflictDoUpdate({
          target: [integrations.provider, integrations.externalId],
          targetWhere: notRevoked,
          set: {
            status: "active",
            settings: values.settings,
            updatedAt: input.now,
          },
          setWhere: eq(integrations.organizationId, input.organizationId),
        })
        .returning();

      return rows[0] ? GithubIntegrationRecordSchema.parse(rows[0]) : undefined;
    },
  };
};
