import {
  TrainingTokenSchema,
  WorkspacePathSchema,
  problemContent,
} from "@gradiated/contracts";
import type { WorkspaceApiKeyService } from "@gradiated/control";
import { createRoute, type OpenAPIHono } from "@hono/zod-openapi";

import { consoleOnly } from "../http/audience.js";
import { requireUser } from "../http/problems.js";
import type { ApiEnvironment, AuthService } from "../types.js";

const createTrainingTokenRoute = createRoute({
  method: "post",
  path: "/api/v1/workspaces/{workspace_id}/training-tokens",
  operationId: "createTrainingToken",
  summary: "Create a training token",
  description:
    "Signs a ten-minute JWT with which the console calls the training API for this workspace as the signed-in member. Workspace credentials cannot call it.",
  tags: ["Workspaces"],
  ...consoleOnly,
  request: { params: WorkspacePathSchema },
  responses: {
    201: {
      description: "A signed training token.",
      headers: {
        "Cache-Control": {
          description: "Prevents storage of the token.",
          schema: { type: "string" },
        },
      },
      content: { "application/json": { schema: TrainingTokenSchema } },
    },
    401: {
      description: "Authentication is required.",
      content: problemContent,
    },
    403: {
      description:
        "The workspace is archived or the organization is suspended.",
      content: problemContent,
    },
    404: {
      description: "The workspace was not found.",
      content: problemContent,
    },
    503: {
      description: "The session store is unavailable.",
      content: problemContent,
    },
  },
});

export const registerTrainingTokenRoutes = (
  app: OpenAPIHono<ApiEnvironment>,
  workspaces: Pick<WorkspaceApiKeyService, "describeTrainingMember">,
  auth: Pick<AuthService, "signTrainingToken">,
) => {
  app.openapi(createTrainingTokenRoute, async (context) => {
    const user = await requireUser(context);
    const params = context.req.valid("param");

    const member = await workspaces.describeTrainingMember(
      user.id,
      params.workspace_id,
    );
    const { token, expiresAt } = await auth.signTrainingToken({
      userId: user.id,
      ...member,
    });

    context.set("logResourceIds", { workspace_id: member.workspaceId });
    context.header("Cache-Control", "no-store");
    return context.json({ token, expires_at: expiresAt.toISOString() }, 201);
  });
};
