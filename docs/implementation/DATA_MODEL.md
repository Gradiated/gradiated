# PostgreSQL physical data model

Status: canonical seed migration contract

This document turns the minimal model in [the simplicity review](../SIMPLICITY_REVIEW.md#minimal-persistent-model) into migration-level guidance. It defines required columns, keys and constraints. An implementation may choose equivalent SQL names only through a contract ADR and generated migration fixture update.

## 1. Global conventions

- PostgreSQL major version matches the selected Aurora version.
- IDs are application-generated UUIDv7 values stored as `uuid`.
- Timestamps are `timestamptz`, UTC, database-defaulted only for actual insertion time.
- Money is `bigint` micro-USD. Arithmetic happens in checked application wrappers and database sums use `numeric` before checked conversion.
- Digests are lowercase `text` in `sha256:<64 hex>` form with a check constraint.
- Enums are constrained `text`, not PostgreSQL enum types, so additive rollout remains migration-safe.
- JSONB exists only for closed schemas named below. The application validates schema/version before write; a database check at least enforces object/array shape.
- Foreign keys are explicit. Financial/evidence rows use `RESTRICT`; disposable membership/policy links may use controlled `CASCADE` only through the owning workflow.
- Every tenant query includes organization and, where applicable, workspace in the predicate even when an ID is globally unique.
- `created_at` is not added automatically to join/projection rows unless listed. `updated_at` exists only for mutable current rows.
- No free-form `metadata`, arbitrary tags, soft-delete timestamp or speculative lifecycle timestamps are allowed.

The DB package exports table types and repositories. Domain/application packages never issue raw SQL. Better Auth owns its required user/session/recovery/OAuth tables and migrations; product code does not duplicate them.

## 2. Identity and tenancy

### `organizations`

| Column | Type | Rule |
| --- | --- | --- |
| `id` | uuid | primary key |
| `name` | text | non-empty, bounded display name |
| `status` | text | `active`, `suspended`, `deletion_pending`, `deleted` |
| `stripe_customer_id` | text nullable | unique when non-null |
| `created_at` | timestamptz | required |

Indexes: status for operator/deletion scans; no customer list query may omit membership join. `deleted` rows retain only identity needed to connect legally retained evidence and are pseudonymized by the deletion workflow.

### `organization_deletions`

| Column | Type | Rule |
| --- | --- | --- |
| `id` | uuid | primary key |
| `organization_id` | uuid | FK organizations, restrict |
| `requested_by` | text | Better Auth user ID at request time; pseudonymized on completion if policy requires |
| `status` | text | `pending`, `running`, `completed`, `cancelled`, `blocked` |
| `requested_at` | timestamptz | required |
| `execute_after` | timestamptz | required and not before requested time |
| `completed_at` | timestamptz nullable | only completed |
| `cancelled_at` | timestamptz nullable | only cancelled |
| `last_error_code` | text nullable | stable bounded code, no external body |

Indexes: `(status, execute_after)` for worker claims and a unique partial index on `organization_id WHERE status IN ('pending','running','blocked')`. Row is locked during transition. Cancellation preserves the row and a later request creates a new row; no generic step/event tables exist.

### `organization_members`

Composite primary key `(organization_id, user_id)`. Columns: organization FK, Better Auth `user_id` text, `role` constrained to owner/admin/billing/member, `status` active/suspended, `created_at`. Index `(user_id, status)` supports organization chooser. Last-owner and active-user rules are transaction/service invariants.

### `invitations`

Columns: `id` PK, organization FK, normalized lowercase `email` text, role owner/admin/billing/member as permitted by policy, unique `token_digest`, `expires_at`, nullable `accepted_at`, nullable `revoked_at`, `created_by` Better Auth user ID and `created_at`.

Indexes: organization + lower(email), token digest, expiry scan, and one active invitation per `(organization_id, lower(email))`. State is derived: accepted, revoked, expired or pending; accepted/revoked are mutually exclusive. Reissue transactionally revokes the prior pending invitation and creates a new invitation/token. Rows plus audit preserve the evidence; a revoked token never resolves.

### `workspaces`

Columns: `id` PK, organization FK, `name`, status active/suspended/archived, `is_default` boolean, data mode product_intelligence/no_retention, `retention_days` constrained to 7 or 30 (default 30), nullable nonnegative `monthly_limit_micros`, positive `concurrency_limit`, positive `policy_version`, `created_at`.

Constraints/indexes:

- unique partial index on `organization_id WHERE is_default` (at most one);
- unique `(organization_id, lower(name))`;
- index `(organization_id, status)`;
- Default existence/non-deletion is a transaction and state-model invariant because SQL alone cannot prove “at least one” during creation/deletion safely.

Archival is terminal, allowed only for a non-Default workspace, revokes its keys and serving projection in one application transaction, and retains workspace/usage/trace metadata for financial and customer-retention obligations. It is not a payload purge; trace delete/retention and organization deletion own those semantics.

### `workspace_members`

Composite primary key `(workspace_id, user_id)`. Columns: workspace FK, Better Auth user ID, role admin/developer/viewer, `created_at`. Organization membership active state is always rechecked. Index `(user_id, workspace_id)`.

### `workspace_models`

Composite primary key `(workspace_id, model_id)`. Both are FKs. Absence of rows for a workspace means the curated organization catalog, not “deny all.” Policy builder must encode this meaning in the snapshot golden.

### `api_keys`

Columns: `id` PK, organization/workspace FKs with a composite constraint proving workspace belongs to organization, bounded `name`, unique `prefix`, keyed `digest` bytes/text, positive `pepper_version`, status active/revoked, nullable nonnegative monthly limit, nullable positive concurrency limit, nullable expiry, `created_by`, `created_at`.

Indexes: `(organization_id, workspace_id, status)`, prefix lookup, expiry scan. Raw secret and last-four are not stored. Rotation creates a new row then revokes the old.

## 3. Ledger, payment and usage

### `organization_balances`

Primary key/FK `organization_id`; `available_micros bigint`, positive `version bigint`, `updated_at`. Available may become negative after an externally forced chargeback; admission still requires sufficient nonnegative availability. This row is locked and updated in the same transaction as ledger posting and can be rebuilt.

### `ledger_accounts`

Columns: `id` PK, scope platform/organization/channel, nullable organization FK, nullable channel FK, constrained fixed-chart `kind`, currency fixed to USD, `created_at`.

A check requires exactly the identity appropriate to scope: platform has neither owner, organization has only organization, channel has only channel. Unique `(scope, organization_id, channel_id, kind, currency)` with null-safe treatment prevents duplicate fixed accounts.

### `ledger_transactions`

Columns: `id` PK, constrained `type`, unique `business_key`, `source_type`, `source_id`, `effective_at`, `created_at`. No mutable state or metadata.

Indexes: `(source_type, source_id)` and effective time for statements/audit. Source fields link usage/top-up/refund/chargeback/correction without another hierarchy.

### `ledger_entries`

Composite primary key `(transaction_id, account_id)`. Columns: transaction FK restrict, account FK restrict, nonzero `amount_micros bigint`.

A deferred constraint trigger verifies the sum of entries for each touched transaction is exactly zero and that every account has the same currency. The ledger application inserts transaction and all entries in one database transaction; incomplete postings cannot commit.

### `topup_intents`

Columns: `id` PK, organization FK, positive `amount_micros`, status created/completed/failed/expired, nullable unique `stripe_session_id`, nullable unique `stripe_payment_id`, unique `(organization_id, idempotency_key)`, `created_at`, nullable `completed_at`.

State/timestamp consistency checks apply. Intent completion is not financial authority without the linked unique ledger business effect.

### `payment_events`

Primary key `provider_event_id text`; columns: constrained type, `object_id`, received time, nullable processed time, status received/processed/failed, nullable stable error code. No raw payload. Index unprocessed received order.

### `usage_records`

| Column | Type | Rule |
| --- | --- | --- |
| `id` | uuid | primary key |
| `request_id` | uuid | unique |
| `organization_id` | uuid | FK; channel traffic uses `channel_usage_records` rather than nullable tenant identity |
| `workspace_id` | uuid | composite tenant FK |
| `api_key_id` | uuid | composite tenant/workspace FK |
| `release_digest` | text | FK model release |
| `requested_model_id` | text | exact public string requested |
| `actual_target` | text | bounded canonical provider/model or owned release target; no private endpoint |
| `status` | text | reserved/settled/abandoned plus bounded terminal outcome mapping |
| `reserved_micros` | bigint | nonnegative |
| `sell_micros` | bigint nullable | nonnegative terminal sell |
| `buy_micros` | bigint nullable | nonnegative scope-supported cost evidence |
| `input_tokens` | bigint nullable | nonnegative |
| `cached_input_tokens` | bigint nullable | nonnegative and not above input where semantics require |
| `output_tokens` | bigint nullable | nonnegative |
| `attempts_json` | jsonb | bounded array validated by versioned schema; no payload/secret/private endpoint |
| `started_at` | timestamptz | required |
| `completed_at` | timestamptz nullable | terminal only |

Indexes support mandatory tenant/time/model/status queries: `(organization_id, workspace_id, started_at DESC, id)`, `(organization_id, request_id)`, and bounded model/status aggregates. Add partitioning or a rollup only after the measured query trigger.

Usable-output/cancellation evidence required by failed-request policy is encoded in the terminal attempt-summary schema and supplied by `UsageSettled`; it is not a second mutable usage table.

### `channel_usage_records`

This is the distribution counterpart to `usage_records`; a separate table keeps customer tenant columns non-nullable and prevents a generic principal union from entering every customer query.

| Column | Type | Rule |
| --- | --- | --- |
| `id` | uuid | primary key |
| `request_id` | uuid | unique |
| `channel_id` | uuid | FK distribution channel |
| `credential_id` | uuid | composite FK proving credential belongs to channel |
| `release_digest` | text | FK exact owned release |
| `external_model_id` | text | exact channel catalog identity requested |
| `status` | text | reserved/settled/abandoned plus bounded terminal outcome mapping |
| `reserved_micros` | bigint | nonnegative exposure hold |
| `sell_micros` | bigint nullable | nonnegative contractual receivable |
| `buy_micros` | bigint nullable | nonnegative scope-supported cost evidence |
| `input_tokens` | bigint nullable | nonnegative |
| `cached_input_tokens` | bigint nullable | nonnegative and semantically bounded |
| `output_tokens` | bigint nullable | nonnegative |
| `attempts_json` | jsonb | same bounded payload-free versioned schema as organization usage |
| `started_at` | timestamptz | required |
| `completed_at` | timestamptz nullable | terminal only |

Indexes: `(channel_id, started_at DESC, id)`, `(channel_id, request_id)`, and bounded statement/reconciliation scans. Channel traffic has no organization, workspace, API-key, customer trace or recommendation row unless a later signed data contract explicitly adds a separately reviewed feature.

## 4. Catalog and release

### `provider_endpoints`

Columns: `id` PK, constrained provider, region, base URL, typed `credential_ref`, status active/suspended, `updated_at`. Unique `(provider, region, base_url)`. Base URL is operator-only and never enters public errors/usage attempt JSON.

### `model_definitions`

Columns: `id` PK, unique `public_id`, kind direct/owned, nullable provider and upstream model ID valid only for direct, status draft/active/retired, created/updated times. Check enforces kind-specific fields.

### `model_releases`

Columns: digest PK, model FK, nullable bundle digest required for owned and absent for direct, closed `capabilities_json`, positive context/output limits, nonnegative integer input/output/cache prices, bounded nonnegative `max_pre_output_retries`, status draft/active/retired, created time, nullable activated time.

Release identity fields and ordered direct endpoint membership determine digest. A database trigger forbids updating identity/capability/price fields after insert; only valid status/activated transition may update. New semantics/prices create a new row.

### `release_endpoints`

Composite primary key `(release_digest, endpoint_id)`. Columns: release/endpoint FKs, nonnegative unique priority within release, positive weight. Direct releases require at least one membership before activation; owned releases require none. Ordered membership is part of digest verification.

### `model_aliases`

Primary key/FK `model_id`; stable active release FK, nullable canary active release FK, basis points 0..10000, positive generation, `updated_at`. Canary null requires zero basis points. Alias update locks row, verifies same model/capability policy and increments generation.

### `qualification_runs`

Columns: `id` PK, subject digest, closed `scope_json`, positive `policy_version`, result passed/failed, private report object key, nullable expiry, created time. Unique subject/scope digest/policy/run identity as defined by qualification command. A passed report is immutable and usable only for exact matching non-expired scope.

## 5. Traces and recommendations

### `traces`

Columns: `id` PK, unique request ID with tenant FKs, capture status, nullable opaque object key/digest/wrapped key/size, created time, nullable expiry/deleted time.

Checks enforce:

- captured state has object/digest/wrapped key/size;
- skipped/no-retention state has none;
- deleted state is never returned even if object fields remain during cleanup;
- expiry is after creation.

Indexes: tenant created time, expiry where not deleted and request lookup. Wrapped-key access is destroyed before object cleanup.

### `recommendations`

Columns: `id` PK, workspace FK, source model FK, candidate release FK, bounded closed `summary_json`, status pending/accepted/dismissed/expired, created/expiry times. Candidate must be qualified at creation. No automatic traffic pointer exists.

### `evaluations`

Columns: `id` PK, recommendation FK, mode replay/shadow/live_canary, status queued/running/completed/failed/cancelled, nonnegative budget, closed `authority_json`, closed `stop_conditions_json`, nullable closed `result_json`, created/completed times.

Authority/stop schemas are required before queue. Live canary still uses ordinary gateway admission and a separate evaluation cap.

## 6. Distribution

### `distribution_channels`

Columns: `id` PK, unique bounded name, status active/suspended, constrained data policy, nonnegative exposure limit, positive concurrency, positive catalog version, created/updated times.

### `channel_balances`

Primary key/FK channel; nonnegative-or-contract-valid outstanding micros, positive version and updated time. Rebuildable from channel-scoped ledger entries.

### `channel_credentials`

Columns: `id` PK, channel FK, unique prefix, digest, pepper version, active/revoked status, nullable expiry and created time. Same display-once/rotation rules as workspace keys. Last use is derived from channel usage when needed rather than persisted as a hot mutable field.

### `channel_catalog`

Composite primary key `(channel_id, external_model_id)`. Columns: release FK, nonnegative input/output/cache prices, active/suspended status and updated time. Catalog version increments with a transaction that changes rows.

### `channel_statements`

This table is absent until the signed OpenRouter contract requires statements. When enabled: ID PK, channel FK, non-overlapping contract-supplied period start/end, private object key and digest, draft/issued/reconciled/disputed status, nullable delta micros and created time. It is evidence, not a generic billing-period engine.

## 7. Owned capacity

### `capacity_sources`

Columns: `id` PK, constrained provider and compiled driver kind, region, typed config ref, active/suspended status, nonnegative hourly budget, created time. Unique provider/config/region identity. No dynamic plugin metadata.

### `capacity_targets`

Composite primary key `(release_digest, region, capacity_class)`. Columns: nonnegative minimum, maximum at least minimum, nonnegative hourly budget and updated time. Counts complete cells, not nodes. Release/topology/hardware qualification is validated before write.

### `allocations`

Columns: `id` PK, source FK, nullable provider allocation ID, release FK, desired state requested/ready/draining/released, observed state requested/provisioning/ready/draining/released/failed, positive lease epoch, nullable lease owner/expiry, nullable one-use bootstrap digest/expiry, nullable quoted hourly micros, created time, nullable stable error code, cleanup state pending/confirmed/uncertain.

Indexes: source/observed/lease expiry for claims, release/ready, cleanup uncertainty. Unique `(source_id, provider_allocation_id)` where present. Lease compare-and-set includes epoch. Desired/observed transitions are validated by domain state model.

### `allocation_members`

Composite primary key `(allocation_id, ordinal)`. Columns: constrained role coordinator/worker, nullable provider resource ID unique within source/provider scope, observed state, nullable one-use join-token digest/expiry, nullable joined time/last observed time, cleanup pending/confirmed/uncertain.

Exactly one coordinator ordinal exists; required member count/roles come from topology manifest and are checked before acquisition/readiness. Any uncertain member blocks allocation cleanup confirmation.

### `cells`

Columns: `id` PK, unique allocation FK, release FK, region, status enrolling/ready/draining/failed/released, capacity class, attestation digest, certificate identity serial, identity expiry, last observed time and nullable drain time.

PostgreSQL status is lifecycle evidence, not request-time health. Router memory is rebuilt from authenticated live connections.

## 8. Research

### `research_programs`

Columns: `id` PK, unique name, closed model-source/scope JSON, status active/paused/completed, nullable baseline/champion digests, nonnegative program budget and created/updated times.

### `research_hypotheses`

Columns: `id` PK, program FK, bounded claim text, scope digest, closed intervention/falsification JSON, integer priority, status proposed/active/falsified/supported/retired, created time. Ranked queue is a query, not stored state.

### `research_campaigns`

Columns: `id` PK, program FK, name, closed scope JSON, nonnegative budget, deadline, status draft/active/paused/completed/cancelled, created time. Campaign is the durable authority/budget envelope.

### `experiment_specs`

Columns: `id` PK, hypothesis FK, nullable campaign FK, source commit, closed inputs/metrics/stop JSON, nonnegative budget, positive timeout and created time. A canonical spec digest/unique identity is computed by application; rows are immutable.

### `experiment_runs`

Columns: `id` PK, spec FK, unique Temporal workflow ID, status queued/running/succeeded/falsified/failed/cancelled, nullable environment manifest digest/result object key, nullable started/completed times. Temporal event/activity history is not copied here.

### `evidence_reports`

Columns: `id` PK, program FK, scope digest, bounded conclusion, evidence class measured/analytical/vendor_reported/derived/inferred/synthetic, private report object key, status draft/reviewed/accepted/rejected, created time. Negative evidence uses the same model.

### `bundles`

Digest primary key; manifest object key, runtime image digest, nullable parent bundle FK, source run FK and created time. Bundle bytes are immutable; qualification/release status is not stored on this row.

### `bundle_qualifications`

Columns: `id` PK, bundle FK, positive policy version, status pending/passed/failed, report object key, nullable expiry, created/completed times. Exact scope is inside the canonical qualification report and mirrored by a digest/constraint in application logic; rows are immutable after terminal.

## 9. Operations

### `outbox`

Columns: `id` UUID PK, bounded `type`, positive schema version, closed typed `payload_json`, occurred/available times, nullable published time, nonnegative attempts and nullable stable error code.

Indexes: unpublished `(available_at, occurred_at)` and type/time for operator diagnosis. At-least-once publisher uses `FOR UPDATE SKIP LOCKED`; consumers dedupe on domain business identity. Outbox is not a second event store.

### `audit_records`

Columns: `id` UUID PK, nullable organization FK, actor kind user/deployment/operator/channel, actor ID, bounded action, resource kind/ID, result allowed/denied/succeeded/failed, occurred time.

No payload snapshot or generic metadata. Terms/privacy acceptance uses a versioned action/resource ID here rather than a speculative user-profile field. Index tenant/time, actor/time and resource/time.

## 10. Database roles and write ownership

| Role | Writes | Reads |
| --- | --- | --- |
| migration owner | schema only during migration | catalog |
| control API | tenancy/keys/top-up intents/payment events/catalog commands/audit/outbox | authorized product queries |
| financial | ledger/balances/usage/event receipts/outbox/audit | billing authority and reconciliation |
| intelligence | traces/recommendations/evaluations/audit | bounded usage/trace metadata |
| trace-access | audit only | one authorized trace row and membership |
| fleet planner/driver/enrollment | capacity target/allocation/member/cell/audit subset | exact fleet/release/artifact refs |
| research API | research tables/bundles/qualification/audit/outbox | research domain |
| evaluator | qualification report result through application command | exact bundle/evidence refs |
| gateway/router/cell/MCP/browser | none | none directly |

Row-level security may be defense in depth, but server predicates and role grants are mandatory. No broad application role owns every table.

## 11. Migration and invariant tests

Every migration packet proves:

- empty install and upgrade from prior committed schema fixture;
- rollback means application compatibility/forward fix, not destructive production down migration;
- constraint names and expected violation codes are stable where application maps conflicts;
- all tenant queries use required composite indexes under production-shaped fixtures;
- ledger deferred-balance trigger and immutable-release/spec/bundle protections work;
- no cascade can remove ledger, payment, usage, qualification or audit evidence accidentally;
- organization deletion worker, not generic cascade, owns pseudonymization/purge order;
- JSON schemas, generated repository types and Protobuf event fields agree;
- a field/table with no concrete command/query/test is rejected from review.
