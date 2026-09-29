import { readFileSync } from "node:fs";
import { setTimeout as delay } from "node:timers/promises";
import {
  createControlDatabase,
  createWorkspaceApiKeyService,
} from "@gradiated/control";
import { z } from "zod";
import { verifyModel } from "./model-verification.js";

const input = z
  .object({
    modelId: z.string().min(1).max(300),
    stage: z.enum(["canary", "serving"]),
    deploymentIds: z.array(z.uuid()).min(1),
    protocol: z.literal("system_one").optional(),
    runtimeRevision: z.string().min(1).max(300),
  })
  .strict()
  .parse(JSON.parse(readFileSync(0, "utf8")));
const environment = z
  .object({
    DATABASE_URL: z.string().min(1),
    MODEL_VERIFICATION_WORKSPACE_ID: z.uuid(),
    MODEL_VERIFICATION_USER_ID: z.uuid(),
  })
  .parse(process.env);
const { database, pool } = createControlDatabase(environment.DATABASE_URL, 1);
const keys = createWorkspaceApiKeyService(database);
const abort = new AbortController();
process.once("SIGTERM", () => abort.abort());
process.once("SIGINT", () => abort.abort());
const timeout = setTimeout(() => {
  console.error(JSON.stringify({ event: "model_sdk_verification_timed_out" }));
  process.exit(1);
}, 8 * 60_000).unref();
const signal = AbortSignal.any([abort.signal, AbortSignal.timeout(8 * 60_000)]);
let issued: Awaited<ReturnType<typeof keys.createApiKey>> | undefined;
let stage = "reconciliation";
try {
  const deadline = Date.now() + 90_000;
  for (;;) {
    const { rows } = await pool.query<{
      id: string;
      status: string;
      revision: string;
    }>(
      "select id,status,release->>'runtime_revision' as revision from model_deployments where model_id=$1 and (id=any($2::uuid[]) or status='available')",
      [input.modelId, input.deploymentIds],
    );
    const visible = input.deploymentIds.every((id) =>
      rows.some(
        (row) =>
          row.id === id &&
          row.revision === input.runtimeRevision &&
          (row.status === "available" ||
            (input.stage === "canary" && row.status === "unavailable")),
      ),
    );
    const promoted =
      input.stage === "canary" ||
      rows.every(
        (row) =>
          row.status !== "available" || input.deploymentIds.includes(row.id),
      );
    if (visible && promoted) break;
    if (Date.now() >= deadline)
      throw new Error("Deployment reconciliation did not converge");
    await delay(1000, undefined, { signal });
  }
  await delay(16_000, undefined, { signal });
  stage = "key_issue";
  issued = await keys.createApiKey(
    environment.MODEL_VERIFICATION_USER_ID,
    environment.MODEL_VERIFICATION_WORKSPACE_ID,
    {
      name: "Nomad SDK rollout verification",
      expiresAt: new Date(Date.now() + 15 * 60_000),
    },
  );
  stage = "inference";
  const targets = input.stage === "canary" ? input.deploymentIds : [undefined];
  for (const deploymentId of targets) {
    const result = await verifyModel({
      modelId: input.modelId,
      protocol: input.protocol,
      deploymentId,
      apiKey: issued.secret,
      baseURL: "https://api.gradiated.com",
      signal,
    });
    console.log(
      JSON.stringify({
        event: "model_sdk_verification_passed",
        ...result,
      }),
    );
  }
} catch (error) {
  console.error(
    JSON.stringify({
      event: "model_sdk_verification_failed",
      modelId: input.modelId,
      deploymentIds: input.deploymentIds,
      stage,
      status:
        typeof (error as { status?: unknown })?.status === "number"
          ? (error as { status: number }).status
          : undefined,
      error_type: error instanceof Error ? error.name : "unknown",
    }),
  );
  process.exitCode = 1;
} finally {
  try {
    if (issued)
      await keys.revokeApiKey(
        environment.MODEL_VERIFICATION_USER_ID,
        environment.MODEL_VERIFICATION_WORKSPACE_ID,
        issued.apiKey.id,
      );
  } catch {
    console.error(
      JSON.stringify({ event: "model_sdk_verification_key_revocation_failed" }),
    );
    process.exitCode = 1;
  } finally {
    await pool.end();
    clearTimeout(timeout);
  }
}
