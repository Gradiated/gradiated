import { timingSafeEqual } from "node:crypto";
import { createRoute, OpenAPIHono, z } from "@hono/zod-openapi";
import { bodyLimit } from "hono/body-limit";
import { requestId } from "hono/request-id";
import {
  ArtifactReferenceSchema,
  UuidSchema,
  problemContent,
} from "@gradiated/contracts";
import type { EvalVersions } from "@gradiated/control";
import { problemResponse, problems, toApiProblem } from "./http/problems.js";
import type { ApiEnvironment } from "./types.js";

const evalVersions = createRoute({
  hide: true,
  method: "post",
  path: "/api/internal/v1/training/eval-versions",
  operationId: "publishEvalVersion",
  description:
    "Publishes an artifact as an eval-only version: in the workspace's hidden eval model, named by artifact ID, never promoted, callable only on the gateway's eval lane, and deleted with its pin 7 days after the last call here. Idempotent per workspace and artifact.",
  request: {
    body: {
      required: true,
      content: {
        "application/json": {
          schema: z.strictObject({
            workspace_id: UuidSchema,
            artifact_id: ArtifactReferenceSchema,
          }),
        },
      },
    },
  },
  responses: {
    200: {
      description: "The eval-only version and its gateway model name.",
      content: {
        "application/json": {
          schema: z.object({
            model: z.string().describe("`<org_slug>/<model>/<version>`."),
            version_id: UuidSchema,
          }),
        },
      },
    },
    401: { description: "Missing or wrong bearer.", content: problemContent },
    404: {
      description: "Unknown artifact or workspace.",
      content: problemContent,
    },
    409: { description: "Conflict.", content: problemContent },
    422: { description: "Not servable.", content: problemContent },
    503: {
      description: "grad or storage unavailable.",
      content: problemContent,
    },
  },
});

const matches = (presented: string, expected: readonly string[]) => {
  const candidate = Buffer.from(presented);
  return expected.reduce((matched, token) => {
    const known = Buffer.from(token);
    return (
      (known.length === candidate.length &&
        timingSafeEqual(known, candidate)) ||
      matched
    );
  }, false);
};

/**
 * The private listener grad-server calls (ClusterIP only), with a static bearer
 * and its previous value during a rotation.
 */
export const createTrainingInternalApp = ({
  tokens,
  evals,
}: {
  tokens: readonly string[];
  evals: EvalVersions;
}) => {
  const app = new OpenAPIHono<ApiEnvironment>({
    defaultHook: (result, context) => {
      if (result.success) return;
      return problemResponse(
        context,
        problems.validation(
          result.error.issues.map((issue) => ({
            path: issue.path.join("."),
            message: issue.message,
          })),
        ),
      );
    },
  });
  app.onError((error, context) =>
    problemResponse(context, toApiProblem(error)?.problem ?? problems.internal),
  );
  app.use("*", requestId());
  app.use(
    "/api/*",
    bodyLimit({
      maxSize: 64 * 1024,
      onError: (context) => problemResponse(context, problems.payloadTooLarge),
    }),
  );
  app.use("/api/internal/*", async (context, next) => {
    const presented = /^Bearer (\S+)$/.exec(
      context.req.header("authorization") ?? "",
    )?.[1];
    if (!presented || !matches(presented, tokens))
      return problemResponse(context, problems.unauthenticated);

    context.header("Cache-Control", "no-store");
    await next();
  });

  app.openapi(evalVersions, async (context) => {
    const body = context.req.valid("json");
    const published = await evals.publish(body.workspace_id, body.artifact_id);

    return context.json(
      { model: published.model, version_id: published.version.id },
      200,
    );
  });

  return app;
};
