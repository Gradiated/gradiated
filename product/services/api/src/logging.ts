import { createServiceLogger } from "@gradiated/control";

import type { Context } from "hono";
import type { ApiEnvironment } from "./types.js";

export const serviceLog = createServiceLogger("api");

// Route IDs describe the requested resource, not an authorization decision.
export const requestLogFields = (context: Context<ApiEnvironment>) => {
  const user = context.get("sessionUser");

  return {
    request_id: context.get("requestId"),
    ...(user
      ? {
          user_id: user.id,
          organization_id: context.req.param("organization_id"),
          workspace_id: context.req.param("workspace_id"),
          api_key_id: context.req.param("api_key_id"),
          ...context.get("logResourceIds"),
          context_source: "authenticated_session_requested_resource" as const,
        }
      : {}),
  };
};
