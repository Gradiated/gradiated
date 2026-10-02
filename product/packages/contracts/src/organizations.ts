import { z } from "@hono/zod-openapi";

import {
  NameInputSchema,
  NameSchema,
  TimestampSchema,
  UuidSchema,
} from "./common.js";

export const CreateOrganizationSchema = z
  .strictObject({
    name: NameInputSchema,
  })
  .openapi("CreateOrganization");

export const UpdateOrganizationSchema = z
  .strictObject({ name: NameInputSchema })
  .openapi("UpdateOrganization");
export type UpdateOrganization = z.infer<typeof UpdateOrganizationSchema>;

export const OrganizationSchema = z
  .object({
    id: UuidSchema,
    kind: z.literal("customer"),
    name: NameSchema,
    status: z.literal("active"),
    role: z.literal("owner"),
    default_workspace_id: UuidSchema,
    created_at: TimestampSchema,
    updated_at: TimestampSchema,
  })
  .openapi("Organization");

export type CreateOrganization = z.infer<typeof CreateOrganizationSchema>;
export type Organization = z.infer<typeof OrganizationSchema>;
