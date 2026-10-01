# Fine-tuning from captured traces

The console, persistent task model and Temporal orchestration are implemented.
Execution currently uses opt-in mock activities. Real SFT on a small Qwen model
is the next increment, using a RunPod H100 pool and Nomad host allocations.
No production GPU pool has been provisioned for training.

The [run contract](TASK_FINE_TUNING_RUN_CONTRACT.md) defines the implemented
interfaces. [TRACES_PLAN.md](TRACES_PLAN.md) owns capture and S3 trace storage.
[ARCHITECTURE.md](ARCHITECTURE.md) owns service boundaries.

Published adapter downloads use `GET /api/v1/workspaces/{workspace_id}/tasks/{task}/versions/{version_id}/adapter`. The API checks workspace membership and version ownership, then returns an uncached, five-minute signed archive URL. Serving eligibility does not restrict downloads. The API needs `TRAINING_ARTIFACTS_BUCKET` and `s3:GetObject` / `s3:GetObjectVersion` on that bucket's `runs/*` prefix; production configuration and the API role policy declare both. The archive must belong to the version's training run and match its recorded size and SHA-256. Signed links pin the verified S3 object version. Archives without an S3 full-object SHA-256 are streamed through the API for hashing before signing. No standalone manifest is published by the current trainer, so the console offers the archive only.

## Implemented

The console's `training` feature flag exposes workspace-scoped tasks, model
settings, runs, paged events, versions and manual promotion through the generated
Management API client. The collector creates tasks idempotently at capture time;
task listing reads PostgreSQL directly. The workspace owns
its evaluation judge. The Data tab reads captured traces; no traffic chart,
request/token statistics or trace progress counter is maintained for training.

Manual training requires 100 distinct trace arrivals since the last successful
run's input cutoff. Each task has a PostgreSQL schedule setting and its own
Temporal Schedule, configured with a nullable UTC cron expression and defaulting
to a weekly cron with a persisted staggered minute, hour and weekday. Updating a
task saves its settings in PostgreSQL and then directly creates or updates its
Temporal Schedule. Clearing the cron deletes the schedule. Temporal failures are
logged and do not roll back the task update; resubmitting the task settings
retries synchronization. There is no periodic reconciliation or pending-update
queue. Scheduled executions recheck task, workspace and organization eligibility
before starting training and require 500 trainable arrivals per task.
It reads manifests newest hour first, stops at the threshold and uses manifest
modification times to include late uploads. There is no training counter or
ClickHouse dependency. Manual admission does not require capture to remain on.

The separate TypeScript `temporal-worker` application hosts one workflow per task, identified by the
internal task UUID. Temporal rejects concurrent starts. Every client and worker
uses encrypted payload and failure conversion. PostgreSQL stores run state and
ordered events; each stage transition and its event share a transaction. S3 owns
large artifacts. Workflow activities isolate retries by step. Cancellation waits
for active work to stop and releases the host before recording a terminal state.

The API starts and cancels runs, and the console displays admission failures.
Train and Cancel require an editor role. Promotion remains manual. Mock execution
is enabled only with `TRAINING_EXECUTOR=mock` and produces synthetic, unavailable
versions that cannot be promoted. It validates orchestration, not model quality.

Workflow changes must replay the committed v1 history. Compatible patches retain
old command behavior for existing runs; incompatible changes introduce a new
workflow type while keeping old handlers available until their executions finish.
Rolling deployments must not strand hours-long runs on a removed worker build.

## Next increment: Qwen SFT and GPU hosts

Use a small, explicitly pinned Qwen model and a pinned Python training package.
The private runtime bundle installs that package; TypeScript owns admission, dataset orchestration, run state,
Nomad operations and artifact validation. Start with basic supervised fine-tuning,
with separate training and held-out data. Provider outputs are not training
labels. Captured hosted outputs and explicitly permitted imported examples need
provenance checks before entering a training dataset.

An allocation activity starts a long-running Nomad job that loads the base model.
Step activities send work through the per-host Nomad proxy, heartbeat while
polling and reuse that allocation where possible. GPU hosts have no Temporal
credentials. Nomad restart and reschedule behavior must be disabled for these
jobs: the workflow owns replacement and cleanup.

Before retrying GPU work on another attempt, stop the prior job and confirm its
allocation is dead. Persist checkpoints under `runs/<run_id>/` and resume from the
last valid checkpoint. Publish an adapter only after validating its files and
hashes. Evaluate against the configured comparison model with the workspace
judge; store summaries in PostgreSQL and large evidence in S3. Promotion is still
an explicit user action after results are available.

RunPod capacity must be represented in Terraform and joined to the existing Nomad
fleet with a training-specific pool or constraint. GPU provisioning awaits the
approved spending cap, maximum concurrent GPU count and retention policy. Validate
one complete train, checkpoint resume, cancellation, cleanup and artifact load
before expanding the pool. Infrastructure applies follow the protected deployment
workflow; production secret values are never read by agents.

## Verification

The control package tests admission, late arrivals, transactional events,
idempotent publication and cancellation against real PostgreSQL. Temporal tests
use the time-skipping environment for step retries, cancellation and scheduled admission
behavior, replay a frozen history, and exercise schedule creation and a complete
`temporal-worker` lifecycle with encrypted clients and PostgreSQL. Console browser tests
cover persistence, pagination, collector registration and outage recovery, admission errors and cancel.

The real trainer increment adds dataset provenance and split tests, trainer event
and artifact validation, Nomad host lifecycle tests, checkpoint recovery and a
bounded H100 smoke run. Synthetic orchestration results do not establish training
correctness or quality.

## Qwen executor

The `qwen-sft` workflow is orchestrated by `product/services/temporal-worker`.
Training runs as a separate Python process on exact enrolled H100 nodes, using
pinned Qwen3-0.6B, rank-two LoRA and fifty optimizer steps. The training library
lives in the private [Gradiated/autotrain](https://github.com/Gradiated/autotrain)
repository, pinned as the `product/packages/autotrain` submodule. It accepts local
files and an explicit recipe; progress and checkpoint callbacks connect it to the
private runtime adapter. Docker packaging, HTTP, signed S3 transfers, Nomad and
host lifecycle remain in this repository. Only the Python library is intended
for future open sourcing.

The worker publishes conversational prompt/completion JSONL train/validation/test
artifacts and a portable dataset manifest, then coordinates training, verification
and infrastructure evaluation. Host replacement requires confirmed process death
and resumes verified optimizer checkpoints. See the run contract and
`infra/environments/prod/runpod/training/README.md` for deployment order and manual
pool assignment. Live H100 training and rolling-deployment recovery still require
production qualification.
