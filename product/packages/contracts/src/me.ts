import { z } from "@hono/zod-openapi";

import { NameSchema, TimestampSchema, UuidSchema } from "./common.js";

export const OrganizationRoleSchema = z
  .enum(["admin", "member"])
  .openapi("OrganizationRole");
export type OrganizationRole = z.infer<typeof OrganizationRoleSchema>;

export const EmailDomainSchema = z
  .string()
  .trim()
  .toLowerCase()
  .max(253)
  .regex(/^[a-z0-9-]+(\.[a-z0-9-]+)+$/, "Enter a domain such as acme.com.");

export const ORGANIZATION_SLUG_PATTERN = /^[a-z0-9][a-z0-9-]{0,37}[a-z0-9]$/;
export const OrganizationSlugSchema = z
  .string()
  .regex(ORGANIZATION_SLUG_PATTERN)
  .describe(
    "Unique organization handle that prefixes its private model names, as in `acme/support-triage`. It is fixed once the organization has a model.",
  )
  .openapi("OrganizationSlug");
export const OrganizationSlugInputSchema = z
  .string()
  .trim()
  .toLowerCase()
  .regex(
    ORGANIZATION_SLUG_PATTERN,
    "Use 2 to 39 lowercase letters, numbers or hyphens, starting and ending with a letter or number.",
  );

export const CurrentOrganizationSchema = z
  .object({
    id: UuidSchema,
    name: NameSchema,
    slug: OrganizationSlugSchema,
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
    impersonated_by: UuidSchema.nullable().describe(
      "The staff actor when viewing the console as another user.",
    ),
    impersonation_expires_at: TimestampSchema.nullable().describe(
      "The server-enforced impersonation deadline, or null outside impersonation.",
    ),
    is_staff: z
      .boolean()
      .describe("Whether the user may access the staff portal."),
    company_email_domain: EmailDomainSchema.nullable().describe(
      "The verified email domain this user may offer for automatic joining, or null for personal and unverified addresses.",
    ),
    image_url: z.url().nullable(),
    created_at: TimestampSchema,
    organizations: z.array(CurrentOrganizationSchema),
  })
  .openapi("CurrentUser");

export type CurrentUser = z.infer<typeof CurrentUserSchema>;
