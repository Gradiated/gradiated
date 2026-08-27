import { timingSafeEqual } from "node:crypto";

import { DeploymentStatusReportSchema } from "@gradiated/contracts";
import {
  DeploymentStatusError,
  type DeploymentStatusService,
} from "@gradiated/control";
import { Hono } from "hono";
import { bodyLimit } from "hono/body-limit";

interface DeploymentStatusIngestDependencies {
  tokens: ReadonlyMap<string, string>;
  service: DeploymentStatusService;
}

const providerForToken = (
  authorization: string | undefined,
  tokens: ReadonlyMap<string, string>,
): string | undefined => {
  if (!authorization?.startsWith("Bearer ")) return undefined;
  const supplied = Buffer.from(authorization.slice("Bearer ".length));
  for (const [provider, token] of tokens) {
    const expected = Buffer.from(token);
    if (
      supplied.length === expected.length &&
      timingSafeEqual(supplied, expected)
    ) {
      return provider;
    }
  }
  return undefined;
};

export const parseDeploymentStatusTokens = (
  value: string | undefined,
): ReadonlyMap<string, string> => {
  if (!value) return new Map();
  const parsed: unknown = JSON.parse(value);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("DEPLOYMENT_STATUS_INGEST_TOKENS must be a JSON object");
  }
  const tokens = new Map<string, string>();
  for (const [provider, token] of Object.entries(parsed)) {
    if (!/^[a-z][a-z0-9_-]{0,99}$/.test(provider)) {
      throw new Error("Deployment status provider names are invalid");
    }
    if (typeof token !== "string" || token.length < 32) {
      throw new Error("Deployment status tokens must contain 32 characters");
    }
    tokens.set(provider, token);
  }
  return tokens;
};

export const createDeploymentStatusIngestApp = ({
  tokens,
  service,
}: DeploymentStatusIngestDependencies): Hono => {
  const app = new Hono();
  app.use(
    "*",
    bodyLimit({
      maxSize: 64 * 1024,
      onError: (context) => context.json({ error: "payload_too_large" }, 413),
    }),
  );
  app.post("/v1/deployment-status", async (context) => {
    const provider = providerForToken(
      context.req.header("authorization"),
      tokens,
    );
    if (!provider) return context.json({ error: "unauthorized" }, 401);

    let payload: unknown;
    try {
      payload = await context.req.json();
    } catch {
      return context.json({ error: "invalid_json" }, 400);
    }
    const parsed = DeploymentStatusReportSchema.safeParse(payload);
    if (!parsed.success) {
      return context.json({ error: "invalid_status" }, 422);
    }
    try {
      await service.report(provider, parsed.data);
    } catch (error) {
      if (error instanceof DeploymentStatusError) {
        const status = error.code === "deployment_not_found" ? 404 : 403;
        return context.json({ error: error.code }, status);
      }
      throw error;
    }
    return context.body(null, 204);
  });
  return app;
};
