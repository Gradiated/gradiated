import { z } from "@hono/zod-openapi";

export const UuidSchema = z
  .uuid()
  .openapi({ example: "0198ae50-94d8-7d4d-a8be-9f9b44b8c774" });
export const DeploymentIdSchema = z
  .guid()
  .describe(
    "Deployment identifier, including unversioned Nomad allocation UUIDs.",
  )
  .openapi({ example: "a4d51466-8782-bf13-3b97-b8a07ad79c26" });

export const TimestampSchema = z.iso.datetime({ offset: true }).openapi({
  example: "2026-08-16T12:00:00.000Z",
});

export const ModelIdSchema = z.string().min(1).max(200);
export const NameSchema = z.string().min(1).max(200);
export const NameInputSchema = z.string().trim().min(1).max(200);
export const TokenCountSchema = z.number().int().nonnegative();
export const BoundedIdentifierSchema = z.string().min(1).max(300);
export const SnakeCaseCodeSchema = z.string().regex(/^[a-z][a-z0-9_]*$/);
export const UnsignedIntegerStringSchema = z.string().regex(/^\d+$/);
export const MoneySchema = z.string().regex(/^-?\d+$/, { abort: true });
export const ApiKeySecretSchema = z.string().regex(/^grad_[A-Za-z0-9_-]{43}$/);

export const GenerationStatusSchema = z.enum([
  "succeeded",
  "failed",
  "cancelled",
  "abandoned",
]);
export const CancellationOwnerSchema = z.enum(["client", "server", "runtime"]);

export const pageFields = <Item extends z.ZodType>(item: Item) => ({
  data: z.array(item),
  next_cursor: z.string().nullable(),
});

export const OrganizationIdParamsSchema = z.object({
  organization_id: UuidSchema,
});
