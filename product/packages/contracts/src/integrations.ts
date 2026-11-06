import { z } from "@hono/zod-openapi";

import { TimestampSchema } from "./common.js";

export const INTEGRATION_PROVIDERS = ["github", "slack"] as const;
export const INTEGRATION_STATUSES = ["pending", "active", "revoked"] as const;

export const IntegrationStatusSchema = z.enum(INTEGRATION_STATUSES);
export type IntegrationStatus = z.infer<typeof IntegrationStatusSchema>;

export const SlackChannelIdSchema = z.string().regex(/^[CG][A-Z0-9]+$/);
export const GithubInstallationIdSchema = z
  .string()
  .regex(/^[1-9][0-9]{0,19}$/);

export const SlackIntegrationSettingsSchema = z.strictObject({
  schema_version: z.literal(1),
  channel_name: z.string().min(1).max(80),
  invited_email: z.email().max(200).optional(),
  invited_at: TimestampSchema.optional(),
});
export type SlackIntegrationSettings = z.infer<
  typeof SlackIntegrationSettingsSchema
>;

export const GithubIntegrationSettingsSchema = z.strictObject({
  schema_version: z.literal(1),
  account_login: z.string().min(1).max(100),
  repository_selection: z.enum(["all", "selected"]),
});
export type GithubIntegrationSettings = z.infer<
  typeof GithubIntegrationSettingsSchema
>;
