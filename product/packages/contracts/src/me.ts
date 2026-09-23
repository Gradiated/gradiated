import { z } from "@hono/zod-openapi";

import { NameSchema, TimestampSchema, UuidSchema } from "./common.js";

export const OrganizationRoleSchema = z.enum([
  "owner",
  "admin",
  "billing",
  "member",
]);

export const CurrentOrganizationSchema = z
  .object({
    id: UuidSchema,
    name: NameSchema,
    status: z.enum(["active", "suspended"]),
    role: OrganizationRoleSchema,
    default_workspace_id: UuidSchema,
  })
  .openapi("CurrentOrganization");

export const CurrentUserSchema = z
  .object({
    id: UuidSchema,
    name: NameSchema,
    email: z.email(),
    email_verified: z.boolean(),
    image_url: z.url().nullable(),
    created_at: TimestampSchema,
    organizations: z.array(CurrentOrganizationSchema),
  })
  .openapi("CurrentUser");

export type CurrentUser = z.infer<typeof CurrentUserSchema>;
