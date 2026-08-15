# Proposed product and inference data models

- status: proposed for founder review
- date: 2026-08-15
- architecture: [ADR-0010](../decisions/0010-direct-inference-and-openrouter.md)
- launch plan: [Kimi K3 provider launch](KIMI_K3_PROVIDER_LAUNCH_PLAN.md)

This document proposes the complete seed data model for the exact-model product. It is not yet a migration contract. Review comments should be resolved before it replaces the older [physical data model](DATA_MODEL.md).

The proposal removes the old routing, fleet, trace, recommendation, research, alias and third-party-provider models.

## Decisions to review first

1. Represent OpenRouter as an internal `distribution_channel` organization with its own workspace and API key, instead of separate channel credential, catalog, balance and usage tables.
   this makes sense
2. Keep the global hosted-model catalog, pricing and availability in PostgreSQL. Keep only environment-specific deployment configuration in Git.
3. Launch with zero prompt/response retention and no trace tables. Add configurable retention only with a later product decision.

we can start with no trace retention

## Global conventions

- Application IDs are UUIDv7. Exact public model IDs are stable bounded text identifiers.
- PostgreSQL timestamps are `timestamptz` in UTC; ClickHouse timestamps are `DateTime64` in UTC.
- Money fields such as `balance`, `amount`, `charge` and `reserved_amount` are signed `bigint` micro-USD unless explicitly constrained nonnegative.
- Token prices are nonnegative `bigint` nano-USD per token, which supports sub-micro-USD rates.
- Enums are constrained `text`, not PostgreSQL enum types.
- API keys contain 256 random bits and are stored only as SHA-256 `bytea` digests; raw secrets are shown once and never persisted.
- Mutable PostgreSQL records have `updated_at`; immutable PostgreSQL and ClickHouse records do not.
- No generic `metadata`, arbitrary tags or universal soft-delete fields.
- JSON is allowed only where a versioned Zod schema defines a closed shape.
- Every tenant query includes `organization_id` and, where applicable, `workspace_id`.
- The TypeScript application owns PostgreSQL and queries ClickHouse for product analytics. Rust consumes serving projections and emits versioned generation events; it does not contain product repositories.
- Valkey is the only synchronous internal state dependency for every inference request, including OpenRouter and direct API keys. PostgreSQL and ClickHouse are never queried on the inference path.

# PostgreSQL models

## Authentication

The first four tables are generated and owned by Better Auth. We map its logical camel-case fields to snake-case PostgreSQL columns and pin the generated schema in migrations.

### 1. `users`

| Field            | Type        | Null | Rules                                 |
| ---------------- | ----------- | ---- | ------------------------------------- |
| `id`             | uuid        | no   | Primary key                           |
| `name`           | text        | no   | Bounded display name                  |
| `email`          | text        | no   | Normalized; unique case-insensitively |
| `email_verified` | boolean     | no   | Default false                         |
| `image_url`      | text        | yes  | Profile image URL                     |
| `created_at`     | timestamptz | no   | Creation time                         |
| `updated_at`     | timestamptz | no   | Last mutation time                    |

Do not add a global application role. Authorization belongs to organization membership. Active organization members can access every workspace in their organization.

### 2. `sessions`

| Field        | Type        | Null | Rules                       |
| ------------ | ----------- | ---- | --------------------------- |
| `id`         | uuid        | no   | Primary key                 |
| `user_id`    | uuid        | no   | FK `users.id`               |
| `token`      | text        | no   | Unique; Better Auth-managed |
| `expires_at` | timestamptz | no   | Session expiry              |
| `ip_address` | inet        | yes  | Better Auth-managed         |
| `user_agent` | text        | yes  | Bounded                     |
| `created_at` | timestamptz | no   | Creation time               |
| `updated_at` | timestamptz | no   | Last mutation time          |

### 3. `accounts`

| Field                      | Type        | Null | Rules                     |
| -------------------------- | ----------- | ---- | ------------------------- |
| `id`                       | uuid        | no   | Primary key               |
| `user_id`                  | uuid        | no   | FK `users.id`             |
| `account_id`               | text        | no   | Provider account ID       |
| `provider_id`              | text        | no   | Initially `credential`    |
| `access_token`             | text        | yes  | OAuth only                |
| `refresh_token`            | text        | yes  | OAuth only                |
| `id_token`                 | text        | yes  | OAuth only                |
| `access_token_expires_at`  | timestamptz | yes  | OAuth only                |
| `refresh_token_expires_at` | timestamptz | yes  | OAuth only                |
| `scope`                    | text        | yes  | OAuth only                |
| `password`                 | text        | yes  | Better Auth password hash |
| `created_at`               | timestamptz | no   | Creation time             |
| `updated_at`               | timestamptz | no   | Last mutation time        |

Email/password is the launch path, so the OAuth fields are initially null.

### 4. `verifications`

| Field        | Type        | Null | Rules                                  |
| ------------ | ----------- | ---- | -------------------------------------- |
| `id`         | uuid        | no   | Primary key                            |
| `identifier` | text        | no   | Email/purpose identity                 |
| `value`      | text        | no   | Better Auth-managed verification value |
| `expires_at` | timestamptz | no   | Expiry                                 |
| `created_at` | timestamptz | no   | Creation time                          |
| `updated_at` | timestamptz | no   | Last mutation time                     |

## Organizations and workspaces

### 5. `organizations`

Direct customers and distribution channels such as OpenRouter use the same organization boundary.

| Field        | Type        | Null | Rules                              |
| ------------ | ----------- | ---- | ---------------------------------- |
| `id`         | uuid        | no   | Primary key                        |
| `kind`       | text        | no   | `customer`, `distribution_channel` |
| `name`       | text        | no   | Bounded display name               |
| `status`     | text        | no   | `active`, `suspended`              |
| `created_at` | timestamptz | no   | Creation time                      |
| `updated_at` | timestamptz | no   | Last mutation time                 |

OpenRouter is an internal `distribution_channel` organization and is not visible in the customer organization chooser.

### 6. `organization_members`

Primary key: `(organization_id, user_id)`.

| Field             | Type        | Null | Rules                                 |
| ----------------- | ----------- | ---- | ------------------------------------- |
| `organization_id` | uuid        | no   | FK `organizations.id`                 |
| `user_id`         | uuid        | no   | FK `users.id`                         |
| `role`            | text        | no   | `owner`, `admin`, `billing`, `member` |
| `status`          | text        | no   | `active`, `suspended`                 |
| `created_at`      | timestamptz | no   | Creation time                         |
| `updated_at`      | timestamptz | no   | Last mutation time                    |

Customer organizations must retain at least one active owner. Distribution-channel organizations do not require human members.

### 7. `invitations`

| Field                | Type        | Null | Rules                                 |
| -------------------- | ----------- | ---- | ------------------------------------- |
| `id`                 | uuid        | no   | Primary key                           |
| `organization_id`    | uuid        | no   | FK `organizations.id`                 |
| `email`              | text        | no   | Normalized lowercase                  |
| `role`               | text        | no   | Offered organization role             |
| `token_digest`       | bytea       | no   | Unique; raw token never stored        |
| `expires_at`         | timestamptz | no   | Expiry                                |
| `accepted_at`        | timestamptz | yes  | Mutually exclusive with `revoked_at`  |
| `revoked_at`         | timestamptz | yes  | Mutually exclusive with `accepted_at` |
| `created_by`         | uuid        | no   | FK `users.id`                         |
| `created_at`         | timestamptz | no   | Creation time                         |
| `updated_at`         | timestamptz | no   | Last mutation time                    |

There is at most one pending invitation per organization and normalized email.

### 8. `workspaces`

| Field             | Type        | Null | Rules                                                   |
| ----------------- | ----------- | ---- | ------------------------------------------------------- |
| `id`              | uuid        | no   | Primary key                                             |
| `organization_id` | uuid        | no   | FK `organizations.id`                                   |
| `name`            | text        | no   | Unique per organization, case-insensitively             |
| `is_default`      | boolean     | no   | Exactly one default workspace per organization          |
| `archived_at`     | timestamptz | yes  | Null while usable; archived workspaces cannot serve API |
| `created_at`      | timestamptz | no   | Creation time                                           |
| `updated_at`      | timestamptz | no   | Last mutation time                                      |

A workspace is a policy and cost-attribution boundary, not an authorization boundary. Active organization members can access every workspace in their organization. Each organization is created with one default workspace; the product can hide workspace selection while only that workspace exists.

At launch, workspaces group API keys and usage only. Every unarchived workspace can access every active hosted model, with no workspace spend, rate or concurrency limits. Future model allowlists and per-model limits belong in a workspace-model policy table rather than on API keys. Launch behavior is zero retention for all inference payloads.

### 9. `api_keys`

Used by direct customers and OpenRouter.

| Field                  | Type        | Null | Rules                                           |
| ---------------------- | ----------- | ---- | ----------------------------------------------- |
| `id`                   | uuid        | no   | Primary key                                     |
| `organization_id`      | uuid        | no   | FK `organizations.id`                           |
| `workspace_id`         | uuid        | no   | FK `workspaces.id`; composite tenant constraint |
| `name`                 | text        | no   | Bounded display name                            |
| `digest`               | bytea       | no   | Unique SHA-256 digest of the canonical raw key  |
| `expires_at`           | timestamptz | yes  | Optional expiry                                 |
| `revoked_at`           | timestamptz | yes  | Irreversible manual revocation                  |
| `created_by`           | uuid        | yes  | FK `users.id`; null for system-created channels |
| `created_at`           | timestamptz | no   | Creation time                                   |
| `updated_at`           | timestamptz | no   | Last mutation time                              |

The raw format is `grad_<32 random bytes encoded as base64url>`. Authentication computes SHA-256 over that complete canonical string and looks up the unique digest. High-entropy keys do not need a pepper or pepper rotation. Do not store the raw key, a display prefix, last four characters or `last_used_at`; the key name and creation time identify it in the product, and last use is derived from usage. A key is valid only when `revoked_at IS NULL` and `expires_at` is either null or in the future. Rotation creates a new key and sets `revoked_at` on the old one.

## Model catalog

### 10. `models`

Global hosted-model catalog. It is not organization-scoped. The primary key is the immutable human-readable model identifier used in direct requests and returned to OpenRouter, for example `moonshotai/kimi-k3`.

| Field        | Type        | Null | Rules                                         |
| ------------ | ----------- | ---- | --------------------------------------------- |
| `id`         | text        | no   | Primary key; exact immutable public model ID  |
| `name`       | text        | no   | Bounded customer-facing name                  |
| `status`     | text        | no   | `available`, `unavailable`, `retired`         |
| `properties` | jsonb       | no   | Closed Zod `ModelProperties` document         |
| `created_at` | timestamptz | no   | Creation time                                 |
| `updated_at` | timestamptz | no   | Last mutation time                            |

`ModelProperties` follows the structure of the OpenRouter provider model document where practical, while retaining internal artifact identity and exact integer money:

| Property                 | Type                   | Rules                                                        |
| ------------------------ | ---------------------- | ------------------------------------------------------------ |
| `description`            | string                 | Bounded customer-facing description                          |
| `released_at`            | timestamp nullable     | Upstream model release time                                  |
| `hugging_face_id`        | string nullable        | Upstream repository identity                                 |
| `artifact_revision`      | string                 | Immutable model commit or digest                             |
| `tokenizer_id`           | string                 | Tokenizer repository identity                                |
| `tokenizer_revision`     | string                 | Immutable tokenizer commit or digest                         |
| `quantization`           | string nullable        | OpenRouter-compatible quantization                           |
| `tokenizer`              | string nullable        | Tokenizer family exposed to OpenRouter                       |
| `input_modalities`       | input-modality[]       | Nonempty typed modality documents                            |
| `output_modalities`      | output-modality[]      | Nonempty typed modality documents                            |
| `pricing`                | pricing-entry[]        | Request-scoped prices only                                   |
| `capacity`               | capacity-entry[]       | Advertised request-scoped capacity                           |
| `passthrough_parameters` | descriptor map         | Closed request-scoped passthrough parameters                 |
| `deprecation_at`         | timestamp nullable     | Optional scheduled retirement                                |
| `is_free`                | boolean                | Default false                                                |
| `discount_to_user`       | decimal                | Below one; default zero                                      |
| `openrouter`             | object nullable        | Optional canonical `slug` when it differs from this row's ID |

Each input/output modality owns its typed constraints, supported parameters, modality-scoped pricing and advertised capacity. Capability descriptors use the OpenRouter-compatible range, integer, boolean, enum, array, object or unknown grammar. Internal prices use nonnegative integer `cost_nano_usd`; the provider response converts them to OpenRouter's decimal-string `cost_usd` representation. This is a closed domain document, not arbitrary metadata.

The TypeScript control application owns model changes. After a price or status mutation commits, it reloads the current row from the PostgreSQL primary and synchronously projects it to Valkey before reporting success. A capacity monitor or operator may set `status = 'unavailable'` when qualified GPU capacity is unavailable and restore `available` when service is ready. Rust receives the current model snapshot through Valkey and rejects unavailable, retired or unknown model IDs before GPU work.

## Billing

### 11. `billing_accounts`

One record per organization.

| Field                | Type        | Null | Rules                                      |
| -------------------- | ----------- | ---- | ------------------------------------------ |
| `organization_id`    | uuid        | no   | PK and FK `organizations.id`               |
| `mode`               | text        | no   | `prepaid`, `invoiced`                      |
| `stripe_customer_id` | text        | yes  | Unique when present                        |
| `balance`            | bigint      | no   | Remaining spendable micro-USD              |
| `created_at`         | timestamptz | no   | Creation time                              |
| `updated_at`         | timestamptz | no   | Last mutation time                         |

PostgreSQL owns the durable posted balance, while Valkey owns the synchronous available balance including live reservations and settlements not yet posted to PostgreSQL. Direct inference never reads this row. Direct prepaid customers increase balance through Stripe top-ups. OpenRouter uses `invoiced` mode and an approved credit limit; its usage is reconciled separately from customer prepaid balances. A chargeback or adjustment may make the durable balance negative, and the corresponding Valkey update then blocks new direct admission.

### 12. `balance_transactions`

Immutable history of durable balance movements. This is a customer wallet ledger, not a general double-entry accounting system.

| Field              | Type        | Null | Rules                                                                       |
| ------------------ | ----------- | ---- | --------------------------------------------------------------------------- |
| `id`               | uuid        | no   | Primary key                                                                 |
| `organization_id`  | uuid        | no   | FK `organizations.id`                                                       |
| `type`             | text        | no   | `topup`, `usage`, `refund`, `chargeback`, `credit`, `payment`, `adjustment` |
| `amount`           | bigint      | no   | Signed, nonzero balance change                                              |
| `balance_after`    | bigint      | no   | Account balance after this movement                                         |
| `source_type`      | text        | no   | Closed source allowlist                                                     |
| `source_id`        | text        | no   | Source object or settlement-batch identity                                  |
| `period_start`     | timestamptz | yes  | Aggregated usage only                                                       |
| `period_end`       | timestamptz | yes  | Aggregated usage only; after `period_start`                                 |
| `generation_count` | bigint      | yes  | Positive for aggregated usage                                               |
| `created_by`       | uuid        | yes  | FK `users.id`; manual credits and adjustments only                          |
| `created_at`       | timestamptz | no   | Movement time                                                               |

`(source_type, source_id)` is unique and is the idempotency boundary. Initial source types are `stripe_checkout_session`, `stripe_refund`, `stripe_dispute`, `generation`, `generation_settlement_batch`, `openrouter_payment` and `operator`.

A balance mutation locks the account row, inserts the immutable movement and updates `billing_accounts.balance` in one PostgreSQL transaction. Positive amounts add funds and negative amounts consume funds. Before usage aggregation is needed, one generation may produce one `generation` source movement. At high volume, the billing consumer instead posts one `generation_settlement_batch` movement per organization and bounded time window; individual generation charges remain queryable in ClickHouse and must reconcile exactly to the batch amount.

Stripe owns pending, failed and abandoned Checkout Sessions. The application creates a server-priced Checkout Session carrying the organization identity. A signed successful-payment webhook inserts a `topup` movement keyed by the Checkout Session ID. The handler returns success only after the PostgreSQL transaction commits; Stripe retries failures, and the source uniqueness constraint makes duplicate delivery harmless. Refund and dispute webhooks use their Stripe object IDs in the same way. There is no local top-up-intent or webhook-inbox table.

## PostgreSQL-to-Valkey synchronization

There is no projection queue or outbox table. These projections are low-volume, level-triggered copies of current PostgreSQL state. After an ordinary control-plane mutation commits, the TypeScript application reloads the latest authoritative row from the PostgreSQL primary, writes its stable Valkey key and reports success only after Valkey acknowledges. If projection fails, the operation returns `503`; retrying projects the already-committed current state.

Restrictive changes fail closed. API-key revocation, organization suspension, model unavailability or price changes, and negative balance adjustments first block the affected Valkey scope, then commit PostgreSQL, then publish the final state and reopen only when appropriate. A failure leaves that scope blocked. Permissive changes such as key creation, model creation and positive top-ups commit PostgreSQL first, so a projection failure withholds access or credit rather than granting too much.

A background role inside the existing TypeScript `control` deployment periodically reconciles PostgreSQL with Valkey and performs a complete rebuild at startup or after Valkey loss. It always reloads current rows instead of replaying mutation payloads, so a delayed operation cannot overwrite newer state. Each logical object has one stable Valkey key. Rebuilds close all admission, drain and post terminal settlement events, resolve or abandon live reservations, rewrite projections in place and then reopen.

PostgreSQL-originated money changes are reconciled from immutable `balance_transactions` and applied to Valkey idempotently using the transaction ID. The reconciler never overwrites an operational Valkey balance containing live reservations or unposted settlements. Valkey-originated usage postings do not echo back into Valkey.

The reconciler exports its last-success time, failures and mismatches as metrics. Missing or unavailable required projection state rejects every request. Do not add CDC, Debezium, Kafka, a projection queue or a standalone projector at launch.

# Git-owned deployment configuration

Environment-specific infrastructure and runtime configuration is Zod-authored and committed to Git. Customer-facing model metadata, prices and availability live in PostgreSQL.

## 13. `ModelDeploymentManifest`

Environment-specific serving configuration.

| Field                          | Type    | Rules                                        |
| ------------------------------ | ------- | -------------------------------------------- |
| `schema_version`               | string  | Manifest schema version                      |
| `id`                           | string  | Deployment identity                          |
| `model_id`                     | string  | Exact ID of the PostgreSQL `models` row       |
| `environment`                  | string  | `local`, `staging`, `production`             |
| `provider`                     | string  | Selected GPU provider                        |
| `provider_region`              | string  | Provider region                              |
| `country_code`                 | string  | ISO 3166-1 alpha-2                           |
| `cluster_id`                   | string  | Non-secret cluster identity                  |
| `namespace`                    | string  | Kubernetes namespace                         |
| `service_url`                  | string  | Private or restricted SGLang URL             |
| `auth_secret_ref`              | string  | Secret reference, never secret value         |
| `sglang_image_digest`          | string  | Immutable OCI digest                         |
| `gpu_instance_type`            | string  | Initially `b300-8x`                          |
| `gpu_count`                    | integer | Initially 8                                  |
| `model_path`                   | string  | Pinned model path                            |
| `tensor_parallel_size`         | integer | Initially 8                                  |
| `memory_fraction_static`       | decimal | Greater than zero and below one              |
| `reasoning_parser`             | string  | Initially `kimi_k3`                          |
| `tool_call_parser`             | string  | Initially `kimi_k3`                          |
| `metrics_enabled`              | boolean | Required true in production                  |
| `prompt_tokens_per_minute`     | integer | Measured nonnegative capacity                |
| `completion_tokens_per_minute` | integer | Measured nonnegative capacity                |
| `max_concurrency`              | integer | Measured positive capacity                   |
| `zdr`                          | boolean | Zero-retention declaration                   |
| `hipaa`                        | boolean | Initially false                              |

The served release digest covers immutable model artifact identity and canonical deployment runtime configuration. Mutable customer prices and availability are excluded from this digest and are projected separately from PostgreSQL.

# ClickHouse models

ClickHouse Cloud on AWS stores immutable terminal generation records for customer history, usage analytics, spend analysis and inference performance. It is a replayable query projection, not the authority for balances, credentials, reservations or financial postings.

## 14. `generations`

One row per terminal model invocation. Direct and OpenRouter traffic share this table because both use the same organization, workspace and API-key dimensions.

| Field                     | ClickHouse type               | Rules                                               |
| ------------------------- | ----------------------------- | --------------------------------------------------- |
| `id`                      | UUID                          | Logical unique generation ID; UUIDv7                |
| `event_id`                | UUID                          | `GenerationSettled` event identity                  |
| `event_schema_version`    | UInt16                        | Positive                                            |
| `external_id`             | Nullable(String)              | OpenRouter or direct-client correlation             |
| `organization_id`         | UUID                          | PostgreSQL organization identity                    |
| `workspace_id`            | UUID                          | PostgreSQL workspace identity                       |
| `api_key_id`              | UUID                          | PostgreSQL API-key identity                         |
| `model_id`                | LowCardinality(String)        | Exact requested hosted-model ID                     |
| `served_release_digest`   | String                        | Immutable served release                            |
| `status`                  | LowCardinality(String)        | `succeeded`, `failed`, `cancelled`, `abandoned`     |
| `streamed`                | Bool                          | Whether SSE was requested                           |
| `reserved_amount`         | Int64                         | Nonnegative                                         |
| `charge`                  | Int64                         | Nonnegative customer charge                         |
| `input_tokens`            | UInt64                        | Actual nonnegative count                            |
| `cached_input_tokens`     | UInt64                        | Actual nonnegative count                            |
| `output_tokens`           | UInt64                        | Actual nonnegative count                            |
| `reasoning_tokens`        | UInt64                        | Actual nonnegative count                            |
| `finish_reason`           | LowCardinality(Nullable(String)) | Stable allowlist                                 |
| `error_code`              | LowCardinality(Nullable(String)) | Stable payload-free code                         |
| `usable_output_delivered` | Bool                          | Required terminal evidence                          |
| `cancellation_owner`      | LowCardinality(Nullable(String)) | `client`, `server`, `runtime`                    |
| `received_at`             | DateTime64(6, 'UTC')          | Accepted request time                               |
| `started_at`              | Nullable(DateTime64(6, 'UTC')) | Runtime start                                      |
| `first_token_at`          | Nullable(DateTime64(6, 'UTC')) | First usable output                                |
| `completed_at`            | DateTime64(6, 'UTC')          | Terminal time and partition timestamp               |
| `ingested_at`             | DateTime64(6, 'UTC')          | ClickHouse ingestion time                           |

Use an append-only `MergeTree`, partitioned by `toYYYYMM(completed_at)` and initially ordered by `(organization_id, workspace_id, completed_at, id)`. UUIDv7 allows a point lookup to derive the likely time partition from the generation ID. Add a projection for another access pattern only after measurements justify it.

The ingestion consumer batches `GenerationSettled` events. Retries use a deterministic insert-deduplication token derived from the source stream partition and offset range, and the consumer advances its durable checkpoint only after ClickHouse acknowledges the batch. Do not use `ReplacingMergeTree`, lifecycle updates or `FINAL` queries for the launch schema.

Do not store prompts, completions, arbitrary request JSON, credentials, private runtime URLs or attempt arrays. The seed has one exact runtime target and no fallback. Detailed retention and S3 archival are configured by explicit policy; no billing evidence is silently deleted before that policy is approved.

# Inference event contracts

These versioned closed schemas decouple Rust inference from ClickHouse and PostgreSQL. Atomic Valkey reservation and settlement operations append them to a dedicated Valkey Stream; no separate queue is required at launch. ClickHouse and PostgreSQL billing consumers must be independently replayable from that stream and acknowledge entries only after their destination commits.

## 15. `GenerationReserved`

Introduced with Valkey reservations for direct paid traffic.

| Field                   | Type      |
| ----------------------- | --------- |
| `event_id`              | uuid      |
| `schema_version`        | integer   |
| `generation_id`         | uuid      |
| `request_digest`        | bytes     |
| `organization_id`       | uuid      |
| `workspace_id`          | uuid      |
| `api_key_id`            | uuid      |
| `model_id`              | string    |
| `served_release_digest` | string    |
| `reserved_amount`       | bigint    |
| `received_at`           | timestamp |
| `lease_expires_at`      | timestamp |

## 16. `GenerationSettled`

The canonical terminal-generation event. It contains every source field required to insert the ClickHouse generation row except the consumer-generated `ingested_at`.

| Field                     | Type                                |
| ------------------------- | ----------------------------------- |
| `event_id`                | uuid                                |
| `schema_version`          | integer                             |
| `generation_id`           | uuid                                |
| `external_id`             | string nullable                     |
| `organization_id`         | uuid                                |
| `workspace_id`            | uuid                                |
| `api_key_id`              | uuid                                |
| `model_id`                | string                              |
| `served_release_digest`   | string                              |
| `status`                  | `succeeded`, `failed`, `cancelled`, `abandoned` |
| `streamed`                | boolean                             |
| `reserved_amount`         | bigint                              |
| `charge`                  | bigint                              |
| `input_tokens`            | bigint                              |
| `cached_input_tokens`     | bigint                              |
| `output_tokens`           | bigint                              |
| `reasoning_tokens`        | bigint                              |
| `finish_reason`           | string nullable                     |
| `error_code`              | string nullable                     |
| `usable_output_delivered` | boolean                             |
| `cancellation_owner`      | `client`, `server`, `runtime`, null |
| `received_at`             | timestamp                           |
| `started_at`              | timestamp nullable                  |
| `first_token_at`          | timestamp nullable                  |
| `completed_at`            | timestamp                           |

# Valkey hot-path models

These models exist before any inference traffic is enabled. PostgreSQL projects OpenRouter and direct credentials, organization/workspace state, billing state and serving policy into Valkey. Every request performs authentication, admission, reservation and settlement through atomic Valkey operations. The paths differ only in billing mode: direct customers consume prepaid balance, while OpenRouter consumes invoiced credit exposure.

## 17. `AccountSnapshot`

| Field                 | Type                               |
| --------------------- | ---------------------------------- |
| `organization_id`     | uuid                               |
| `organization_kind`   | `customer`, `distribution_channel` |
| `organization_status` | organization status                |
| `billing_mode`        | `prepaid`, `invoiced`              |
| `balance`             | bigint                             |

## 18. `WorkspaceSnapshot`

| Field             | Type               |
| ----------------- | ------------------ |
| `organization_id` | uuid               |
| `workspace_id`    | uuid               |
| `archived_at`     | timestamp nullable |

## 19. `CredentialSnapshot`

Valkey key: `credential:<hex SHA-256 digest>`. The digest is the lookup key and is not duplicated in the value.

| Field             | Type               |
| ----------------- | ------------------ |
| `api_key_id`      | uuid               |
| `organization_id` | uuid               |
| `workspace_id`    | uuid               |
| `expires_at`      | timestamp nullable |
| `revoked_at`      | timestamp nullable |

## 20. `ModelSnapshot`

Valkey key: `model:<id>`.

| Field        | Type              |
| ------------ | ----------------- |
| `id`         | string            |
| `name`       | string            |
| `status`     | model status      |
| `properties` | `ModelProperties` |

This directly mirrors the serving-relevant PostgreSQL `models` row. The catalog is small, so retaining one shared model shape is simpler than maintaining a second flattened projection. Rust combines it with the locally loaded `ModelDeploymentManifest`; the deployment manifest supplies the target, measured capacity, datacenter/compliance declarations and served release digest. The model snapshot supplies customer-visible identity, capabilities, advertised capacity, prices and availability.

## 21. `Reservation`

| Field                   | Type                             |
| ----------------------- | -------------------------------- |
| `generation_id`         | uuid                             |
| `request_digest`        | bytes                            |
| `organization_id`       | uuid                             |
| `workspace_id`          | uuid                             |
| `api_key_id`            | uuid                             |
| `model_id`              | string                           |
| `served_release_digest` | string                           |
| `reserved_amount`       | bigint                           |
| `status`                | `active`, `settled`, `abandoned` |
| `received_at`           | timestamp                        |
| `lease_expires_at`      | timestamp                        |
| `terminal_event_id`     | uuid nullable                    |
| `charge`                | bigint nullable                  |
| `updated_at`            | timestamp                        |

# Explicitly excluded models

The following existed in older plans and are not part of this proposal:

- `provider_endpoints`
- `model_definitions`
- `model_releases`
- `release_endpoints`
- `model_aliases`
- `qualification_runs`
- `distribution_channels`
- `channel_credentials`
- `channel_catalog`
- `channel_usage_records`
- `channel_statements`
- `ledger_accounts`
- `ledger_transactions`
- `ledger_entries`
- `topup_intents`
- `payment_events`
- `usage_records`
- `idempotency_records`
- `outbox_events`
- `audit_events`
- `organization_deletions`
- `workspace_members`
- `workspace_models`
- `traces`
- `recommendations`
- `evaluations`
- `capacity_sources`
- `capacity_targets`
- `allocations`
- `allocation_members`
- `cells`
- all research program, campaign and experiment tables
- a PostgreSQL deployment or fleet registry

# Review checklist

- [ ] Approve or reject unified organization treatment for OpenRouter.
- [ ] Review the PostgreSQL global model catalog and Git-owned deployment boundary.
- [ ] Approve or reject universal zero retention at launch.
- [ ] Review organization roles and the workspace policy boundary.
- [ ] Review prepaid versus invoiced billing accounts and balance transactions.
- [ ] Review nano-USD token pricing and micro-USD totals.
- [ ] Review the ClickHouse generation schema, ordering key and retention policy.
- [ ] Review the Valkey Stream generation-event transport and consumer acknowledgement rules.
- [ ] Confirm generation fields retain no prompts or responses.
- [ ] Review PostgreSQL-to-Valkey projection, rebuild and propagation-SLO rules.
- [ ] Review Valkey snapshot and reservation fields.
- [ ] Confirm excluded models should remain excluded.
