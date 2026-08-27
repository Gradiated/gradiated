import { z } from "@hono/zod-openapi";

import { UuidSchema } from "./common.js";
import { ApiKeySchema } from "./workspaces.js";

export const WizardKeyResponseSchema = z
  .object({
    api_key: ApiKeySchema,
    secret: z.string().regex(/^grad_[A-Za-z0-9_-]{43}$/),
    organization_id: UuidSchema,
    workspace_id: UuidSchema,
    organization_name: z.string().min(1).max(200),
    balance_nano_usd: z.number().int(),
  })
  .openapi("WizardKeyResponse");

export type WizardKeyResponse = z.infer<typeof WizardKeyResponseSchema>;
