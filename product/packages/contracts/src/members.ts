import { z } from "@hono/zod-openapi";

import {
  OrganizationIdParamsSchema,
  TimestampSchema,
  UuidSchema,
  pageFields,
} from "./common.js";
import { OrganizationRoleSchema } from "./me.js";

export const EmailInputSchema = z
  .string()
  .trim()
  .toLowerCase()
  .pipe(z.email().max(320));

export const MemberSchema = z
  .object({
    user_id: UuidSchema,
    email: z.email(),
    role: OrganizationRoleSchema,
    joined_at: TimestampSchema,
  })
  .openapi("Member");
export type Member = z.infer<typeof MemberSchema>;

export const MemberListSchema = z
  .object(pageFields(MemberSchema))
  .openapi("MemberList");

export const MemberParamsSchema = OrganizationIdParamsSchema.extend({
  user_id: UuidSchema,
});

export const UpdateMemberSchema = z
  .strictObject({ role: OrganizationRoleSchema })
  .openapi("UpdateMember");
export type UpdateMember = z.infer<typeof UpdateMemberSchema>;

export const InvitationSchema = z
  .object({
    id: UuidSchema,
    email: z.email(),
    role: OrganizationRoleSchema,
    invited_by_email: z.email(),
    expires_at: TimestampSchema,
    created_at: TimestampSchema,
  })
  .openapi("Invitation");
export type Invitation = z.infer<typeof InvitationSchema>;

export const InvitationListSchema = z
  .object(pageFields(InvitationSchema))
  .openapi("InvitationList");

export const CreateInvitationsSchema = z
  .strictObject({
    emails: z
      .array(EmailInputSchema)
      .min(1)
      .max(20)
      .describe("Up to 20 addresses; duplicates are ignored."),
    role: OrganizationRoleSchema,
  })
  .openapi("CreateInvitations");
export type CreateInvitations = z.infer<typeof CreateInvitationsSchema>;

export const InvitationParamsSchema = OrganizationIdParamsSchema.extend({
  invitation_id: UuidSchema,
});

export const InvitationTokenSchema = z
  .strictObject({
    token: z
      .string()
      .regex(/^[A-Za-z0-9_-]{43}$/)
      .describe("The secret from the invitation link."),
  })
  .openapi("InvitationToken");

export const InvitationPreviewSchema = z
  .discriminatedUnion("status", [
    z.object({
      status: z.enum(["pending", "expired", "accepted"]),
      organization_id: UuidSchema,
      organization_name: z.string(),
      email: z.email(),
      role: OrganizationRoleSchema,
      invited_by_email: z.email(),
    }),
    z.object({ status: z.literal("invalid") }),
  ])
  .openapi("InvitationPreview");
export type InvitationPreview = z.infer<typeof InvitationPreviewSchema>;
