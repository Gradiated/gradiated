import { z } from "@hono/zod-openapi";

import { TimestampSchema, UuidSchema } from "./common.js";

export const OrganizationRoleSchema = z.enum([
  "owner",
  "admin",
  "billing",
  "member",
]);

export const CurrentOrganizationSchema = z
  .object({
    id: UuidSchema,
    name: z.string().min(1).max(200),
    status: z.enum(["active", "suspended"]),
    role: OrganizationRoleSchema,
    default_workspace_id: UuidSchema,
  })
  .openapi("CurrentOrganization");

export const CurrentUserSchema = z
  .object({
    id: UuidSchema,
    name: z.string().min(1).max(200),
    email: z.email(),
    email_verified: z.boolean(),
    image_url: z.url().nullable(),
    created_at: TimestampSchema,
    organizations: z.array(CurrentOrganizationSchema),
  })
  .openapi("CurrentUser");

export type CurrentUser = z.infer<typeof CurrentUserSchema>;
