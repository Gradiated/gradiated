import { createHash } from "node:crypto";

import type {
  DeploymentStatusReport,
  ModelDeploymentRelease,
} from "@gradiated/contracts";
import { eq } from "drizzle-orm";

import type { ControlDatabase } from "../db/client.js";
import { modelDeployments } from "../db/schema/index.js";

interface DeploymentStatusValkey {
  expire(key: string, seconds: number): Promise<unknown>;
  hSet(key: string, field: string, value: string): Promise<unknown>;
}

export type DeploymentStatusFailure =
  "deployment_not_found" | "provider_mismatch" | "runtime_revision_mismatch";

export class DeploymentStatusError extends Error {
  constructor(public readonly code: DeploymentStatusFailure) {
    super(code);
  }
}

export interface DeploymentStatusService {
  report(provider: string, report: DeploymentStatusReport): Promise<void>;
}

export const servedReleaseDigest = (
  release: ModelDeploymentRelease,
): string => {
  const canonical = {
    schema_version: release.schema_version,
    runtime_revision: release.runtime_revision,
    model_path: release.model_path,
    model_revision: release.model_revision,
    ...(release.runtime_model_name === undefined
      ? {}
      : { runtime_model_name: release.runtime_model_name }),
    tokenizer_path: release.tokenizer_path,
    tokenizer_revision: release.tokenizer_revision,
    ...(release.tokenizer_mode === undefined
      ? {}
      : { tokenizer_mode: release.tokenizer_mode }),
  };
  return `sha256:${createHash("sha256")
    .update(JSON.stringify(canonical))
    .digest("hex")}`;
};

export const createDeploymentStatusService = (
  database: ControlDatabase,
  valkey: DeploymentStatusValkey,
): DeploymentStatusService => ({
  async report(provider, report) {
    const [deployment] = await database
      .select({
        id: modelDeployments.id,
        provider: modelDeployments.provider,
        release: modelDeployments.release,
      })
      .from(modelDeployments)
      .where(eq(modelDeployments.id, report.deployment_id))
      .limit(1);
    if (!deployment) {
      throw new DeploymentStatusError("deployment_not_found");
    }
    if (deployment.provider !== provider) {
      throw new DeploymentStatusError("provider_mismatch");
    }
    if (deployment.release.runtime_revision !== report.runtime_revision) {
      throw new DeploymentStatusError("runtime_revision_mismatch");
    }

    const key = `deployment-status:{${servedReleaseDigest(deployment.release)}}`;
    await valkey.hSet(
      key,
      deployment.id,
      JSON.stringify({
        ...report,
        received_at: new Date().toISOString(),
      }),
    );
    await valkey.expire(key, 8);
  },
});
