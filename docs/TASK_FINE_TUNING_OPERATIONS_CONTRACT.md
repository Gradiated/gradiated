# Fine-tuning: control, storage and operations

Status: specified design; deployment evidence and backup configuration still required. Owns `OPS-01` to `OPS-06`.

## Stores

| Store | Owns | Never used for |
| --- | --- | --- |
| PostgreSQL | Policy, task configuration, task and version identities, run config and lifecycle state, model lifecycle, production pointers, host enrollment | Bodies, high-rate telemetry |
| ClickHouse | Traces, generations, structured training execution history, checkpoint references, evaluation results, best-effort action audit events, and summaries; execution history supports recovery decisions | Required synchronous gateway state |
| S3 | Immutable content named by accepted manifests | Anything mutable |
| Kubernetes | Actual workload placement, allocation lifecycle and serving-process recovery | Product authorisation, training retry decisions or adapter readiness |
| Valkey | Gateway projections, admission counters, leases, one `generation-events` stream | Source of truth for anything |

Valkey is the gateway's only required synchronous internal state store. ClickHouse capture writes must not block inference. Training, evaluation and control-plane operations may depend on ClickHouse or PostgreSQL as needed. There is no requirement for training recovery to remain available during a ClickHouse outage.

Logical records live in the existing control modular monolith; schemas and constraints are described before implementation.

## Decisions in this contract

| Decision | Reason | Rejected |
| --- | --- | --- |
| ClickHouse owns training execution history used for logs and recovery; PostgreSQL defines runs and stores product control records; Kubernetes owns allocation state | Store each fact where it is used; avoid duplicate training step records | A blanket ban on ClickHouse recovery decisions |
| `MergeTree` plus explicit logical dedupe | Correctness never depends on background merges | `ReplacingMergeTree`, `FINAL` |
| Projections carry `(bootstrap_epoch, revision)` with compare-and-set; tombstones ordered | An old worker cannot resurrect a deleted model or reopen a policy | Last-write-wins projections |
| Restriction is a three-step barrier (intent and denial, project and acknowledge, commit) | Denial takes effect before the flag flips; nothing reopens through a stale snapshot | Flipping a boolean |
| Retention classes: sources 30 days, datasets and evidence indefinite, models by operator cleanup, intermediates 30 days | Training window, customer evidence and cost are different needs | One blanket TTL |
| Grants are scoped by the run token; no static IAM signer; presigned URLs at most 15 minutes | Least privilege with short-lived credentials | A long-lived signer user |
| Console-only management; one permission level for all active members | No customers yet; roles are removed rather than migrated | Role hierarchy; management API keys |
| Availability uses Prometheus request counters, edge metrics and external probes; internal target 99.9% per month | Use existing monitoring; show missing telemetry as unknown | Per-request availability event ledger |
| Standard managed backups of the stores in use | No custom backup service | A bespoke pipeline |

## OPS-01 Database authority and barriers

**Constraints.** Tenant-and-task foreign keys scope runs, models and production pointers. S3 manifests and ClickHouse events are authorized through their owning run or model; there are no PostgreSQL dataset-membership or artifact-operation rows. A production target must be in the same workspace and task and be available. Model lifecycle (`candidate`, `available`, `retired`) is distinct from runtime readiness reported through Valkey. Catalog readers stay compatible through a migration adapter. Partial unique index: one non-terminal run per task. Unique operation identities. CHECK constraints on run close times and required lifecycle fields. PostgreSQL stores current status; detailed execution history comes from ClickHouse.

Every JSON and event variant has a closed versioned schema with lengths, units and null semantics. Generation v3 makes API-key and release identity and unknown usage and cost nullable by mode; typed JSON paths and materialised columns migrate together; v1 and v2 rows keep their meaning; old rows, nulls and mixed readers are tested before v3 is emitted. All v3 generation events carry explicit `billing_mode` and `exemption_reason`; settlement filters billable records, never zero versus nonzero charge.

Workspace `proxy_settings.fallback_models` contains nullable `anthropic` and `openai` model IDs. It has a strict described JSON schema and uses the workspace policy revision. Updates project the complete policy before reporting success. Request overrides are transient. Tasks have no fallback field. Provider price metadata is optional analytics data and contains no credentials. GW-05 defines customer-key routing; no external-provider accounting is required.

**Records.** The gateway reads identity and the catalog from PostgreSQL through a Valkey cache keyed by the record, with a lifetime of `GATEWAY_RECORD_CACHE_TTL_SECONDS`. A record PostgreSQL does not have is never cached, so a created key or model is usable at once and a cache gap cannot hide an existing record. Nothing projects rows, so no resource carries a bootstrap epoch or a projected revision, and losing Valkey costs cache misses rather than availability. Deployment heartbeats are pushed by the runtimes and expire after 6 s; the gateway holds them for 1 s with no stale-on-error extension. Runtime registration validates actual Kubernetes pod ownership and enrollment (FLEET-05). Status binds allocation id, engine boot id, release and base/loader readiness; stale incarnations cannot overwrite current readiness. A running Kubernetes pod alone never opens routing.

**Restriction barrier.**

```mermaid
sequenceDiagram
  participant A as API
  participant PG as PostgreSQL
  participant W as Projector
  participant VK as Valkey
  participant G as Gateway
  A->>PG: 1. commit restriction intent (next revision)
  Note over PG: new grants and first starts blocked from here
  Note over G: after the record cache lifetime the denial is effective
  A->>PG: 3. commit final policy state; complete the operation
```

Concurrent intents on one resource are serialised. A projection failure leaves a visible pending restriction that retries; it never reports success or drops the denial. No transaction is held while waiting for Valkey. Reversal needs a newer revision. The projector treats a pending restriction as denial even if the stored boolean reads enabled; ingestion checks intent before accepting capture. Enabling is the inverse: commit and outbox, project, then report enabled. The console shows pending and effective separately. A started run's continuation authorisation is separate from capture permission.

**Valkey restore.** Identity and the catalog need no rebuild: they are cache misses that read PostgreSQL. The operational balance does. The gateway seeds an absent account hash from `billing_accounts.balance`, records the source timestamp that seed included, and applies later ledger entries idempotently past that watermark, so a restore recovers the balance on first use. Charges settled in Valkey but not yet posted to PostgreSQL are lost with the stream, as before. Deployment statuses return with the next heartbeat.

## OPS-02 Retention

| Content | Lifetime |
| --- | --- |
| Source traces and every copy or buffer | 30 days from trusted request start; reads and selection reject at expiry |
| Accepted datasets and final evaluation evidence | Indefinite, including copies of customer text; workspace deletion is outside launch scope |
| Published model payloads and manifests | No expiry field; SERV-04 operator cleanup after 365 days unused |
| Serving caches | Host-managed eviction when unused; cached files are not the authoritative artifact |
| Structured training execution events and result summaries | Indefinite for run history; checkpoint events do not extend checkpoint-file retention |
| Intermediate checkpoints and retained run files | 30 days from the run's terminal `finished_at`, the single execution |
| Unaccepted staging, partial uploads, disposable caches | Operation deadline or source expiry, whichever first |
| Content-free audit, names, accounting, deletion evidence | Existing durable metadata policy |

Within `runs/<run_id>/`, input staging, accepted datasets, checkpoints, output and evaluation files keep their own retention classes. There is no separate quarantine prefix or blanket run-prefix deletion.

Classes are independent: source expiry does not delete an accepted derivative; a derivative does not authorise new training from expired sources; export does not require keeping a training VM.

Accepting a dataset rechecks, in the transaction that commits the input manifest, the current policy and continuation authority, every source id and its expiry; the transaction time must precede each source's expiry. Only that manifest moves copies into derivative retention. Before reading a source, access and expiry are validated; before writing staging, the inventory (names, class, deadline) is persisted.

Capture in flight during a disable: the gateway rechecks policy before enqueueing; ingestion rejects expired or denied payloads and sweeps staged objects. Accepted data keeps its lifetime; started runs may use their accepted dataset.

Private data: `us-east-1`, encryption at rest, TLS, private bucket policies, separate publisher and trainer permissions. Platform processing in the US; providers process where they operate. No credential, signed URL or payload in logs, labels or events.

## OPS-03 Grants, cleanup and backups

**Grants.** New grants require a currently authorized, non-terminal run and an unexpired JWT; cancellation does not revoke previously issued JWTs. A grant names a purpose; the server resolves one exact object and version. Authorised by the run token's `artifacts:read:<purpose>` or `artifacts:write:<purpose>` scope (RUN-04). Purposes: dataset input, run output, bounded intermediate output. Refused: arbitrary keys, prefix listing, cross-run access. URLs last at most 15 minutes and no longer than the operation or source deadline. No static IAM signer: the control service's short-lived workload credentials sign, bounded by their validity; S3 and KMS access validated together. Job specs and Kubernetes Job specifications hold identities, never signed URLs or provider keys. A write inventory precedes every PUT or multipart grant. Exports use the same exact-version inventory and lifecycle checks.

**Cleanup.** Workspace deletion is outside launch scope. There is no purge endpoint, UI action or operation table. Archive stops use and retains records. Source TTL, temporary-file cleanup and the existing operator cleanup of unused model artifacts remain. Cleanup uses object manifests and storage lifecycle rules; it does not imply a workspace-wide deletion guarantee.

Artifact uploads, validation and publication use structured training-run events and S3 manifests. There is no generic artifact-operation table. Grants identify exact objects; the run log records issued upload grants and their expiry before use. Model records reference published artifacts. Incomplete uploads and temporary files are cleaned within their retention bounds. Cleanup must account for non-current object versions and outstanding upload lifetimes.

**Backups.** Standard managed mechanisms of the stores in use. Infrastructure setup records coverage, retention, restore procedure and physical-deletion bounds before launch. Every restore applies current tombstones and expiry before access reopens.

**Action audit helper.** A shared control-plane helper, `writeAuditEvent`, validates a versioned event with stable event ID, actor, action, workspace/resource identity, timestamp and bounded change details. It writes directly to ClickHouse `audit_events` after the action commits. Failures are caught and counted; they do not fail or undo the action. No PostgreSQL audit table, audit outbox, Kafka or durable queue is required at launch. Calls use a bounded timeout. This log is best effort and does not claim complete transactional coverage. Never include credentials or customer payloads. Durable buffering may be added later.

Action audit events are separate from `training_run_events`. Execution events needed to continue a run retain their acknowledged-write contract. A failed optional audit write must not be used as evidence that an action did not occur.

## OPS-04 Management and lifecycle

Console-only management with authenticated sessions and the generated client. Every route has a described schema, metadata, generated OpenAPI, client and tests. All active organisation members have equal authority; every action checks membership, ownership, lifecycle and request protections. Inference keys and run tokens never authorise management. Platform operators are separate. A live organisation keeps at least one active human member. Role-specific schemas are removed in increment 1 (no customers, so no live migration; if that changes, migrate safely).

No customer retire or unpublish action; `retired` is for operator cleanup; promotion never retires the previous version.

| Action | Checks and result |
| --- | --- |
| Read task, run, model, evaluation | Membership, scope; bounded pagination |
| Set the capture switch | Disclosure; OPS-01 barrier; no second switch |
| Configure a task | Immutable slug; exact base, reference, recipe; field errors |
| Request a run | Switch and permission; valid sources and recipe; one non-terminal run per task; no caps |
| Cancel a run | RUN-02 and RUN-04 durable cancel; models stay available |
| Promote or roll back | SERV-03; any valid available version; previous stays callable; no score gate |
| Export a version | Membership; not restricted for deletion; short-lived exact-object grant |
| Archive task or workspace | Restrict new capture, inference, runs; stop owned work; keep records; no deletion |

A task seen in valid traffic exists before configuration, collects eligible data when the switch permits, and shows `configuration_required` until base, reference, recipe and permissions are explicit. A base is never guessed from a provider name. Slugs never rename. Restore is an explicit revisioned action.

| Method and path | Request and response |
| --- | --- |
| `GET /workspaces/:workspaceId/tasks` | Cursor, page size; summaries and next cursor |
| `GET /workspaces/:workspaceId/connection-status` | Latest valid customer request and task from generations; capture policy; ingestion freshness; works with capture off |
| `POST /workspaces/:workspaceId/tasks` | `slug`, `display_name`, idempotency key; 201 or existing identical result |
| `PATCH /workspaces/:workspaceId/trace-capture` | `enabled`, `expected_revision`, disclosure version, idempotency key; 202 policy operation |
| `PATCH /workspaces/:workspaceId` | Expected workspace revision and typed `proxy_settings`; complete projection before success, or explicit pending state |
| `PATCH /tasks/:taskId` | Expected revision plus any of `display_name`, `base_release_id`, `reference_model_id`, `recipe_version`, `evaluation_judge_id`; 200; no slug change |
| `POST /tasks/:taskId/training-runs` | Expected task revision, idempotency key, optional explicit source selection; 202 run |
| `GET /training-runs/:runId` | Stage, deadline, execution identity, blocked reason, model and evaluation references |
| `POST /training-runs/:runId/cancel` | Expected revision, idempotency key; 202 |
| `PATCH /tasks/:taskId/production` | Target model id and expected production revision; prepare and set pointer; 200 with updated task after projection, or explicit propagation-pending response after commit |
| `POST /models/:modelId/exports` | Idempotency key; 201 bounded download operation |
| `POST /tasks/:taskId/archive`, `POST /workspaces/:workspaceId/archive` | Expected revision, idempotency key; 202 |
| `POST /tasks/:taskId/restore`, `POST /workspaces/:workspaceId/restore` | Expected revision, idempotency key; 202, subject to policy and capacity |
| `GET /operations/:operationId` | State, result reference, reason, observed revision |
| `GET /tasks/:taskId/models`, `GET /models/:modelId`, `GET /training-runs/:runId/evaluation` | Scoped views, bounded pagination |

Unknown fields rejected. Same key and payload returns the same operation; different payload 409. 401 without authentication; 404 for inaccessible resources with no cross-tenant disclosure; 409 stale revision; 422 field errors. Pending operations are never shown as completed. Membership removals serialise on the organisation row.

**Console.** Connection panel polls every 5 s while open and distinguishes request received, waiting for ingestion, capture off, eligible data accumulating; an empty capture table never means no connection. The switch "Capture traces and train models" is shown before and after the first task. Production version is distinct from newest. Shown: observed, captured, eligible and new-session counts; package selection counts; run stage and blocked reason; partial evaluation coverage; exact version identity; production status; last use and export; production projection status; capacity failures. Not shown or claimed: upload controls, management tokens, roles, automatic promotion, quality badges, recommendations, "all text deleted at day 30", or an SLA.

**Operator commands.** `stop-new-automation` (blocks new runs and first starts; started runs continue), `cancel-run`, `retry-run` (new linked run), `quarantine-host`, `retire-unused-models` (SERV-04). `quarantine-host` closes eligibility and new local compute; it does not claim that a running process has stopped. Reuse requires FLEET-04 cleanup or fencing evidence. Routine role changes wait for started training to finish. No patching of run stages, no bypass of validation, no management authority for inference keys.

## OPS-05 Availability, telemetry and incidents

Internal target: **99.9% successful eligible hosted-inference requests per UTC month**, measured with Prometheus counters. There is no customer-facing SLA or exact per-request availability ledger.

Count terminal successful and failed requests at the gateway. Capacity rejections, cold-load failures and interrupted streams are failures. Exclude invalid requests, authentication failures, explicit account-policy rejection and confirmed caller cancellation before a service failure. Distinguish these outcomes with bounded reason labels. Provider relay and internal evaluation are separate traffic classes.

Use edge error metrics and independent external probes to detect failures before requests reach the gateway. Display these signals alongside the gateway success ratio; do not add overlapping edge and gateway counts into one denominator. Missing scrapes, monitoring outages and zero traffic are explicit unknown or no-data states. Configure error-rate and monitoring-gap alerts. Generations support request diagnosis.

There is no `availability_events` table, availability Valkey stream, consumer or per-request reconciliation process. Monitoring must not block inference.

Grafana: request outcomes, cold-load and drain failures, desired versus ready capacity, Kubernetes Pending pods, autoscaler decisions and metric freshness, queue and run age, capture loss, eligibility yield, projection age, cache bytes, provider usage and cost coverage, cleanup lag; bounded labels; per-task and per-organisation views from scoped database queries.

Incidents: Incident.io, 24/7 coverage, 300 s human acknowledgement target, escalation and backup responders, drills before launch. No customer-facing SLA. Runbooks: stop automation, add capacity, quarantine, failed promotion or projection, bad-release rollback, expiry and artifact cleanup, capacity restoration.

## OPS-06 Rollout and rollback

Generation ingestion migrates to one `generation-events` stream. Deploy readers and settlement filtering before new writers. Drain the old stream through the existing consumer before retiring it; preserve generation IDs so overlap cannot charge twice. Map legacy billed events explicitly to `billable`; reject unknown classifications rather than guessing from price. No permanent dual-stream design is required. Test mixed billable/exempt traffic, duplicate delivery, zero-charge billable records, unknown usage, and backlog recovery.

Readers and schemas expand before writers. Gateway readers for private ids, run tokens, policy revisions and tombstones deploy before the worker publishes those records. Membership contract deploys coherently across API, client and console. Model and deployment classes are registered with workspace identity.

Rollout uses internal enable flags per increment, not customer switches; customer capture stays disabled until the capture-to-run path is ready. Old workers reject unsupported schema versions; new writers enable only when all consumers report compatible versions; mixed-version behaviour and Valkey bootstrap are audited.

Rollback after the first private model or run exists keeps compatible readers and denial and tombstone support: disable writers, bound or drain work, restore a known compatible release; never roll back to code that could relay a private model id or ignore a policy revision. Destructive down-migrations need an explicit plan; disabling never deletes customer state. The last compatible rollback release is recorded and tested before launch.

## Required evidence

S6: transactional effects, stale leaders, expiry, grants, cleanup, restore. S7: availability counting; response and recovery faults. API tests: wrong tenant, equal member permissions, inference-token rejection, session protections, idempotency, every lifecycle action. Infrastructure evidence: real backup coverage and restore results.

## Core proxy reporting

The [core proxy product plan](PROXY_FEATURE_PLAN.md) defines the usage API and console additions. Reporting works with capture disabled. Task production targets can select a global hosted open model or a private model from the same task and workspace. Preserve the private ownership constraints through an explicit target variant. Freeze baseline prices per generation. Unknown cost stays null. Signed savings never enter the billing ledger.
