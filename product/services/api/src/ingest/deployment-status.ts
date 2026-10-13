import { DeploymentStatusReportSchema } from "@gradiated/contracts";
import {
  DeploymentStatusError,
  type DeploymentStatusFailure,
  type DeploymentStatusService,
} from "@gradiated/control";
import { Hono } from "hono";

import { handleIngestError, ingestBodyLimit, readJsonBody } from "./http.js";
import { serviceLog } from "../logging.js";

type DeploymentStatusIngestDependencies = {
  service: DeploymentStatusService;
  provider: string;
};

const failureStatus: Record<DeploymentStatusFailure, 403 | 404> = {
  deployment_not_found: 404,
  provider_mismatch: 403,
  runtime_revision_mismatch: 403,
};

export const createDeploymentStatusIngestApp = ({
  provider,
  service,
}: DeploymentStatusIngestDependencies): Hono => {
  const app = new Hono();

  app.post(
    "/v1/deployment-status",
    ingestBodyLimit(64 * 1024),
    async (context) => {
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
