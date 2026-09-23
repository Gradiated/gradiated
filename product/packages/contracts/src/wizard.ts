import { z } from "@hono/zod-openapi";

import { ApiKeySecretSchema, NameSchema, UuidSchema } from "./common.js";
import { ApiKeySchema } from "./workspaces.js";

export const WizardKeyResponseSchema = z
  .object({
    api_key: ApiKeySchema,
    secret: ApiKeySecretSchema,
    organization_id: UuidSchema,
    workspace_id: UuidSchema,
    organization_name: NameSchema,
    balance_nano_usd: z.number().int(),
  })
  .openapi("WizardKeyResponse");

export type WizardKeyResponse = z.infer<typeof WizardKeyResponseSchema>;
