import { createHash } from "node:crypto";

import type { Case } from "./case.js";

/** Marks every deployment of the case LoRA-capable and reports it healthy. */
export const enable = async (
  instance: Case,
  loraBaseRevision?: string,
): Promise<string> => {
  const release = {
    ...instance.release,
    lora_enabled: true,
    ...(loraBaseRevision ? { lora_base_model_revision: loraBaseRevision } : {}),
  };
  for (const deployment of instance.deployments) deployment.release = release;
  await instance.publish();
  const digest = `sha256:${createHash("sha256").update(JSON.stringify(release)).digest("hex")}`;
  await instance.redis.hSet(
    `deployment-status:{${digest}}`,
    Object.fromEntries(
      instance.deployments.map((deployment) => [
        deployment.id,
        JSON.stringify({
          schema_version: 1,
          deployment_id: deployment.id,
          runtime_revision: release.runtime_revision,
          received_at: new Date().toISOString(),
          healthy: true,
          accepting_requests: true,
          reason_code: null,
        }),
      ]),
    ),
  );
  return digest;
};

export const version = async (
  instance: Case,
  task = crypto.randomUUID(),
  baseRevision = instance.release.model_revision,
) => {
  const id = crypto.randomUUID();
  const run = crypto.randomUUID();
  const sha256 = "a".repeat(64);
  await instance.database.query(
    "insert into tasks (id, organization_id, workspace_id, name, base_model_id) values ($1, $2, $3, $4, $5) on conflict (id) do nothing",
    [
      task,
      instance.organization,
      instance.workspace,
      `task-${task}`,
      instance.model,
    ],
  );
  await instance.database.query(
    "insert into training_runs (id, task_id, trigger, stage, base_model_id, input_cutoff, finished_at) values ($1, $2, 'manual', 'succeeded', $3, now(), now())",
    [run, task, instance.model],
  );
  await instance.database.query(
    "insert into task_versions (id, workspace_id, task_id, training_run_id, name, base_model_id, adapter, status) values ($1, $2, $3, $4, $5, $6, $7, 'available')",
    [
      id,
      instance.workspace,
      task,
      run,
      `version-${id}`,
      instance.model,
      JSON.stringify({
        format: "peft_lora",
        artifact_uri: `s3://synthetic/runs/${run}/adapter.tar.gz`,
        sha256,
        size_bytes: 10,
        rank: 2,
        base_model_revision: baseRevision,
      }),
    ],
  );
  return {
    id,
    task,
    sha256,
    name: `version-${id}`,
    selector: `${instance.organizationSlug}/task-${task}/version-${id}`,
    runtimeName: `${instance.workspace}/${id}`,
  };
};

export const production = (
  instance: Case,
  selected: Awaited<ReturnType<typeof version>>,
) =>
  instance.database.query(
    "update tasks set production_version_id = $2 where id = $1",
    [selected.task, selected.id],
  );
