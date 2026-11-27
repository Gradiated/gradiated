# Retiring the product training stack

- status: plan. Code is removed only after the publish, eval and model-upload changes it depends on are merged and running; until then this document is the whole change.
- related: [TRAINING_CLOUD_INTEGRATION.md](TRAINING_CLOUD_INTEGRATION.md) §10, [MODEL_UPLOADS_ON_ARTIFACTS.md](MODEL_UPLOADS_ON_ARTIFACTS.md), [virtual-kubelet README](../tools/virtual-kubelet/README.md)

grad (grad-server, its pull workers and the SDKs) replaces the product's own training. This plan removes the old stack once nothing depends on it.

## What goes

| Piece                                  | Where                                                                                                                                                                                                                                                                                                                        |
| -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Temporal training workflows and worker | `product/services/temporal-worker/` (the only Temporal user: `src/training/{run-workflow,workflows,activities,executor-activities,evaluation*,dataset,cleanup,metrics,worker}.ts`), `product/packages/temporal/`, the `temporal-worker` Deployment, its secrets and the Temporal Cloud namespace                             |
| Training engine in the API             | `product/services/api/src/training/engine.ts`, `product/packages/control/src/training/{engine,admission,schedules,run-store,dataset,recipe,traces,metrics,workload-benchmarks}.ts`, the run routes in `routes/training.ts` (`/training-runs*`, `startTrainingRun`, `cancelTrainingRun`) and their console pages              |
| Training Jobs on virtual-kubelet hosts | `product/services/temporal-worker/src/training/kubernetes-host.ts`, the `gpu-training` PriorityClass and training-Job handling in `tools/virtual-kubelet` and `product/services/gpu-fleet`, the `"kind": "training"` runtime in `product/inference/gpu/runtimes.json`, `product/inference/training/` (training bundle image) |
| Data                                   | `training_runs`, `training_run_events`, `tasks.training_schedule`, `tasks.comparison_model_id`/`judge_model_id` (old evaluation only), `task_versions.training_run_id`                                                                                                                                                       |
| Old upload path                        | per [MODEL_UPLOADS_ON_ARTIFACTS.md](MODEL_UPLOADS_ON_ARTIFACTS.md) step 4: `model-uploads` routes, `uploads.ts`, `upload-store.ts`, `model_uploads`, the product bucket's `runs/` and `cartridges/` prefixes                                                                                                                 |

`tasks`, `task_versions`, promote, rollback, production history, version files and report shares stay: they are the inference side.

## Preconditions

1. Publish from artifacts, the rank cap, eval-only versions and the gateway eval lane are merged and deployed (this stack's earlier PRs).
2. grad on Cloud is at M1 and the console's training pages use grad (P6).
3. `MODEL_UPLOADS_CLOSED=true` in production and the upload backfill has run: no `task_versions` row lacks `adapter.source`.
4. No `training_runs` row is unfinished (`finished_at IS NULL`).

## Order

Each step is one PR and deploys on its own; a later step never ships in the same deploy as an earlier one.

1. **Stop starting runs.** Feature flag `TRAINING_RUNS_DISABLED`: `POST /training-runs` and schedules answer `410 training_moved_to_grad`; the Temporal schedules are deleted by the worker's cleanup (`deleteRetiredTrainingSchedules`). In-flight runs finish or are cancelled.
2. **Export for audit.** Copy `training_runs` and `training_run_events` to `s3://<product bucket>/exports/training/<date>/` as gzipped JSONL, with a manifest of row counts and SHA-256s.
3. **Remove the Temporal worker.** Delete `services/temporal-worker`, `packages/temporal`, the engine in the API and control, the run routes and console pages. Infra removes the Deployment, ExternalSecrets and, once nothing connects for a week, the Temporal Cloud namespace.
4. **Remove training Jobs from the fleet.** Delete `kubernetes-host.ts`, the `gpu-training` PriorityClass, training-Job handling in virtual-kubelet and the gpu-fleet operator, the training runtime in `runtimes.json` and `product/inference/training`. The grad lease path (`grad` holder, §6 of the integration design) replaces it.
5. **Remove the old upload path** (MODEL_UPLOADS_ON_ARTIFACTS.md step 4).
6. **Drop the tables and columns.** One migration drops `training_runs`, `training_run_events`, `model_uploads`, `tasks.training_schedule`, `tasks.comparison_model_id`, `tasks.judge_model_id` and `task_versions.training_run_id` (and its unique and composite foreign keys). The gateway never reads them; check `postgres_reader.rs` again before merging.

## Checks per step

- `gradctl devex check`, the product's `pnpm check`, cargo tests for the gateway and gpu-fleet, and the virtual-kubelet tests.
- Step 3: `rg -n "@gradiated/temporal|temporal-worker|TrainingEngine" product` returns nothing.
- Step 4: no runtime with `"kind": "training"` remains, and `rg -n gpu-training` returns nothing outside history.
- Step 6: the migration runs against a production snapshot restore; `GET …/tasks`, promote, rollback and gateway private-adapter reads pass.

## Open questions

1. **Scheduled retraining** (`tasks.training_schedule`) has no grad equivalent and is dropped (user decision, 2026-11-27). Customers with a schedule get an email before step 1.
2. **Old evaluation results** (`/versions/{id}/evaluation`, judged comparisons) read `runs/<run>/evaluation/` in the product bucket. Keep them read-only until step 5, then drop them with `runs/`, or copy them into each Version's files first.
