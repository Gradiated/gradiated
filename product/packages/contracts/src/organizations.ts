import { z } from "@hono/zod-openapi";

import { TimestampSchema, UuidSchema } from "./common.js";

export const CreateOrganizationSchema = z
  .strictObject({
    name: z.string().trim().min(1).max(200),
  })
  .openapi("CreateOrganization");

export const OrganizationSchema = z
  .object({
    id: UuidSchema,
    kind: z.literal("customer"),
    name: z.string().min(1).max(200),
    status: z.literal("active"),
    role: z.literal("owner"),
    default_workspace_id: UuidSchema,
    created_at: TimestampSchema,
    updated_at: TimestampSchema,
  })
  .openapi("Organization");

export type CreateOrganization = z.infer<typeof CreateOrganizationSchema>;
export type Organization = z.infer<typeof OrganizationSchema>;
