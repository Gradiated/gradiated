# Architecture simplicity review

## Decision

The prior architecture was complete but over-specified. This review removes dependencies, deployables, projections and data-model layers that do not directly protect billing correctness, security, customer experience, inference quality or safe evolution.

The reduced seed has three application authorities, three product data services and one workflow engine:

- PostgreSQL owns customer, billing, catalog, trace metadata, fleet intent and research state;
- Valkey owns only the gateway's hot projection, reservations, concurrency and short-lived leases/streams;
- S3/ECR own encrypted payloads and immutable model/runtime artifacts;
- Temporal owns resumable research workflow execution/history but no domain decision;
- the Node control plane owns customer/business transitions;
- the Rust serving/fleet plane owns request execution and external-cell lifecycle;
- the Python research worker owns experiments and bundle construction.

Stripe, curated model APIs, external GPU providers and OpenRouter are external counterparties, not internal sources of truth. Kubernetes hosts processes but does not become an application data model.

This is an analytical architecture decision. It is falsified if a removed component is required to meet a measured correctness, security, availability, customer-latency or research-throughput target that the retained system cannot meet.

## Necessity test

Every dependency, service, table and field must answer at least one question:

1. Does it prevent lost/incorrect money, unauthorized access or retained-data leakage?
2. Does it materially improve the customer's setup, reliability, compatibility or understanding?
3. Is it required to execute or reproduce an owned model safely?
4. Is it the smallest practical way to survive a real failure we must handle now?
5. Is migration later materially harder without it?

If all answers are no, remove it. A standard library/controller also earns its place when it replaces custom state/retry/operations code and makes the system easier to maintain. If value begins only after measured scale or a partner contract, defer it behind a trigger. “Might be useful”, “industry standard” and “makes the architecture complete” are not sufficient.

## Complexity budget

### Seed runtime and stateful systems

| Dependency | Decision | Why / trigger |
| --- | --- | --- |
| PostgreSQL/Aurora | Keep | One durable transactional authority for money and all control state. Use schemas/roles, not separate database products. |
| Valkey | Keep | Required by the Redis-only gateway contract and atomic reserve/settle hot path. Use one production cluster with ACL/key/stream separation. |
| S3 | Keep | Cheap encrypted traces, research artifacts, reports and backups. Use separate buckets/prefix policies where IAM/lifecycle differ. |
| ECR | Keep | Immutable runtime/application images. Do not add a second OCI artifact registry. |
| AWS Private CA | Keep for external cells | A managed CA plus a narrow enrollment role avoids inventing certificate signing/rotation. It owns PKI only, not cell eligibility or release state. |
| Stripe | Keep | Customer top-ups. Only verified webhooks affect credit. |
| Better Auth tables | Keep in PostgreSQL | Avoid building identity/recovery. Better Auth's user is the product user; do not duplicate a profile/status table. |
| ClickHouse Cloud | Remove from seed | PostgreSQL indexed usage/trace metadata and small rollups provide the same seed UX. Reconsider only when a measured query/storage/ingest SLO fails at realistic retention. |
| Aurora analytics read model | Remove as a named subsystem | Ordinary PostgreSQL views/indexes are the initial analytics implementation. Add materialized/daily rollups only from measured queries. |
| Temporal | Keep for research execution | It replaces a custom durable scheduler, timers, retries, cancellation and recovery engine. Seed runs pinned Temporal services on EKS using a separate Aurora database/role and PostgreSQL visibility; no Elasticsearch/Cassandra. PostgreSQL product schemas remain domain authority. |
| Fleet CRDs | Remove | They duplicate PostgreSQL allocation/cell state and create field-ownership/conversion/rebuild machinery. Kubernetes hosts fleet controllers; provider abstraction is a Rust trait and SQL state machine. |
| Kubernetes etcd as product state | Reject | Kubernetes stores only Deployments/Jobs/configuration. No customer, money, release, allocation authority or per-request object. |
| Redis trace analytics stream | Keep as a separate stream on the same Valkey service | It keeps encrypted capture off response latency and cannot block the billing stream. It is not another database. |
| Prometheus/CloudWatch telemetry | Keep managed/bounded | Operational metrics/logs are required; payloads and unbounded IDs are forbidden. Long-term product analytics stay in PostgreSQL. |
| Local MinIO/Temporal/fake services | Keep in relevant test profiles | They are disposable fixtures, not product authorities. Remove local ClickHouse and the OCI registry from the default core profile. |

ClickHouse is not an “optional path” implemented behind an interface at seed: its adapter, schemas and projector are absent until a failing benchmark. Temporal is retained because removing it would create a bespoke workflow database/lease/retry implementation; its history never becomes research evidence or release authority.

### Application and build dependencies

| Dependency | Decision | Boundary |
| --- | --- | --- |
| Vite + React + TypeScript | Keep | User-requested static console. |
| Hono REST + `@hono/zod-openapi` | Keep | One described Zod route registry serves the Vite app and generates OpenAPI 3.1, clients, docs and a security-allowlisted MCP adapter. tRPC is removed. |
| Scalar + OpenAPI TypeScript + MCP SDK | Keep narrowly | Build-time/docs/client adapters over the REST artifact; none owns business logic or durable state. |
| TanStack Query/Router | Keep | Server cache and URL-scoped organization/workspace state. |
| Tailwind + shadcn/ui | Keep | User-requested single UI system. |
| React Hook Form | Keep | It removes repetitive form state/error plumbing; use it only for forms and share Zod transport schemas. |
| Zod | Keep at untrusted boundaries | Do not mirror domain objects in Zod internally. |
| Drizzle + node-postgres | Keep | Typed schema/query composition and explicit SQL transactions. Use direct SQL for locks/ledger invariants; no second ORM. |
| Better Auth | Keep | Identity/session/recovery only. No competing organization plugin authority. |
| Stripe/AWS/Valkey SDKs | Keep at adapters | Never leak SDK objects into domain models. |
| Axum/Tower/Tokio/Reqwest/rustls/serde/tracing | Keep | Minimal Rust HTTP/streaming stack. |
| Separate Rust crate per provider/protocol | Remove initially | One gateway crate with private modules plus contracts/testkit. Split only for compile/ownership pressure. |
| Protobuf + Buf/Prost | Narrow and keep | Only cross-language hot serving, Redis projection/event and cell contracts. TS-only domain events and research artifacts do not use Protobuf. |
| OpenAPI/JSON fixtures | Keep | Public wire compatibility cannot be inferred from internal types. |
| Python + PyTorch/Triton | Keep | Fast model/operator/kernel research. Transformers/vLLM are pinned runtime/research dependencies, not control-plane dependencies. |
| Private Python research API | Keep | It preserves one writer for research state and prevents Hono/Python sharing mutation rules. Generated Protobuf clients keep the boundary explicit. |
| Artifact schemas | Combine selectively | Keep generic artifact, runtime, bundle and qualification-report schemas. Remove separate schemas that only repeat bundle fields; do not collapse reusable runtime/checkpoint detail into an opaque blob. |
| fast-check/proptest/Hypothesis | Keep | They directly protect money, concurrency, state-machine and tensor/operator invariants. |
| OpenTelemetry SDK/exporter everywhere | Defer exporter breadth | Use structured `tracing`/application metrics first; add spans only on diagnosed paths. |

### Infrastructure and controller dependencies

| Dependency | Decision | Why / trigger |
| --- | --- | --- |
| EKS | Keep | Explicit product constraint and common host for AWS control/data processes. External GPU cells are not joined to it. |
| EKS Auto Mode | Preferred after a staging gate | AWS currently manages compute scaling, networking, load balancing and storage components; it can remove self-managed Karpenter/LB/CNI/CSI/Pod Identity add-ons. Fall back to fixed managed node groups if cost/restrictions fail. |
| Self-managed Karpenter | Remove from seed | Duplicates Auto Mode. Reintroduce only for an unsupported placement/cost requirement. |
| KEDA | Keep | Queue/stream age is the correct worker scaling signal and avoids custom autoscaling. Critical roles retain static floors/fallbacks; it owns no business state. |
| Kueue/JobSet | Keep where execution requires them | Kueue owns Kubernetes research quota/admission; JobSet is used only for actual distributed jobs. Native-provider jobs remain native and do not acquire fake Kubernetes objects. |
| Kyverno | Keep a small policy set | Runtime admission enforcement protects immutable images/security contexts/unsafe manifests and avoids bespoke webhooks. Do not turn business policy into cluster policy. |
| cert-manager/reloader/service mesh | Reject at seed | ACM terminates public TLS; explicit restarts and app mTLS cover the need. |
| Argo CD | Keep one installation | Pull-based deploys preserve private EKS and Git authority without a VPC CI runner. It owns static desired state only. |
| Terraform | Keep | AWS authority and reproducibility. |
| Terragrunt | Keep | It reduces environment/root repetition and dependency wiring while Terraform remains resource authority. Pin it and keep units shallow; do not use hooks/generation as a second programming framework. |
| Helm | Keep | One library chart and a small number of role-valued application charts. |
| Docker Compose + mprocs + `grad` | Keep | Explicit user requirement and the agent-facing local/CI surface. `grad` remains a transparent wrapper. |
| Four AWS accounts | Keep minimum | Management, security-log, non-production and production. No always-on development cluster; local/CI plus staging are sufficient initially. |

Primary-source check, retrieved 2026-07-14: AWS reports that EKS Auto Mode manages compute autoscaling, pod networking, load balancing, storage and Pod Identity components, while managed node groups remain a fallback ([Auto Mode](https://docs.aws.amazon.com/eks/latest/userguide/automode.html), [managed node groups](https://docs.aws.amazon.com/eks/latest/userguide/managed-node-groups.html)). HashiCorp documents native S3 lock files and deprecates DynamoDB locking, so Terragrunt needs no additional lock database and can remain a stateless composition tool ([S3 backend](https://developer.hashicorp.com/terraform/language/backend/s3)). These are vendor-reported; staging still validates cost, restrictions and required features.

## Reduced deployable topology

| Artifact | Role deployments | Why not combine further |
| --- | --- | --- |
| `web` static artifact | CloudFront/S3 | no server runtime |
| `control` Node image | `api`, `financial`, `intelligence`, `trace-access` | same code/image; separate roles only where IAM, scaling or KMS decrypt differs |
| `gateway` Rust image | public gateway | public latency/money trust boundary |
| `inference-router` Rust image | private cell tunnel/dispatch registry | external-cell network boundary; no provider lifecycle credentials |
| `fleet` Rust image | planner, cell enrollment/sweeper, plus one provider-driver role per credential | slow path with provider lifecycle/PKI authority; cannot share serving identity |
| `cell-agent` Rust image | external cell supervisor/router | external trust boundary and runtime lifecycle |
| `research` Python image | private API, Temporal workflow/activity and evaluator roles | model dependencies must not enter Node/Rust serving images; evaluator uses a distinct role even if image is shared |
| model runtime image | one OCI image per qualified bundle runtime | language-neutral execution artifact supervised by cell agent |

There is no separate analytics projector, recommendation service, CRD controller or trace-worker codebase. The private research API and Temporal workers share the `research` source/image with role-specific credentials.

## Contract simplification

### Events

Delete the universal `PrincipalRef`, aggregate envelope, correlation/causation fields and Protobuf event taxonomy. A generic event that works for every domain makes every consumer branch on fields that may not apply.

The PostgreSQL outbox has only:

```text
id, type, schema_version, payload_json, occurred_at,
available_at, published_at, attempts, last_error_code
```

Each typed payload carries only its own IDs. Billing stream records are the sole binary cross-language events and use:

```text
ReservationCreated
  event_id, request_id, reservation_id
  organization_id, workspace_id, api_key_id
  requested_model_id, release_digest
  reserved_micros, started_at, expires_at

UsageSettled
  event_id, request_id, reservation_id
  organization_id, workspace_id, api_key_id
  release_digest, actual_target, usage
  sell_micros, buy_micros?, attempts_json
  terminal_status, usable_output_delivered, cancellation_owner?
  completed_at
```

These are not generic observability fields: they are exactly the inputs needed to create the required `usage_records` row, apply failed-request credit policy and reconcile provider cost without another request-attempt table. `attempts_json` is bounded, typed at the producer and contains no provider endpoint secret or payload. Channel events replace organization/workspace/key with `channel_id` and `credential_id`; they share the same Rust admission implementation but never the same balance key. Research uses PostgreSQL rows, not a general event bus.

### Gateway-to-cell

Remove billing, public-product and duplicated policy fields from the cell request. The gateway has already admitted an immutable release.

```text
GenerateRequest
  request_id
  attempt_id
  release_digest
  canonical_input
  max_output_tokens
  deadline
  cache_scope
  traceparent

GenerateEvent
  output_delta(sequence, bytes)
  usage_update(input_tokens, cached_input_tokens, output_tokens)
  completed(finish_reason, authoritative_usage)
  failed(code, retryable_before_output, authoritative_usage_if_known)
```

Remove `reservation_id`, `route_release_id`, separate manifest digest, public model ID, effort, speed, capability requirements, data mode, queue deadline and idempotency token. They are either gateway-only, fixed by `release_digest`, derived from `deadline`, or equal to `attempt_id`. Accepted/queued events remain internal metrics, not protocol states.

### Artifact and runtime contract

Use a small compositional schema set: generic `ArtifactDescriptor`, `CheckpointManifest`, `RuntimeManifest`, `BundleManifest`, and immutable `QualificationReport`. Checkpoint/runtime detail can evolve and be reused without bloating every bundle. `RuntimeManifest` contains the exact one-or-many-node topology, parallelism, collective/fabric, command, software bounds and cache layout. The bundle contains:

```text
schema_version
source_model { repository, revision }
source_commit
parent_bundle_digest?
checkpoint_manifest_digest
runtime_manifest_digest
artifacts[] { digest, size, media_type, role, object_key }
compatibility { accelerator_families, min_memory_bytes, driver_runtime_bounds }
capabilities { context, output, modalities, tools, structured_output }
cache { implementation_version, layout_version }
known_limitations[]
```

Each manifest digest is the hash of its canonical bytes and is not self-referential. Creation time, experiment IDs, qualification, mutable status, prices and rollout do not belong in runtime identity. Runtime language is deliberately absent: Python, C++ or Rust is an image implementation detail behind the same local protocol. Sign the bundle and runtime image provenance; referenced manifests/artifacts are protected by digests rather than independent product signatures.

## Minimal persistent model

Fields below are the seed schema contract. `id` is a stable opaque identifier; all timestamps are UTC. Tables add database housekeeping columns only when an implemented query/lock requires them. Do not add free-form `metadata`, speculative lifecycle timestamps or duplicated display fields.

### Identity and tenancy

| Model | Required fields | Removed/deferred |
| --- | --- | --- |
| Better Auth user/session/OAuth-provider tables | library-required identity/session/recovery/OAuth client-consent-token fields | duplicate product `users` or custom OAuth token tables |
| `organizations` | `id`, `name`, `status`, `stripe_customer_id?`, `created_at` | global policy blob, risk enum and duplicated deletion-phase fields |
| `organization_deletions` | `id`, `organization_id`, `requested_by`, `status`, `requested_at`, `execute_after`, `completed_at?`, `cancelled_at?`, `last_error_code?` | generic workflow engine/step/event rows; one idempotent workflow row is required for refund/purge recovery |
| `organization_members` | `organization_id`, `user_id`, `role`, `status`, `created_at` | surrogate membership ID, per-action grants |
| `invitations` | `id`, `organization_id`, `email`, `role`, `token_digest`, `expires_at`, `accepted_at?`, `revoked_at?`, `created_by`, `created_at` | invitation state enum derivable from dates; revocation is required token invalidation evidence |
| `workspaces` | `id`, `organization_id`, `name`, `status` (`active|suspended|archived`), `is_default`, `data_mode`, `retention_days` (`7|30`, default `30`), `monthly_limit_micros?`, `concurrency_limit`, `policy_version`, `created_at` | independent wallet, daily/weekly/lifetime budget records, route builder, observability settings blob; archival is terminal and non-Default only |
| `workspace_members` | `workspace_id`, `user_id`, `role`, `created_at` | surrogate ID and duplicate status; organization membership controls active state |
| `workspace_models` | `workspace_id`, `model_id` | nullable model-ID arrays/policy JSON; absence of rows means the curated organization catalog |
| `api_keys` | `id`, `organization_id`, `workspace_id`, `name`, `prefix`, `digest`, `pepper_version`, `status`, `monthly_limit_micros?`, `concurrency_limit?`, `expires_at?`, `created_by`, `created_at` | scopes, metadata, last-four, persisted last-use, in-place rotation/grace state; create new then revoke old and derive last use from usage |

One monthly budget is enough initially. Add other windows only after a customer requirement; each extra window multiplies Redis and reconciliation state.

### Money and usage

| Model | Required fields | Removed/deferred |
| --- | --- | --- |
| `organization_balances` | `organization_id`, `available_micros`, `version`, `updated_at` | risk state and multiple balance buckets; this is a rebuildable locked snapshot of the ledger |
| `ledger_accounts` | `id`, `scope`, `organization_id?`, `channel_id?`, `kind`, `currency`, `created_at` | generic owner ID, arbitrary customer-created accounts and multi-currency at seed; checks/FKs allow exactly platform, one organization or one channel scope |
| `ledger_transactions` | `id`, `type`, `business_key`, `source_type`, `source_id`, `effective_at`, `created_at` | duplicated owner fields derivable from accounts, mutable state and generic metadata blobs |
| `ledger_entries` | `transaction_id`, `account_id`, `amount_micros` | per-entry free-form descriptions; transaction carries evidence identity |
| `topup_intents` | `id`, `organization_id`, `amount_micros`, `status`, `stripe_session_id?`, `stripe_payment_id?`, `idempotency_key`, `created_at`, `completed_at?` | arbitrary currency (USD only at seed), provider metadata blobs |
| `payment_events` | `provider_event_id`, `type`, `object_id`, `received_at`, `processed_at?`, `status`, `error_code?` | raw webhook payload retention and generic retry metadata |
| `usage_records` | `id`, `request_id`, `organization_id`, `workspace_id`, `api_key_id`, `release_digest`, `requested_model_id`, `actual_target`, `status`, `reserved_micros`, `sell_micros?`, `buy_micros?`, `input_tokens?`, `cached_input_tokens?`, `output_tokens?`, `attempts_json`, `started_at`, `completed_at?` | separate usage charge/correction/attempt/route-decision tables, duplicated provider/model/price-book IDs |

Top-ups, usage, refunds, chargebacks and corrections are immutable balanced transactions. A correction links to the original usage through transaction source fields; no separate `usage_corrections` state machine is needed. The fixed chart is cash/processor clearing, customer credit liability, usage revenue and adjustments. Invariant tests prove every transaction sums to zero by currency, business effects are idempotent and the customer-credit account matches the balance projection.

### Catalog and release

| Model | Required fields | Removed/deferred |
| --- | --- | --- |
| `provider_endpoints` | `id`, `provider`, `region`, `base_url`, `credential_ref`, `status`, `updated_at` | separate provider definition and endpoint capability copies |
| `model_definitions` | `id`, `public_id`, `kind`, `provider?`, `upstream_model_id?`, `status`, `created_at`, `updated_at` | separate product/family entities and copied capabilities/prices |
| `model_releases` | `digest`, `model_id`, `bundle_digest?`, `capabilities_json`, `context_limit`, `output_limit`, `input_price_micros`, `output_price_micros`, `cache_price_micros?`, `max_pre_output_retries`, `status`, `created_at`, `activated_at?` | generic route-policy JSON, separate price book/release manifest/rollout entities |
| `release_endpoints` | `release_digest`, `endpoint_id`, `priority`, `weight` | generic route-candidate constraints duplicated from qualification/release |
| `model_aliases` | `model_id`, `stable_release_digest`, `canary_release_digest?`, `canary_basis_points`, `generation`, `updated_at` | duplicated alias text already held by `model_definitions.public_id`, route rollout table, audience DSL, separate alias-head/family records |
| `qualification_runs` | `id`, `subject_digest`, `scope_json`, `policy_version`, `result`, `report_object_key`, `expires_at?`, `created_at` | qualification evidence/gate rows duplicated from immutable report |

Concrete direct endpoints remain relational; owned placement lives in `capacity_targets`. The only release-level retry option is a bounded pre-output retry count. A release digest is computed from canonical release fields plus its ordered direct endpoint membership, so a changed endpoint set creates a new release. Public family names are ordinary model definitions/aliases; no `ModelFamily` entity. The generic effort/speed grammar is parsed, but only published aliases exist.

### Traces and recommendations

| Model | Required fields | Removed/deferred |
| --- | --- | --- |
| `traces` | `id`, `request_id`, `organization_id`, `workspace_id`, `capture_status`, `object_key?`, `object_digest?`, `wrapped_key?`, `size_bytes?`, `created_at`, `expires_at?`, `deleted_at?` | ClickHouse projection state, content-class arrays, export state machine, per-trace analytics versions |
| `recommendations` | `id`, `workspace_id`, `source_model_id`, `candidate_release_digest`, `summary_json`, `status`, `created_at`, `expires_at?` | separate workload profile, migration candidate and recommendation entities |
| `evaluations` | `id`, `recommendation_id`, `mode`, `status`, `budget_micros`, `authority_json`, `stop_conditions_json`, `result_json?`, `created_at`, `completed_at?` | generic migration state hierarchy; authority/stops are required safety inputs for replay, shadow or live canary |

Usage lists, charts and workload groupings are PostgreSQL queries over `usage_records`; retained detail is one authorized trace read. Add a rollup table only when an `EXPLAIN ANALYZE` benchmark proves the indexed query misses its SLO. Trace access uses a short-lived signed grant whose nonce is consumed in Valkey; no durable grant table.

### External distribution

| Model | Required fields | Removed/deferred |
| --- | --- | --- |
| `distribution_channels` | `id`, `name`, `status`, `data_policy`, `exposure_limit_micros`, `concurrency_limit`, `catalog_version`, `created_at`, `updated_at` | derived outstanding amount, risk/profile/legal-owner/settlement-policy blobs; contract terms live in the signed commercial document |
| `channel_balances` | `channel_id`, `outstanding_micros`, `version`, `updated_at` | multiple exposure buckets; this is a rebuildable locked ledger projection like organization balance |
| `channel_credentials` | `id`, `channel_id`, `prefix`, `digest`, `pepper_version`, `status`, `expires_at?`, `created_at` | separate credential profile object and persisted last-use |
| `channel_catalog` | `channel_id`, `external_model_id`, `release_digest`, `input_price_micros`, `output_price_micros`, `cache_price_micros?`, `status`, `updated_at` | generic price JSON and copied capabilities/regions/readiness already derived from release/cell state |
| `channel_usage_records` | `id`, `request_id`, `channel_id`, `credential_id`, `release_digest`, `external_model_id`, reserve/sell/buy/token/attempt/timing facts | nullable organization/workspace/key identity, payload or customer trace linkage |
| `channel_statements` | `id`, `channel_id`, `period_start`, `period_end`, `object_key`, `digest`, `status`, `delta_micros?`, `created_at` | implement only when the first native contract requires statement reconciliation |

Workspace and channel accounting remain separate keys/account charts and foreign-key domains, but use the same balanced transaction implementation. Statement start/end are evidence supplied by the counterparty contract, not a configurable Grad billing-period engine. OpenRouter is the only native channel built first. Hugging Face and all others remain decision records, not code dependencies.

### Owned capacity

| Model | Required fields | Removed/deferred |
| --- | --- | --- |
| `capacity_sources` | `id`, `provider`, `driver`, `region`, `config_ref`, `status`, `hourly_budget_micros`, `created_at` | Kubernetes pool CR, provider capability duplication and dynamic plugin discovery |
| `capacity_targets` | `release_digest`, `region`, `capacity_class`, `minimum_cells`, `maximum_cells`, `budget_micros_hour`, `updated_at` | generated intent generations and separate ownership epochs |
| `allocations` | `id`, `source_id`, `provider_allocation_id?`, `release_digest`, `desired_state`, `observed_state`, `lease_epoch`, `lease_owner?`, `lease_expires_at?`, `bootstrap_token_digest?`, `bootstrap_expires_at?`, `quoted_micros_hour?`, `created_at`, `last_error_code?`, `cleanup_state` | CRD spec/status mirror, bid/history/event tables until required by provider contract |
| `allocation_members` | `allocation_id`, `ordinal`, `role`, `provider_resource_id?`, `observed_state`, `bootstrap_token_digest?`, `bootstrap_expires_at?`, `joined_at?`, `last_observed_at?`, `cleanup_state` | pod/IP/rank metrics and generic topology tables; member rows are required to acquire and prove cleanup of multi-node resources |
| `cells` | `id`, `allocation_id`, `release_digest`, `region`, `status`, `capacity_class`, `attestation_digest`, `identity_serial`, `identity_expires_at`, `last_observed_at`, `drain_at?` | ephemeral connection ID, signed target document, pod/instance topology and per-request state |

The router uses an ephemeral in-memory registry built from authenticated cell connections/heartbeats. PostgreSQL retains lifecycle observations but is not consulted per request. A cell generates its private key and exchanges a one-use allocation-bound token/CSR at the enrollment role for a short-lived AWS Private CA certificate; rotation uses the current identity plus active allocation. mTLS allocation identity and exact bundle/release attestation are the trust boundary. Valkey cell projections, per-target signatures and a dedicated route-signing service are removed. Signed bundles and exact release digests remain mandatory.

### Research

| Model | Required fields | Removed/deferred |
| --- | --- | --- |
| `research_programs` | `id`, `name`, `model_source_json`, `scope_json`, `status`, `baseline_bundle_digest?`, `champion_release_digest?`, `budget_micros`, `created_at`, `updated_at` | stored Pareto frontier, open questions, negative-findings arrays and queue state; these derive from evidence |
| `research_hypotheses` | `id`, `program_id`, `claim`, `scope_digest`, `intervention_json`, `falsification_json`, `priority`, `status`, `created_at` | separate queue-entry table and persisted expected-information score |
| `research_campaigns` | `id`, `program_id`, `name`, `scope_json`, `budget_micros`, `deadline`, `status`, `created_at` | nested campaign hierarchies and duplicated queue state |
| `experiment_specs` | `id`, `hypothesis_id`, `campaign_id?`, `source_commit`, `inputs_json`, `metrics_json`, `budget_micros`, `timeout_seconds`, `stop_condition_json`, `created_at` | mutable specs and provider/runtime observations |
| `experiment_runs` | `id`, `spec_id`, `temporal_workflow_id`, `status`, `environment_manifest_digest?`, `result_object_key?`, `started_at?`, `completed_at?` | mutable environment/result JSON, Temporal event history copied into PostgreSQL and arbitrary step/job rows |
| `evidence_reports` | `id`, `program_id`, `scope_digest`, `conclusion`, `evidence_class`, `report_object_key`, `status`, `created_at` | one row per metric/gate and stored Pareto/open-question projections |
| `bundles` | `digest`, `manifest_object_key`, `runtime_image_digest`, `parent_digest?`, `source_run_id`, `created_at` | mutable bundle status, separate mutable candidate entity and runtime-mode enum |
| `bundle_qualifications` | `id`, `bundle_digest`, `policy_version`, `status`, `report_object_key`, `expires_at?`, `created_at`, `completed_at?` | per-gate relational rows and qualification manifest |

Hypothesis is durable scientific intent, campaign is a real budget/authority envelope, spec is immutable execution intent, run is one observed execution and evidence report is reviewed synthesis. Temporal owns step/timer/retry history; PostgreSQL stores only domain milestones/refs. Negative findings are falsified runs plus evidence reports. Pareto frontier/open questions/ranked queue are queries, not stored projections. A challenger is a bundle, not another mutable candidate object.

### Operations and delivery

| Model | Required fields | Removed/deferred |
| --- | --- | --- |
| `outbox` | `id`, `type`, `schema_version`, `payload_json`, `occurred_at`, `available_at`, `published_at?`, `attempts`, `last_error_code?` | universal principal/aggregate/correlation envelope and second event store |
| `audit_records` | `id`, `organization_id?`, `actor_kind`, `actor_id`, `action`, `resource_kind`, `resource_id`, `result`, `occurred_at` | payload snapshots, free-form metadata and a generic workflow log |

`organization_balances` and `channel_balances` are the two intentional derived financial rows: they provide one lockable current balance for transaction posting and hot publication, and are continuously checked/rebuildable from the ledger. No other ledger total is persisted merely for display.

## Simplified state machines

- Organization: `active -> deletion_pending -> deleted`, with cancellation restoring `active` before irreversible purge; suspension remains an operator policy state. Workspace is `active|suspended|archived` with terminal non-Default archival; key is `active|revoked` plus expiry by clock.
- Organization deletion: `pending -> running -> completed | blocked`, with `pending -> cancelled`; blocked retries after the financial/external condition is repaired.
- Top-up: `created -> completed | failed | expired`; refunds/chargebacks append entries and do not reopen the intent.
- Usage: `reserved -> settled | abandoned`; a correction is an immutable balanced ledger transaction.
- Model release: `draft -> active -> retired`; aliases hold stable/canary pointers. Rollback is a pointer change.
- Allocation: `requested -> provisioning -> ready -> draining -> released | failed`; cleanup state is independently `pending|confirmed|uncertain`.
- Research experiment: `queued -> running -> succeeded | falsified | failed | cancelled`; immutable `experiment_specs` own pre-queue intent and cleanup uncertainty blocks provider acquisition without adding another run status.
- Bundle bytes/digest have no mutable state. `bundle_qualifications` is `pending -> passed | failed`; public activation belongs to `model_releases`.
- Recommendation: `pending -> accepted | dismissed | expired`; evaluations have `queued -> running -> completed | failed | cancelled`.

Do not add a state unless it changes an allowed command, customer display, billing effect or required recovery action.

## Product-quality features retained

Simplification does not remove the product's differentiators or safety:

- organization billing with multiple workspaces, memberships, keys, limits and a Default workspace;
- owner self-service organization deletion with admission suspension, unused-credit refund, cryptographic payload deletion and pseudonymous financial retention;
- verified prepaid top-ups, fail-closed atomic admission, low-balance concurrency and reconciliation;
- OpenAI Responses and Anthropic Messages direct onboarding, exact provider/model identity and strict capabilities;
- first-party `grad/<effort>/<speed>` aliases, immutable releases and owned external-GPU serving;
- default encrypted Product Intelligence plus opt-in no-retention and always-on isolated KV cache;
- customer-visible traces, usage, workload summaries and explicit recommendations;
- direct use, customer-configured gateways and native OpenRouter distribution;
- always-on bounded research, exact bundle reproducibility, independent qualification and human public promotion;
- single- and multi-node external GPU cells behind one exact-release serving contract;
- property-based/state-machine tests and protected real-provider/client checks.

## Implementation order after subtraction

1. One repository/toolchain, PostgreSQL, Valkey, S3 fake, shared contracts and PBT replay.
2. Better Auth, described Hono REST/OpenAPI client/docs, organization/Default workspace/key/self-service deletion, Stripe top-up, fixed-chart double-entry ledger and Redis projection.
3. Rust Models/Responses/Messages gateway through curated direct providers with reserve/settle/reconcile and PostgreSQL usage UI.
4. Trace encryption/S3/detail and PostgreSQL usage/workload views; no ClickHouse/projector.
5. Generated allowlisted MCP role plus customer-gateway recipes; other inference protocols only when demanded.
6. One bundle/runtime, inference router, one capacity-source driver, single/multi-node cell qualification and one `grad/medium/standard` alias; no CRDs.
7. Python research API + Temporal workflow/activity workers and one continuous research program; Kueue/JobSet only for matching Kubernetes jobs.
8. One native OpenRouter channel using the shared admission/entry core.
9. Terragrunt/Terraform, EKS Auto Mode, Argo, KEDA and policy-controller production qualification, recovery and measured autoscaling.

## Reintroduction triggers

| Removed component | Evidence required before an ADR may add it |
| --- | --- |
| ClickHouse | production-shaped PostgreSQL ingest/query/storage test misses explicit SLO/cost after indexing/partition/rollup work |
| Fleet CRDs | a second controller/client needs a Kubernetes-native public API and SQL commands cannot express safe reconciliation |
| Karpenter | EKS Auto Mode or managed groups fail a required placement, cost or availability envelope |
| Separate model entities | a real product operation cannot be represented by immutable releases plus aliases without unsafe JSON mutation |
| Stored research projections | a measured query cannot derive queue/frontier/open-question views from source evidence inside its SLO |

The default response to scale is still to tune and partition the retained system before adding a database, queue, controller or abstraction layer.
