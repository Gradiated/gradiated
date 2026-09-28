import { DeploymentStatusReportSchema } from "@gradiated/contracts";
import {
  DeploymentStatusError,
  type DeploymentStatusFailure,
  type DeploymentStatusService,
} from "@gradiated/control";
import { Hono } from "hono";

import {
  bearerToken,
  handleIngestError,
  ingestBodyLimit,
  readJsonBody,
  tokenMatches,
} from "./http.js";
import { serviceLog } from "../logging.js";

interface DeploymentStatusIngestDependencies {
  tokens: ReadonlyMap<string, string>;
  service: DeploymentStatusService;
}

const failureStatus: Record<DeploymentStatusFailure, 403 | 404> = {
  deployment_not_found: 404,
  provider_mismatch: 403,
  runtime_revision_mismatch: 403,
};

const providerForToken = (
  authorization: string | undefined,
  tokens: ReadonlyMap<string, string>,
): string | undefined => {
  const supplied = bearerToken(authorization);
  if (!supplied) return undefined;

  for (const [provider, token] of tokens) {
    if (tokenMatches(supplied, token)) return provider;
  }

  return undefined;
};

export const createDeploymentStatusIngestApp = ({
  tokens,
  service,
}: DeploymentStatusIngestDependencies): Hono => {
  const app = new Hono();

  app.post(
    "/v1/deployment-status",
    ingestBodyLimit(64 * 1024),
    async (context) => {
      const provider = providerForToken(
        context.req.header("authorization"),
        tokens,
      );
      if (!provider) return context.json({ error: "unauthorized" }, 401);

      const body = await readJsonBody(context);
      if (!body.ok) return context.json({ error: "invalid_json" }, 400);

      const parsed = DeploymentStatusReportSchema.safeParse(body.value);
      if (!parsed.success) {
        return context.json({ error: "invalid_status" }, 422);
      }

      try {
        await service.report(provider, parsed.data);
      } catch (error) {
        if (!(error instanceof DeploymentStatusError)) throw error;

        serviceLog("warn", "deployment_status_rejected", {
          deployment_id: parsed.data.deployment_id,
          reason: error.code,
        });
        return context.json({ error: error.code }, failureStatus[error.code]);
      }

      return context.body(null, 204);
    },
  );
  app.onError(handleIngestError);

  return app;
};
