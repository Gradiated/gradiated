import { z } from "@hono/zod-openapi";
import { UuidSchema } from "./common.js";

export const ImpersonationInputSchema = z
  .strictObject({ user_id: UuidSchema })
  .openapi("ImpersonationInput");
export const ImpersonationResultSchema = z
  .object({ user_id: UuidSchema })
  .openapi("ImpersonationResult");
