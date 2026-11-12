import { z } from "@hono/zod-openapi";

import {
  NameInputSchema,
  NameSchema,
  TimestampSchema,
  UuidSchema,
} from "./common.js";
import {
  EmailDomainSchema,
  OrganizationSlugInputSchema,
  OrganizationSlugSchema,
} from "./me.js";

export const CreateOrganizationSchema = z
  .strictObject({
    name: NameInputSchema,
    slug: OrganizationSlugInputSchema.optional(),
  })
  .openapi("CreateOrganization");

export const UpdateOrganizationSchema = z
  .strictObject({
    name: NameInputSchema,
    slug: OrganizationSlugInputSchema,
    auto_join_domain: EmailDomainSchema.nullable().describe(
      "Must match the caller's verified company email domain, or null to stop automatic joining.",
    ),
    onboarding_completed: z.literal(true),
  })
  .partial()
  .refine(
    (input) => Object.keys(input).length > 0,
    "Provide at least one organization field.",
  )
  .openapi("UpdateOrganization");
export type UpdateOrganization = z.infer<typeof UpdateOrganizationSchema>;

export const OrganizationSchema = z
  .object({
    id: UuidSchema,
    kind: z.literal("customer"),
    name: NameSchema,
    slug: OrganizationSlugSchema,
    status: z.literal("active"),
    role: z.literal("admin"),
    default_workspace_id: UuidSchema,
    created_at: TimestampSchema,
    updated_at: TimestampSchema,
  })
  .openapi("Organization");

export type CreateOrganization = z.infer<typeof CreateOrganizationSchema>;
export type Organization = z.infer<typeof OrganizationSchema>;

export const ContactChannelSchema = z
  .enum(["slack", "email"])
  .describe("How the customer prefers Gradiated engineers to contact them.");
export type ContactChannel = z.infer<typeof ContactChannelSchema>;

export const OrganizationNdaSchema = z.strictObject({
  document_id: z.string().regex(/^[a-zA-Z0-9_-]{1,100}$/),
  template_version: z.string().min(1).max(200),
  signed_at: TimestampSchema,
});
export type OrganizationNda = z.infer<typeof OrganizationNdaSchema>;

export const OrganizationOnboardingSchema = z.strictObject({
  nda: OrganizationNdaSchema.optional(),
  submitted_at: TimestampSchema.optional(),
  submitted_by: UuidSchema.optional(),
  contact_channel: ContactChannelSchema.optional(),
});
export type OrganizationOnboarding = z.infer<
  typeof OrganizationOnboardingSchema
>;

export const OrganizationMetadataSchema = z.strictObject({
  schema_version: z.literal(1),
  training_onboarding: OrganizationOnboardingSchema.optional(),
});
export type OrganizationMetadata = z.infer<typeof OrganizationMetadataSchema>;
