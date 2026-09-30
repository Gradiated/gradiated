# Fine-tuning: dataset, run and trainer contract

The separate TypeScript `temporal-worker` application hosts Temporal workflows. PostgreSQL owns customer-visible run state and events; S3 owns trace content and large artifacts. The console remains behind the `training` feature flag. The current executor is an explicitly enabled mock; it creates unavailable versions, never usable adapters or measured evaluation results. The next executor is basic SFT on a small Qwen model, using a RunPod H100 pool managed through Terraform.

## Admission and identity

A task has one workflow at a time, with ID `training-<task_id>`. The workflow type is `trainingRunV1` on task queue `training-v1`. Workflow IDs contain only internal UUIDs. Its Temporal execution UUID is also the PostgreSQL `training_runs.id`, so cancellation addresses the exact execution rather than whichever run currently occupies the task's workflow ID.

The Train button calls `POST /api/v1/workspaces/{workspace_id}/training-runs` with `{ "task_id": "..." }` in its JSON body. Owners and admins can start a run after choosing a base and comparison model. The endpoint counts distinct trace IDs (falling back to generation IDs), requires at least 100 new traces, and returns 202 with the accepted execution ID. Below-threshold requests return 422 with the required and observed counts. An active run returns 409, “Already training.” Temporal is the final concurrency authority, including the interval before a worker creates the PostgreSQL run row.

Each task stores `training_schedule` as a nullable five-field cron expression in PostgreSQL, interpreted in UTC. For example, `0 3 * * MON` runs weekly and `0 3 1 * *` runs monthly; null disables automatic training. Expressions support lists, ranges, steps and month/day names. When both day-of-month and day-of-week are restricted, both must match, following Temporal calendar semantics. New tasks receive a weekly cron with random minute, hour and weekday persisted at insertion, including tasks created by the collector. `PATCH /api/v1/workspaces/{workspace_id}/tasks/{task}` replaces the expression. Task creation does not call Temporal.

Task PATCH requests save the configuration in PostgreSQL and then directly create
or update `training-task-<task_id>` in Temporal. Clearing the cron deletes the
schedule. A Temporal failure is logged and does not roll back the task update;
users can resubmit settings to retry. There is no periodic sweep or pending-sync
queue. Workspace capture, archival and organization changes do not update
schedules: the scheduled workflow checks current eligibility before starting
training and skips missing, disabled or ineligible tasks.

Each per-task schedule starts `trainingTaskV1` with only the task UUID in its encrypted arguments. It rechecks current eligibility and requires 500 new trace arrivals before starting the normal training workflow. A concurrent manual run wins the same task workflow ID and the scheduled attempt skips. Schedule overlap is skipped, with at most one hour of catch-up after outages. The wrapper waits for training completion to prevent overlapping scheduled executions. Manual training may use retained traces while capture or automatic scheduling is off. These schedules spread admission times; they do not allocate GPUs or guarantee balanced pool utilization.

Admission reads manifests newest date and hour first and stops as soon as the threshold is met. It deduplicates retries and generations belonging to the same trace. It uses the manifest's S3 `LastModified` arrival time within the new run's frozen cutoff and after the last **successful** run's `input_cutoff`, respecting source retention. Late-arriving captures therefore remain eligible even when their request timestamps precede the cutoff. Failed and cancelled runs do not advance that boundary. There is no counter, rollup table, cache or ClickHouse trace query. Counting captured traces does not itself authorize training on provider output; the dataset builder separately enforces source eligibility.

## Persistence and stages

The lifecycle is:

`queued → building_dataset → awaiting_capacity → training → verifying → publishing → evaluating → succeeded`

Failures end at `failed`. Cancellation goes through `cancelling` and finishes at `cancelled` after cleanup. A stage change and its `stage_entered` event commit in one PostgreSQL transaction under a run-row lock. Retrying that write does not duplicate the transition. Terminal runs never reopen, and delayed earlier transitions cannot regress a run. The database also enforces one unfinished run per task.

Each step is a separate Temporal activity. A step failure retries only that activity. Run initialization and terminal recording are idempotent. Cleanup runs in a non-cancellable scope and must finish before the terminal write; a cleanup outage leaves the run open for retry rather than claiming resources were released.

The worker writes small summaries to `training_runs`, structured events to `training_run_events`, and version metadata to `task_versions`. Events are paginated by monotonically increasing ID. Datasets, complete checkpoints, adapters and detailed evaluation results belong under `runs/<run_id>/` in S3, referenced by key and SHA-256, never in workflow arguments or event bodies. No credentials, signed URLs, prompts or generated customer text belong in run logs.

Versions are named `<task>-YYYYMMDD[-n]` with a workspace-unique name and one version per run. Publication never changes `tasks.production_version_id`. Promotion uses the existing PUT production endpoint and is always manual. A published version remains visible while evaluation is pending. The evaluation judge is a workspace setting frozen into the workflow input together with the task's base and comparison models.

## Cancellation and retries

An accepted manual start persists its queued PostgreSQL run before returning 202, so it is visible and cancellable before a worker picks it up. The workflow also initializes the run idempotently.

`DELETE /api/v1/workspaces/{workspace_id}/training-runs/{run_id}` requests Temporal cancellation after workspace authorization. Activity cancellation waits for acknowledgement; long-running activities heartbeat while polling their external operation. The workflow releases the run's host before recording `cancelled`. A retry of cancellation cannot target a subsequent run.

Activity attempts have bounded execution time and backoff. Normal steps currently allow three attempts (the initial attempt and at most two retries), a ten-minute start-to-close timeout and a 24-hour schedule-to-close timeout; trainer-specific limits will replace the mock's limits. State recording retries through a database outage. Resource cleanup retries until it can establish that the resource is released.

For the real trainer, a GPU-step retry resumes from the latest verified checkpoint. Before starting another attempt, stop the previous Nomad job and confirm its allocation is dead. Loss of contact is not proof of death. Never overlap replacement compute with an uncertain previous attempt. A checkpoint must include optimizer and step state as well as adapter weights; upload and verify its immutable manifest before reporting it as resumable.

## Host execution boundary

An allocate-host activity starts a long-running Nomad job that retains the base model in memory. The workflow decides whether each step can reuse it or needs a replacement. Step activities send work through the per-host Nomad proxy and heartbeat while polling. Release runs on success, failure and cancellation, including partial allocation failures.

Nomad does not restart or reschedule training jobs. The workflow owns replacement. GPU hosts never connect to Temporal and never receive Temporal credentials. They receive only the credentials needed for their admitted data and artifact operations. Existing GPU reservations must not be stopped or reconfigured to create this pool.

The mock exercises the orchestration boundary without allocating GPUs. Its zero-count dataset and unavailable version are synthetic. It does not claim a trained adapter, a measured judge result or production availability. Enable it explicitly with `TRAINING_EXECUTOR=mock`; production does not enable it by default.

## Temporal configuration and deployment compatibility

Every client and worker uses `@gradiated/temporal`'s AES-256-GCM data converter, including encoded common failure attributes. Production requires `TEMPORAL_ADDRESS`, `TEMPORAL_NAMESPACE`, `TEMPORAL_API_KEY`, `TEMPORAL_PAYLOAD_KEY_ID` and `TEMPORAL_PAYLOAD_KEYS`. The API and `temporal-worker` consume the Terraform-owned `temporal` ExternalSecret. Never inspect production secret values. Keep old decryption keys while histories using them remain retained.

Local development defaults to `localhost:7233`, namespace `default`, no API key and the fixed `local-dev` payload key. Run the Temporal service in `product/docker-compose.yml`. Customer names, model names, prompts and artifact references must not appear in workflow IDs, type names, task queues, schedule IDs, memo or search attributes: those metadata fields are not encrypted.

`temporal-worker` replicas share one task queue and ensure the same schedule idempotently. Kubernetes restarts the dedicated process on failure; it has no dependency on the ingestion/settlement worker, Valkey or ClickHouse. Shutdown drains activity execution within the pod grace period. Its PodMonitor scrapes Temporal SDK metrics on port 9464, including activity schedule-to-start latency, execution latency and failures. The Gradiated / Temporal worker Grafana dashboard charts those SDK metrics for `training-v1`; queue wait measures Temporal dispatch, not GPU capacity admission. HTTP readiness is served separately on port 3005.

The production deployment starts at zero replicas until a production executor is supplied. Enable the executor and replicas together; the mock is opt-in for local tests. It has a separate ServiceAccount and read-only S3/KMS Pod Identity role. It currently uses the existing worker database login through the database-only `worker` Secret; Temporal credentials are injected only into the API and `temporal-worker`.

`trainingRunV1` is a replay compatibility contract, not a label to rename on every deploy. Rolling deployments use compatible workflow code. Changes to recorded command order require Temporal `patched` branches retaining the old behavior until all affected histories have finished and aged out; use a new workflow type for a deliberately incompatible protocol and retain the old implementation and activity handlers while old executions remain. Do not pin workflows to a build whose workers will be removed by an ordinary Kubernetes rollout.

The worker tests replay a committed, synthetic encrypted v1 history and newly generated histories with activity retries. Do not regenerate the frozen fixture merely to make an incompatible change pass. Tests also use Temporal's time-skipping environment to verify cancellation and retry boundaries, and a real local Temporal server to verify Schedule behavior. PostgreSQL integration tests cover admission, successful cutoffs, transactional stage writes and authorization.

## Shared model catalog

`product/packages/contracts/src/model-catalog.ts` owns model IDs and their supported
uses. Judge validation, workspace defaults, database constraints and console
options derive from that catalog. Update the catalog and regenerate the database
migration and API clients when changing the allowed set. Eligibility as a judge
does not imply support by every training executor.

## Portable dataset contract

`SftExampleSchema` uses conversational `prompt` and `completion` message lists,
with optional example and group IDs. The initial contract supports text messages
and one assistant completion. `SftDatasetManifestSchema` describes versioned JSONL
artifacts for train, validation and test, with file URIs, SHA-256 hashes, byte sizes
and example counts. A sampled evaluation dataset is recorded separately from the
full test split. Builder version and split configuration describe preparation;
trace timestamps are optional provenance. Runtime and host configuration belong
in the execution record, outside the portable dataset manifest.

`RunDatasetSummary` is the UI projection: eligible examples, duplicates removed,
train/validation/test counts, optional trace dates and optional evaluation sample
count. The summary does not duplicate artifact checksums.

## Training measurements

`trainer_progress` requires only `step`: completed optimizer updates, cumulative
across checkpoint resumes. `total_steps`, `train_loss`, `tokens_per_second` and
`eta_seconds` are optional typed fields used by the console. Missing measurements
are omitted, not fabricated as zero. Loss can be signed for methods whose
objective permits it; the recipe defines the objective and averaging interval.
For SFT, it is cross-entropy over supervised completion tokens. Throughput counts
non-padding input tokens across all training devices over the logging interval.
ETA is an estimate, not a deadline.

The optional `metrics` map preserves other finite numeric measurements without
an enumerated name list (up to 64 entries, names up to 128 characters). Recommended
names include `learning_rate`, `grad_norm` (before clipping), `epoch`,
`input_tokens_seen` and `supervised_tokens_seen`. Other methods may report reward,
entropy or individual loss components. Metric definitions belong to the recipe;
consumers must not compare unlike objectives solely because the names match.

`trainer_observation` records trainer logs with an arbitrary `name`, a readable
`message`, and optional `level`, `step`, numeric `metrics`, and structured
`details`. Validation uses an observation such as `validation_completed` with
`metrics.validation_loss`; other method-specific measurements need no new event
type. Observations do not replace the latest typed progress sample. The event
envelope retains timestamp, service and attempt. The UI renders unfamiliar names
and details generically, keeping observations with training. Chart consumers can
plot metrics against step. Hardware utilization remains infrastructure telemetry.

## Workflow events and trainer observations

Lifecycle events such as `stage_entered`, `cancel_requested`, `run_finished`,
`artifact_verified`, `published` and job status remain typed. `trainer_checkpoint`
also stays typed because recovery consumes its step, object key, SHA-256 and byte
size. The worker must verify the artifact before accepting it for recovery.
`trainer_progress` retains the small optional display contract above.

Startup, internal trainer phases, validation, upload diagnostics and trainer
completion/failure messages use `trainer_observation`. Its name and details are
informational: an observation named `finished`, `failed` or `stage_entered` must
never drive a workflow transition, publish an artifact or select a checkpoint.
Those decisions use typed control events and validated operation results. The
worker must accept only the explicitly allowed trainer event types; an extensible
observation vocabulary does not authorize the trainer to emit lifecycle events.

Run listing uses `GET /api/v1/workspaces/{workspace_id}/training-runs` with an
optional `task_id` UUID filter. Without the filter it lists all runs in the
workspace; an unknown or foreign task ID returns an empty list. Task responses
include their stable `id` for filtering. Other task routes continue to use names.

References: [Temporal workflow versioning](https://docs.temporal.io/develop/typescript/versioning), [TypeScript SDK](https://typescript.temporal.io/).
