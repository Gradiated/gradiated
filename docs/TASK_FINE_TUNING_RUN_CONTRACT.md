# Fine-tuning: dataset, run and trainer contract

The separate TypeScript `temporal-worker` application hosts Temporal workflows. PostgreSQL owns customer-visible run state and events; S3 owns trace content and large artifacts. The console remains behind the `training` feature flag. The `qwen-sft` executor trains pinned Qwen3-0.6B with LoRA on a fixed RunPod H100 pool. The mock remains available for local orchestration tests and existing histories. Published adapters remain unavailable for promotion until inference serving is qualified.

## Admission and identity

A task has one workflow at a time, with ID `training-<task_id>`. The workflow type is `trainingRunV1` on task queue `training-v1`. Workflow IDs contain only internal UUIDs. Its Temporal execution UUID is also the PostgreSQL `training_runs.id`, so cancellation addresses the exact execution rather than whichever run currently occupies the task's workflow ID.

The Train button calls `POST /api/v1/workspaces/{workspace_id}/training-runs` with `{ "task_id": "..." }` in its JSON body. Owners and admins can start a run after choosing a base and comparison model. The endpoint counts distinct trace IDs (falling back to generation IDs), requires at least 100 new traces, and returns 202 with the accepted execution ID. Below-threshold requests return 422 with the required and observed counts. An active run returns 409, “Already training.” Temporal is the final concurrency authority, including the interval before the API persists the accepted PostgreSQL run row.

Each task stores `training_schedule` as a nullable five-field cron expression in PostgreSQL, interpreted in UTC. For example, `0 3 * * MON` runs weekly and `0 3 1 * *` runs monthly; null disables automatic training. Expressions support lists, ranges, steps and month/day names. When both day-of-month and day-of-week are restricted, both must match, following Temporal calendar semantics. New tasks receive a weekly cron with random minute, hour and weekday persisted at insertion, including tasks created by the collector. `PATCH /api/v1/workspaces/{workspace_id}/tasks/{task}` replaces the expression. Task creation does not call Temporal.

Task PATCH requests save the configuration in PostgreSQL and then directly create
or update `training-task-<task_id>` in Temporal. Clearing the cron deletes the
schedule. A Temporal failure returns 503 and does not roll back the saved task configuration;
the console retains the draft and shows an explicit retry error instead of confirming
the schedule is active. Users can resubmit the same settings to retry. There is no periodic sweep or pending-sync
queue. Workspace capture, archival and organization changes do not update
schedules: the scheduled workflow checks current eligibility before starting
training and skips missing, disabled or ineligible tasks.

Each per-task schedule starts `trainingTaskV1` with only the task UUID in its encrypted arguments. It rechecks current eligibility and requires 500 new trace arrivals before starting the normal training workflow. A concurrent manual run wins the same task workflow ID and the scheduled attempt skips. Schedule overlap is skipped, with at most one hour of catch-up after outages. The wrapper waits for training completion to prevent overlapping scheduled executions. Manual training may use retained traces while capture or automatic scheduling is off. These schedules spread admission times; they do not allocate GPUs or guarantee balanced pool utilization.

Admission reads manifests newest date and hour first and stops as soon as the threshold is met. It deduplicates retries and generations belonging to the same trace. It uses the manifest's S3 `LastModified` arrival time within the new run's frozen cutoff and after the last **successful** run's `input_cutoff`, respecting source retention. Late-arriving captures therefore remain eligible even when their request timestamps precede the cutoff. Failed and cancelled runs do not advance that boundary. There is no counter, rollup table, cache or ClickHouse trace query. Counting captured traces does not itself authorize training on provider output; the dataset builder separately enforces source eligibility.

## Persistence and stages

The lifecycle is:

`queued → building_dataset → awaiting_capacity → training → verifying → publishing → evaluating → succeeded`

Failures end at `failed`. Cancellation goes through `cancelling` and finishes at `cancelled` after cleanup. A stage change and its `stage_entered` event commit in one PostgreSQL transaction under a run-row lock. Retrying that write does not duplicate the transition. Terminal runs never reopen, and delayed earlier transitions cannot regress a run. The database also enforces one unfinished run per task.

Each step is a separate Temporal activity. A step failure retries only that activity. Run initialization and terminal recording are idempotent. Cleanup runs in a non-cancellable scope. For the real trainer, shutdown requests are bounded and best effort; lease expiry handles unreachable hosts, and an unavailable Nomad API does not prevent terminal recording.

The worker writes small summaries to `training_runs`, structured events to `training_run_events`, and version metadata to `task_versions`. Events are paginated by monotonically increasing ID. Datasets, complete checkpoints, adapters and detailed evaluation results belong under `runs/<run_id>/` in S3, referenced by key and SHA-256, never in workflow arguments or event bodies. No credentials, signed URLs, prompts or generated customer text belong in run logs.

Versions are named `<task>-YYYYMMDD[-n]` with a workspace-unique name and one version per run. Publication never changes `tasks.production_version_id`. Promotion uses the existing PUT production endpoint and is always manual. A published version remains visible while evaluation is pending. The workspace `default_judge_model` is copied into each task's `judge_model_id` when capture first seeds it. Task settings can override that saved judge. Later workspace default changes affect only new tasks. Admission freezes the task judge into the workflow input together with its base and comparison models.

## Cancellation and retries

An accepted manual start persists its queued PostgreSQL run before returning 202, so it is visible and cancellable before a worker picks it up. The workflow also initializes the run idempotently.

`DELETE /api/v1/workspaces/{workspace_id}/training-runs/{run_id}` requests Temporal cancellation after workspace authorization. Activity cancellation waits for acknowledgement; long-running activities heartbeat while polling their external operation. The real workflow stops reservation renewal and requests host shutdown before recording `cancelled`; it does not require a host acknowledgement. A retry of cancellation cannot target a subsequent run.

Activity attempts have bounded execution time and backoff. Normal steps currently allow three attempts (the initial attempt and at most two retries), a ten-minute start-to-close timeout and a 24-hour schedule-to-close timeout; trainer-specific limits will replace the mock's limits. State recording retries through a database outage. The mock executor retries resource cleanup. Real training requests shutdown once with a bounded timeout and relies on its host lease if the request fails.

For the real trainer, a GPU-step retry resumes from the latest verified checkpoint. Before replacing an active host, stop renewing its reservation and request Nomad shutdown without waiting for client acknowledgement. Wait four minutes before replacement to cover an in-flight renewal, the three-minute lease and the ten-second process exit grace. Unready allocations have received no training commands and do not require this wait. Each attempt writes to its own artifact paths; only the workflow activity accepts results and advances the checkpoint pointer. A checkpoint must include optimizer and step state as well as adapter weights; upload and verify its immutable manifest before reporting it as resumable.

## Host execution boundary

An allocate-host activity starts a long-running Nomad job that retains the base model in memory. The workflow decides whether each step can reuse it or needs a replacement. Step activities send work through the per-host Nomad proxy and heartbeat while polling. Release runs on success, failure and cancellation, including partial allocation failures.

Nomad does not restart or reschedule training jobs. The workflow owns replacement. GPU hosts never connect to Temporal and never receive Temporal credentials. They receive only the credentials needed for their admitted data and artifact operations. Existing GPU reservations must not be stopped or reconfigured to create this pool.

The mock exercises the orchestration boundary without allocating GPUs. Its zero-count dataset and unavailable version are synthetic. It does not claim a trained adapter, a measured judge result or production availability. Enable it explicitly with `TRAINING_EXECUTOR=mock`; production does not enable it by default.

## Temporal configuration and deployment compatibility

Every client and worker uses `@gradiated/temporal`'s AES-256-GCM data converter, including encoded common failure attributes. Production requires `TEMPORAL_ADDRESS`, `TEMPORAL_NAMESPACE`, `TEMPORAL_API_KEY`, `TEMPORAL_PAYLOAD_KEY_ID` and `TEMPORAL_PAYLOAD_KEYS`. The API and `temporal-worker` consume the Terraform-owned `temporal` ExternalSecret. Never inspect production secret values. Keep old decryption keys while histories using them remain retained.

Local development defaults to `localhost:7233`, namespace `default`, no API key and the fixed `local-dev` payload key. Run the Temporal service in `product/docker-compose.yml`. Customer names, model names, prompts and artifact references must not appear in workflow IDs, type names, task queues, schedule IDs, memo or search attributes: those metadata fields are not encrypted.

`temporal-worker` replicas share one task queue and ensure the same schedule idempotently. Kubernetes restarts the dedicated process on failure; it has no dependency on the ingestion/settlement worker, Valkey or ClickHouse. Shutdown drains activity execution within the pod grace period. Its PodMonitor scrapes Temporal SDK metrics on port 9464, including activity schedule-to-start latency, execution latency and failures. The Gradiated / Temporal worker Grafana dashboard charts those SDK metrics for `training-v1`; queue wait measures Temporal dispatch, not GPU capacity admission. HTTP readiness is served separately on port 3005.

The production deployment starts at zero replicas until a production executor is supplied. Enable the executor and replicas together; the mock is opt-in for local tests. It has a separate ServiceAccount and Pod Identity role with trace reads, run artifact reads/writes and Nomad client certificate signing. It currently uses the existing worker database login through the database-only `worker` Secret; Temporal credentials are injected only into the API and `temporal-worker`.

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
in the run manifest, outside the portable dataset manifest.

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

## Host execution boundary

An allocate-host activity starts a long-running Nomad job that retains the base model in memory. The workflow decides whether each step can reuse it or needs a replacement. Step activities send work through the per-host Nomad proxy and heartbeat while polling. Release runs on success, failure and cancellation, including partial allocation failures.

Nomad does not restart or reschedule training jobs. The workflow owns replacement. GPU hosts never connect to Temporal and never receive Temporal credentials. They receive only the credentials needed for their admitted data and artifact operations. Existing GPU reservations must not be stopped or reconfigured to create this pool.

The first pool has four on-demand H100s kept running continuously, with no spending cap, as explicitly authorized. Releasing a run stops its Nomad allocation, not its RunPod pod. Placement uses the exact enrolled Nomad node IDs for the configured training pod IDs, the runtime base ID, and the GPU model constraint. It cannot consume unrelated fleet capacity. Future B300 capacity needs its own Terraform change and scope-matched validation.

The mock exercises the orchestration boundary without allocating GPUs. Its zero-count dataset and unavailable version are synthetic. It does not claim a trained adapter, a measured judge result or production availability. Enable it explicitly with `TRAINING_EXECUTOR=mock`; production does not enable it by default.

## Dataset, SFT and evaluation

The frozen recipe is `product/packages/contracts/src/training-recipe.json`: Qwen3-0.6B at a pinned Hugging Face revision, rank-two LoRA, fifty optimizer steps, gradient accumulation four and sequence length 2048. The base, comparison and task judge must all be this model for the initial executor; incompatible settings return a clear admission error. The infrastructure-independent Python library lives in `Gradiated/autotrain`, pinned as the `product/packages/autotrain` submodule. Its API accepts local dataset/checkpoint paths and an explicit recipe, reports progress/checkpoints through callbacks, and returns a local adapter archive. It knows nothing about Temporal, Nomad, RunPod, HTTP, or S3. The private runtime adapter in `product/inference/training` handles signed transfers and command dispatch; its container build installs the pinned package into the trainer bundle. The package repository remains private until it is ready to open source; infrastructure stays in this repository.

Dataset construction reads retained traces up to the frozen cutoff. It accepts trainable hosted/imported text conversations ending in a user message and complete, successful assistant text; relay outputs, tool calls and incomplete captures are excluded. Exact examples are deduplicated. Session groups and identical prompts are joined before deterministic 80/10/10 train/validation/test assignment, preventing cross-split prompt leakage. Collection is bounded at 10,000 examples or 64 MiB of example content. Training needs ten examples and nonempty validation and test groups. Oversized token sequences are excluded from training rather than truncated.

Dataset rows follow TRL's conversational prompt/completion format: `prompt` is a list of input messages and `completion` is a list containing the assistant response. `id` and `group` are additional provenance columns used for deduplication and grouped evaluation. The current recipe supports text-only conversations and exactly one assistant completion; it does not claim tool or multimodal support.

New datasets live under `runs/<run-id>/dataset/v1/`. `dataset-manifest.json` uses the shared `SftDatasetManifestSchema`: schema version, row format, JSONL encoding, builder version and split configuration, and per-split example counts and file URIs, SHA-256 digests and byte lengths. `train.jsonl`, `validation.jsonl` and `test.jsonl` are the complete splits. `evaluation.jsonl` is a separately described sample of up to 64 test examples, ordered by example ID. Trace timestamps and the input cutoff are optional provenance, not a requirement of the portable format. The manifest contains stable object URIs, never expiring download grants or credentials. JSONL rows can be loaded using Hugging Face Datasets; sharded Parquet can be added as another encoding without changing the logical rows.

`RunDatasetSummary` is the UI projection: eligible examples, duplicates removed, split counts, optional trace dates and the actual evaluation sample count. It does not duplicate file hashes. Historical summaries are migrated without guessing the number actually evaluated.

A separate `runs/<run-id>/run-manifest.json` freezes the recipe, runtime bundle hash, host configuration and artifact references for retries across deployments. The portable manifest has no Nomad or service configuration. The model revision also pins its tokenizer and chat template; the recipe uses `enable_thinking=False`, completion-only loss, and excludes overlength examples. Runtime code is pinned by its bundle hash. The trainer masks prompt tokens, measures loss and throughput, and uploads optimizer/adapter/RNG checkpoints every ten steps. Validation loss uses up to 64 fitting examples. The worker verifies uploaded bytes and hashes before advancing the checkpoint pointer. CPU tests compare uninterrupted and resumed adapter weights exactly; this does not establish H100 numerical equivalence or quality.

The same allocation verifies finite adapter logits and evaluates up to 64 held-out examples. It generates adapted and base answers in reproducibly randomized order, then uses the base model as judge once per pair with the same randomized answer presentation. Invalid votes are unresolved. The summary records `judging_method`; older frozen runtimes retain `both_orders`, where inconsistent or invalid votes are unresolved. Results are weighted equally by independent session/shared-prompt group and stored in S3; PostgreSQL stores measured summaries. This small judge is an infrastructure validation tool, not a production-quality benchmark. Cost is null because it is not measured. Training artifacts use the model-artifacts bucket under `runs/<run_id>/`, separate from trace retention.

TypeScript uses the shared `ObjectStorage` class for S3 reads, writes, metadata and signed URLs. The training artifact and adapter-download wrappers receive it through dependency injection and retain run scoping and artifact integrity checks. Reads enforce their byte limit while streaming even when object length metadata is missing or inaccurate.

The allocation receives scoped, expiring S3 URLs over the authenticated host proxy. A short workflow activity renews its allocation-bound lease every 30 seconds, independently of operation polling and across publishing/other intervening steps. Each compute step validates and renews the current allocation before use. The host rejects wrong-allocation and expired renewals; polling cannot keep abandoned compute alive. Three minutes without renewal stops compute, followed by a ten-second exit grace; Nomad releases the GPU when it observes task death. Initial model loading has a bounded 15-minute bootstrap grace, and the host has a 24-hour hard deadline. Manual and scheduled training workflows have a 24-hour execution timeout; each capacity acquisition attempt can wait up to 12 hours, separately from two-hour GPU activity limits. Normal completion/cancellation stops renewal before explicit cleanup. Termination or workflow timeout may bypass cleanup, so the host watchdog remains the independent fallback. The allocation holds no Temporal credentials. Shutdown is requested through Nomad but never waits for a host death acknowledgement. Replacement of an active host waits four minutes after renewals stop; normal final cleanup requests shutdown and records the outcome without waiting for lease expiry. A frozen machine may outlive the lease until it resumes; the watchdog is a local safeguard, not proof of process death. Training uses only the existing, explicitly enrolled fixed pool; spot provisioning is outside this contract.

The current training workflow type is `trainingRunV2`, on the shared `training-v1` task queue. Both manual starts and per-task cron schedules target it when the API executor is `qwen-sft`; schedules pass a task ID and manual starts pass the admitted input. Scheduled admission checks current eligibility and the frozen Qwen recipe as the first activity. PostgreSQL atomically allows one unfinished run per task; a scheduled run that loses admission skips training. No child workflow is created. Migration 0010 stores the actual workflow ID so cancellation targets the exact scheduled or manual execution; older records retain the deterministic per-task fallback. Task updates retain the same direct, best-effort schedule update behavior. All queue consumers must register training executor handlers before enabling SFT API admission; existing mock histories retain their handlers. In a Qwen deployment, legacy `trainingTaskV1` schedules skip admission instead of launching mock training. Re-save existing task schedules to retarget them to `trainingRunV2`. Missing or archived scheduled targets are skipped.

Hard workflow timeout and termination bypass workflow cleanup. When training pages read an unfinished run, or admission encounters one, the service describes its exact stored Temporal execution and records any terminal outcome through the normal run store. Concurrent reconciliation emits the terminal events once and releases the unfinished-run uniqueness constraint. Scheduled admission uses the same reconciliation. A Temporal lookup outage preserves the active run and does not break read-only pages; admission remains blocked until execution status can be confirmed. No periodic sweep is required.

Admission counts distinct retained manifest traces as a preflight. Dataset construction is authoritative for canonical conversation validity, deduplication and usable split sizes; insufficient usable data fails during `building_dataset`, before GPU allocation. The preflight does not reread every captured conversation.

Dataset activities allow three total attempts with a 24-hour queue/retry budget. GPU activities have one Temporal attempt; the workflow permits at most three host attempts, requesting shutdown and waiting for the active reservation expiry window before replacement. Checkpoints carry adapter, optimizer and RNG state. Recording retains durable retries; real trainer shutdown requests are bounded and best effort.

The Temporal worker exposes database-derived training metrics on its health port at `/metrics`, separately from the SDK metrics port. Its PodMonitor scrapes both. Grafana shows active runs, oldest capacity/queue waits, stage durations, completion outcomes and observation freshness. Metrics failures do not block health checks.

The persisted catalog includes the Qwen recipe base with inference status `unavailable`. The shared model catalog marks it for training, so task configuration accepts it without advertising a hosted inference deployment. Its required pricing fields are structural placeholders while unavailable, not a serving price quote. The initial executor still requires the Qwen model as base, comparison and task judge.
