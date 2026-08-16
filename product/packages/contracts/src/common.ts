import { z } from "@hono/zod-openapi";

export const UuidSchema = z
  .uuid()
  .openapi({ example: "0198ae50-94d8-7d4d-a8be-9f9b44b8c774" });
export const TimestampSchema = z.iso.datetime({ offset: true }).openapi({
  example: "2026-08-16T12:00:00.000Z",
});

export const OrganizationIdParamsSchema = z.object({
  organization_id: UuidSchema,
});
