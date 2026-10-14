import { z } from "@hono/zod-openapi";

import { NameSchema, TimestampSchema, UuidSchema } from "./common.js";

export const OrganizationRoleSchema = z.enum([
  "owner",
  "admin",
  "billing",
  "member",
]);

export const EmailDomainSchema = z
  .string()
  .trim()
  .toLowerCase()
  .max(253)
  .regex(/^[a-z0-9-]+(\.[a-z0-9-]+)+$/, "Enter a domain such as acme.com.");

export const CurrentOrganizationSchema = z
  .object({
    id: UuidSchema,
    name: NameSchema,
    status: z.enum(["active", "suspended"]),
    role: OrganizationRoleSchema,
    default_workspace_id: UuidSchema,
    auto_join_domain: EmailDomainSchema.nullable().describe(
      "Users who sign up with a verified email at this domain join the organization automatically.",
    ),
    onboarding_completed: z
      .boolean()
      .describe("Whether the owner has finished first-run setup."),
  })
  .openapi("CurrentOrganization");

export const CurrentUserSchema = z
  .object({
    id: UuidSchema,
    name: NameSchema,
    email: z.email(),
    email_verified: z.boolean(),
    company_email_domain: EmailDomainSchema.nullable().describe(
      "The verified email domain this user may offer for automatic joining, or null for personal and unverified addresses.",
    ),
    image_url: z.url().nullable(),
    created_at: TimestampSchema,
    organizations: z.array(CurrentOrganizationSchema),
  })
  .openapi("CurrentUser");

export type CurrentUser = z.infer<typeof CurrentUserSchema>;
