# Data model

- status: current implementation authority
- date: 2026-08-15
- architecture: [ARCHITECTURE.md](ARCHITECTURE.md)
- launch plan: [Kimi K3 provider launch](KIMI_K3_PROVIDER_LAUNCH_PLAN.md)

This is the canonical seed data model for the exact-model product. Database
migrations, runtime schemas and API contracts must preserve the authorities,
invariants and boundaries defined here. A migration may add implementation
details such as indexes and constraint names, but it must not introduce a new
domain model or change an accepted invariant without first updating this
document.

The model deliberately excludes the old routing, fleet, trace, recommendation,
research, alias and third-party-provider concepts.

## Accepted launch decisions

- OpenRouter is an internal `distribution_channel` organization with its own
  workspace and API key. It does not need separate channel credential, catalog,
  balance or usage tables.
- PostgreSQL owns the global hosted-model catalog, pricing and availability.
  Git owns only environment-specific deployment configuration.
- The launch has universal zero prompt/response retention and no trace tables.
  Configurable retention requires a later explicit product decision.
- Organization membership is the human authorization boundary. Workspaces are
  policy and cost-attribution boundaries available to all active members.
- Prepaid and invoiced organizations share one balance, admission and settlement
  design. All internal monetary values use integer nano-USD.

## Global conventions

- Application IDs are UUIDv7. Exact public model IDs are stable bounded text identifiers.
- PostgreSQL timestamps are `timestamptz` in UTC; ClickHouse timestamps are `DateTime64` in UTC.
- Every internal monetary value and unit price is an integer nano-USD. Money field names omit the unit suffix: use `balance`, `amount`, `balance_after`, `charge`, `unit_price` and `cost` rather than unit-suffixed alternatives.
- Monetary storage uses signed `bigint`/`Int64` unless explicitly constrained nonnegative. Floating-point arithmetic is forbidden; calculations use checked integer intermediates before conversion to the stored range.
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

| Field             | Type        | Null | Rules                                 |
| ----------------- | ----------- | ---- | ------------------------------------- |
| `id`              | uuid        | no   | Primary key                           |
| `organization_id` | uuid        | no   | FK `organizations.id`                 |
| `email`           | text        | no   | Normalized lowercase                  |
| `role`            | text        | no   | Offered organization role             |
| `token_digest`    | bytea       | no   | Unique; raw token never stored        |
| `expires_at`      | timestamptz | no   | Expiry                                |
| `accepted_at`     | timestamptz | yes  | Mutually exclusive with `revoked_at`  |
| `revoked_at`      | timestamptz | yes  | Mutually exclusive with `accepted_at` |
| `created_by`      | uuid        | no   | FK `users.id`                         |
| `created_at`      | timestamptz | no   | Creation time                         |
| `updated_at`      | timestamptz | no   | Last mutation time                    |

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

In addition to the primary key, `workspaces` has a unique `(organization_id, id)` constraint. `api_keys(organization_id, workspace_id)` references that composite key, so PostgreSQL enforces that an API key and its workspace belong to the same organization rather than relying only on application checks.

A workspace is a policy and cost-attribution boundary, not an authorization boundary. Active organization members can access every workspace in their organization. Each organization is created with one default workspace; the product can hide workspace selection while only that workspace exists.

At launch, workspaces group API keys and usage only. Every unarchived workspace can access every active hosted model, with no workspace spend, rate or concurrency limits. Future model allowlists and per-model limits belong in a workspace-model policy table rather than on API keys. Launch behavior is zero retention for all inference payloads.

### 9. `api_keys`

Used by direct customers and OpenRouter.

| Field             | Type        | Null | Rules                                                                     |
| ----------------- | ----------- | ---- | ------------------------------------------------------------------------- |
| `id`              | uuid        | no   | Primary key                                                               |
| `organization_id` | uuid        | no   | FK `organizations.id`                                                     |
| `workspace_id`    | uuid        | no   | With `organization_id`, composite FK to `workspaces(organization_id, id)` |
| `name`            | text        | no   | Bounded display name                                                      |
| `digest`          | bytea       | no   | Unique SHA-256 digest of the canonical raw key                            |
| `expires_at`      | timestamptz | yes  | Optional expiry                                                           |
| `revoked_at`      | timestamptz | yes  | Irreversible manual revocation                                            |
| `created_by`      | uuid        | yes  | FK `users.id`; null for system-created channels                           |
| `created_at`      | timestamptz | no   | Creation time                                                             |
| `updated_at`      | timestamptz | no   | Last mutation time                                                        |

The raw format is `grad_<32 random bytes encoded as base64url>`. Authentication computes SHA-256 over that complete canonical string and looks up the unique digest. High-entropy keys do not need a pepper or pepper rotation. Do not store the raw key, a display prefix, last four characters or `last_used_at`; the key name and creation time identify it in the product, and last use is derived from usage. A key is valid only when `revoked_at IS NULL` and `expires_at` is either null or in the future. Rotation creates a new key and sets `revoked_at` on the old one.

## Model catalog

### 10. `models`

Global hosted-model catalog. It is not organization-scoped. The primary key is the immutable human-readable model identifier used in direct requests and returned to OpenRouter, for example `moonshotai/kimi-k3`.

| Field        | Type        | Null | Rules                                        |
| ------------ | ----------- | ---- | -------------------------------------------- |
| `id`         | text        | no   | Primary key; exact immutable public model ID |
| `name`       | text        | no   | Bounded customer-facing name                 |
| `status`     | text        | no   | `available`, `unavailable`, `retired`        |
| `properties` | jsonb       | no   | Closed Zod `ModelProperties` document        |
| `created_at` | timestamptz | no   | Creation time                                |
| `updated_at` | timestamptz | no   | Last mutation time                           |

`ModelProperties` follows the structure of the OpenRouter provider model document where practical, while retaining public source metadata and exact integer money. Exact deployed model and tokenizer artifacts are Git-owned and are not mutable PostgreSQL properties:

| Property                 | Type               | Rules                                                        |
| ------------------------ | ------------------ | ------------------------------------------------------------ |
| `description`            | string             | Bounded customer-facing description                          |
| `released_at`            | timestamp nullable | Upstream model release time                                  |
| `hugging_face_id`        | string nullable    | Upstream repository identity                                 |
| `quantization`           | string nullable    | OpenRouter-compatible quantization                           |
| `tokenizer`              | string nullable    | Tokenizer family exposed to OpenRouter                       |
| `input_modalities`       | input-modality[]   | Nonempty typed modality documents                            |
| `output_modalities`      | output-modality[]  | Nonempty typed modality documents                            |
| `pricing`                | pricing-entry[]    | Request-scoped prices only                                   |
| `capacity`               | capacity-entry[]   | Advertised request-scoped capacity                           |
| `passthrough_parameters` | descriptor map     | Closed request-scoped passthrough parameters                 |
| `deprecation_at`         | timestamp nullable | Optional scheduled retirement                                |
| `is_free`                | boolean            | Default false                                                |
| `discount_to_user`       | decimal            | Below one; default zero                                      |
| `openrouter`             | object nullable    | Optional canonical `slug` when it differs from this row's ID |

Each input/output modality owns its typed constraints, supported parameters, modality-scoped pricing and advertised capacity. Capability descriptors use the OpenRouter-compatible range, integer, boolean, enum, array, object or unknown grammar. `passthrough_parameters` is the exact model's public request allowlist, not a gateway-wide Rust request schema: the gateway validates descriptor-level types and bounds, preserves qualified JSON values, and leaves deep tool, content, structured-output and cross-field semantics to the pinned SGLang/model combination. Unadvertised fields are rejected rather than silently dropped or blindly exposed from SGLang's larger private protocol. Internal prices use nonnegative integer `cost` under the global nano-USD convention. The provider response converts these values to OpenRouter's decimal-string USD-per-unit pricing fields. This is a closed domain document, not arbitrary metadata.

The TypeScript API service owns model changes. After a price or status mutation commits, it reloads the current row from the PostgreSQL primary and synchronously projects it to Valkey before reporting success. A capacity monitor or operator may set `status = 'unavailable'` when qualified GPU capacity is unavailable and restore `available` when service is ready. Rust receives the current `GatewayModel` through Valkey and rejects unavailable, retired or unknown model IDs before GPU work.

## Billing

### 11. `billing_accounts`

One record per organization.

| Field                | Type        | Null | Rules                        |
| -------------------- | ----------- | ---- | ---------------------------- |
| `organization_id`    | uuid        | no   | PK and FK `organizations.id` |
| `mode`               | text        | no   | `prepaid`, `invoiced`        |
| `stripe_customer_id` | text        | yes  | Unique when present          |
| `balance`            | bigint      | no   | Remaining spendable amount   |
| `created_at`         | timestamptz | no   | Creation time                |
| `updated_at`         | timestamptz | no   | Last mutation time           |

PostgreSQL owns the durable posted balance, while Valkey owns the synchronous balance including terminal usage not yet posted to PostgreSQL. Inference never reads this row. For a prepaid organization, `balance` is its remaining prepaid funds and Stripe top-ups replenish it. For an invoiced organization such as OpenRouter, `balance` is its remaining approved credit exposure and payments or operator credits replenish it. Every organization uses the same admission and settlement path: a nonpositive balance blocks new admission, while final in-flight generations may move the balance slightly below zero. A chargeback or adjustment may also make the durable balance negative, and the corresponding Valkey update blocks new admission.

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
| `source_id`        | text        | no   | Source object or derived `<slot_id>:<organization_id>`                      |
| `period_start`     | timestamptz | yes  | Aggregated usage only                                                       |
| `period_end`       | timestamptz | yes  | Aggregated usage only; after `period_start`                                 |
| `generation_count` | bigint      | yes  | Positive for aggregated usage                                               |
| `created_by`       | uuid        | yes  | FK `users.id`; manual credits and adjustments only                          |
| `created_at`       | timestamptz | no   | Movement time                                                               |

`(source_type, source_id)` is unique and is the idempotency boundary. Initial source types are `stripe_checkout_session`, `stripe_refund`, `stripe_dispute`, `generation_settlement_batch`, `openrouter_payment` and `operator`.

A balance mutation locks the account row, inserts the immutable movement and updates `billing_accounts.balance` in one PostgreSQL transaction. Positive amounts add funds and negative amounts consume funds. Usage is aggregated from launch: every terminal generation belongs to one global settlement slot derived from its Valkey Stream ID. All organizations share that slot. For each organization with nonzero usage in the slot, the PostgreSQL settlement worker posts one `generation_settlement_batch` movement whose negative amount is the sum of its generation charges and whose `generation_count` counts those charged generations. Individual generations remain queryable in ClickHouse. An organization with only zero-charge generations produces no PostgreSQL balance transaction.

The settlement loop runs inside the TypeScript `worker` deployment. One pod holds a PostgreSQL session advisory lock and acts as leader; standby pods periodically retry, and loss of the database session releases the lock automatically. Launch uses five-minute global slots. A slot ID is a fixed-width, chronologically sortable string containing its UTC start, duration and settlement schema version, for example `20260815T123000Z-300s-v1`. The end is derived from the encoded start and duration. The PostgreSQL source ID for one organization's posting is deterministically `<settlement_slot_id>:<organization_id>`.

On startup, the leader reads the greatest `period_start` where `source_type = 'generation_settlement_batch'`, derives that global slot and resumes it inclusively. If none exists, it asks ClickHouse for the earliest eligible slot. For each slot, one ClickHouse query first collapses retries by generation `id`, then groups the materialized `charge` by materialized `organization_id`. The worker derives every nonzero organization's source ID, queries PostgreSQL for the existing IDs, and computes the missing organizations in memory. Each missing organization is handled in its own short transaction: lock its billing account, insert the immutable usage transaction and update `billing_accounts.balance` only if the insert succeeds. The worker verifies that every nonzero organization in the slot exists in PostgreSQL before moving to the next slot.

The financial query is permanently duplicate-safe and does not depend on ClickHouse retaining insert-deduplication tokens:

```sql
SELECT
    settlement_slot_id,
    organization_id,
    sum(charge) AS total_charge,
    countIf(charge > 0) AS generation_count,
    max(financial_variants) AS max_financial_variants
FROM
(
    SELECT
        id,
        any(settlement_slot_id) AS settlement_slot_id,
        any(organization_id) AS organization_id,
        any(charge) AS charge,
        uniqExact(tuple(settlement_slot_id, organization_id, charge)) AS financial_variants
    FROM generations
    WHERE settlement_slot_id = {slot_id:String}
    GROUP BY id
)
GROUP BY settlement_slot_id, organization_id;
```

The worker requires `max_financial_variants = 1` for every result before opening any PostgreSQL transaction. Exact retry duplicates have one distinct `(slot, organization, charge)` tuple and collapse to one logical generation. If duplicate rows for one generation ID disagree on any financial value, the worker emits a high-severity metric and blocks the complete slot for operator review rather than choosing a value. Do not create a ClickHouse projection at launch; add one ordered by `(settlement_slot_id, organization_id, id)` only when measured settlement-query cost justifies it.

The unique `(source_type, source_id)` constraint makes the complete process idempotent. A crash before, during or after a slot causes inclusive replay: completed organizations are skipped and missing organizations are posted. Because the worker never posts a later slot until the current one is complete, PostgreSQL's latest settlement slot is a sufficient restart cursor and no checkpoint table is needed. A globally zero-charge slot has no PostgreSQL record and may be revisited after restart; replay is harmless and immediately advances.

A slot becomes eligible only after a conservative fixed settlement delay and after the ClickHouse ingestion consumer's contiguous acknowledged Valkey Stream watermark has passed the slot's derived end. Settlement is therefore eventually current by the ingestion delay, settlement delay and polling interval rather than synchronously current. There is no settlement checkpoint, batch manifest, ClickHouse update, cross-database join, routine 24-hour rescan or Kafka topic. A periodic reconciliation query may audit recent ClickHouse totals against PostgreSQL, but it is not the normal cursor path. If one settlement worker can no longer keep up, page the organizations within a slot; shard settlement leadership only after measurements require it.

Stripe owns pending, failed and abandoned Checkout Sessions. The application creates a server-priced Checkout Session carrying the organization identity. A signed successful-payment webhook inserts a `topup` movement keyed by the Checkout Session ID. The handler returns success only after the PostgreSQL transaction commits; Stripe retries failures, and the source uniqueness constraint makes duplicate delivery harmless. Refund and dispute webhooks use their Stripe object IDs in the same way. There is no local top-up-intent or webhook-inbox table.

## PostgreSQL-to-Valkey synchronization

There is no projection queue or outbox table. These projections are low-volume, level-triggered copies of current PostgreSQL state. After an ordinary control-plane mutation commits, the TypeScript application reloads the latest authoritative row from the PostgreSQL primary, writes its stable Valkey key and reports success only after Valkey acknowledges. If projection fails, the operation returns `503`; retrying projects the already-committed current state.

Restrictive changes fail closed. API-key revocation, organization suspension, model unavailability or price changes, and negative balance adjustments first block the affected Valkey scope, then commit PostgreSQL, then publish the final state and reopen only when appropriate. A failure leaves that scope blocked. Permissive changes such as key creation, model creation and positive top-ups commit PostgreSQL first, so a projection failure withholds access or credit rather than granting too much.

The reconciliation loop inside the TypeScript `worker` deployment periodically reconciles PostgreSQL with Valkey and performs a complete rebuild at startup or after Valkey loss. It always reloads current rows instead of replaying mutation payloads, so a delayed operation cannot overwrite newer state. Each logical object has one stable Valkey key. Rebuilds close all admission, drain and post terminal generation events, wait for or expire in-flight leases, rewrite projections in place and then reopen.

PostgreSQL-originated money changes are reconciled from immutable `balance_transactions` and applied to Valkey through a versioned Lua script. The script atomically adds the PostgreSQL transaction ID to `AppliedBalanceTransactionIds` and changes `GatewayAccount.balance` only when the ID was newly added. A lost acknowledgement and retry therefore cannot apply the same top-up, payment, refund, chargeback or operator adjustment twice. The reconciler never overwrites an operational Valkey balance containing terminal usage not yet posted to PostgreSQL. Valkey-originated `generation_settlement_batch` postings do not echo back into Valkey and are never added to this set because Rust already applied their charges.

The reconciler exports its last-success time, failures and mismatches as metrics. Missing or unavailable required projection state rejects every request. Do not add CDC, Debezium, Kafka, a projection queue or a standalone projector at launch.

# Git-owned deployment configuration

Environment-specific infrastructure and runtime configuration is Zod-authored and committed to Git. Customer-facing model metadata, prices and availability live in PostgreSQL.

## 13. `ModelDeploymentManifest`

Environment-specific serving configuration.

| Field                          | Type    | Rules                                    |
| ------------------------------ | ------- | ---------------------------------------- |
| `schema_version`               | string  | Manifest schema version                  |
| `id`                           | string  | Deployment identity                      |
| `model_id`                     | string  | Exact ID of the PostgreSQL `models` row  |
| `environment`                  | string  | `local`, `staging`, `production`         |
| `provider`                     | string  | Selected GPU provider                    |
| `provider_region`              | string  | Provider region                          |
| `country_code`                 | string  | ISO 3166-1 alpha-2                       |
| `cluster_id`                   | string  | Non-secret cluster identity              |
| `namespace`                    | string  | Kubernetes namespace                     |
| `service_url`                  | string  | Private or restricted SGLang URL         |
| `auth_secret_ref`              | string  | Secret reference, never secret value     |
| `sglang_image_digest`          | string  | Immutable OCI digest                     |
| `gpu_instance_type`            | string  | Initially `b300-8x`                      |
| `gpu_count`                    | integer | Initially 8                              |
| `model_path`                   | string  | Exact model repository or artifact path  |
| `model_revision`               | string  | Immutable model commit or digest         |
| `tokenizer_path`               | string  | Exact tokenizer repository or path       |
| `tokenizer_revision`           | string  | Immutable tokenizer commit or digest     |
| `tensor_parallel_size`         | integer | Initially 8                              |
| `memory_fraction_static`       | decimal | Greater than zero and below one          |
| `reasoning_parser`             | string  | Initially `kimi_k3`                      |
| `tool_call_parser`             | string  | Initially `kimi_k3`                      |
| `metrics_enabled`              | boolean | Required true in production              |
| `prompt_tokens_per_minute`     | integer | Measured nonnegative capacity            |
| `completion_tokens_per_minute` | integer | Measured nonnegative capacity            |
| `max_running_requests`         | integer | Measured positive SGLang scheduler limit |
| `max_queued_requests`          | integer | Measured nonnegative bounded queue       |
| `zdr`                          | boolean | Zero-retention declaration               |
| `hipaa`                        | boolean | Initially false                          |

All four artifact fields are required even when the tokenizer path and revision equal the model path and revision; the deployed release never relies on inheritance or a mutable upstream default. The served release digest covers the exact model and tokenizer identities, SGLang image and canonical deployment runtime configuration. Mutable customer prices, public metadata and availability are excluded from this digest and are projected separately from PostgreSQL.

# ClickHouse models

ClickHouse Cloud on AWS stores the durable immutable terminal-generation history for customer usage, aggregate PostgreSQL settlement, spend analysis and inference performance. It is not the authority for current balances, credentials, in-flight leases or posted financial movements.

## 14. `generations`

One row per terminal model invocation. Direct and OpenRouter traffic share this table. `properties` is the canonical document for all generation facts other than row identity and ingestion time. Keep only `id`, `properties` and `ingested_at` as independently inserted source columns; derive the small set of query-critical dimensions as ClickHouse `MATERIALIZED` columns from JSON paths.

| Field                  | ClickHouse type        | Storage      | Rules                                           |
| ---------------------- | ---------------------- | ------------ | ----------------------------------------------- |
| `id`                   | UUID                   | stored       | Logical unique generation ID; UUIDv7            |
| `properties`           | JSON                   | stored       | Closed versioned `GenerationProperties`         |
| `ingested_at`          | DateTime64(6, 'UTC')   | stored       | ClickHouse ingestion time                       |
| `event_schema_version` | UInt16                 | materialized | Terminal-event envelope version                 |
| `organization_id`      | UUID                   | materialized | PostgreSQL organization identity                |
| `workspace_id`         | UUID                   | materialized | PostgreSQL workspace identity                   |
| `api_key_id`           | UUID                   | materialized | PostgreSQL API-key identity                     |
| `model_id`             | LowCardinality(String) | materialized | Exact requested hosted-model ID                 |
| `settlement_slot_id`   | String                 | materialized | Shared chronological global settlement slot     |
| `status`               | LowCardinality(String) | materialized | `succeeded`, `failed`, `cancelled`, `abandoned` |
| `charge`               | Int64                  | materialized | `properties.usage.charge`                       |
| `completed_at`         | DateTime64(6, 'UTC')   | materialized | Terminal time and partition timestamp           |

Use an append-only `MergeTree`, partitioned by `toYYYYMM(completed_at)` and initially ordered by `(organization_id, workspace_id, completed_at, id)`. UUIDv7 allows a point lookup to derive the likely time partition from the generation ID. Add a projection for another access pattern only after measurements justify it.

`GenerationProperties` is a closed, versioned Zod-authored JSON document:

```text
{
  event_schema_version: integer,
  external_id: string | null,
  organization_id: uuid,
  workspace_id: uuid,
  api_key_id: uuid,
  model_id: string,
  served_release_digest: string,
  status: "succeeded" | "failed" | "cancelled" | "abandoned",
  streamed: boolean,
  pricing: {
    schema_version: integer,
    components: Array<{
      unit: string,
      quantity: integer,
      unit_price: integer,
      amount: integer
    }>
  },
  usage: {
    charge: integer,
    input_tokens: integer,
    cached_input_tokens: integer,
    output_tokens: integer,
    reasoning_tokens: integer
  },
  outcome: {
    finish_reason: string | null,
    error_code: string | null,
    usable_output_delivered: boolean,
    cancellation_owner: "client" | "server" | "runtime" | null
  },
  timing: {
    received_at: timestamp,
    started_at: timestamp | null,
    first_token_at: timestamp | null,
    completed_at: timestamp
  },
  settlement: {
    slot_id: string
  }
}
```

`pricing` contains every effective price component used for the generation after discounts, including configured zero-quantity or zero-price components. `unit` is a closed schema-versioned value such as `request`, `input_token`, `cached_input_token`, `output_token` or `reasoning_token`. Under the global nano-USD convention, each component's `amount` is exactly `quantity * unit_price`, and all component amounts sum exactly to `usage.charge`; no monetary rounding policy is needed. This preserves the complete billing calculation when the global model price later changes without copying unrelated model descriptions, capabilities, capacity or availability.

The application validates the complete properties document before insertion; it is not arbitrary JSON. New optional properties and new closed schema versions do not require a ClickHouse table migration. The initial materialized columns exist because they define tenant filtering, ordering, common status filtering or PostgreSQL settlement. Add another materialized column from a JSON path only when a measured filtering, grouping or indexing pattern justifies it. The original value remains in `properties`, so a materialization is a query optimization rather than another source of truth.

One TypeScript ClickHouse-ingestion consumer group reads `GenerationSettled` from Valkey. For each event it derives the global `settlement.slot_id` from the Valkey Stream ID's time bucket and settlement schema. Every organization in that time bucket receives the same slot ID; ClickHouse materializes it for chronological reconciliation. The worker issues one logical insert per generation with ClickHouse `async_insert = 1` and `wait_for_async_insert = 1`; ClickHouse combines those inserts server-side. Retries use a generation-ID-based insert deduplication token as a normal-path optimization, but billing correctness never depends on the lifetime of that token. The worker acknowledges a stream entry only after ClickHouse confirms the asynchronous insert was flushed, uses `XAUTOCLAIM` to recover abandoned pending entries, and trims only through the contiguous acknowledged watermark. That watermark is derived from the consumer group's last-delivered ID and oldest pending ID rather than stored in another database table. Do not use `ReplacingMergeTree`, lifecycle updates or `FINAL` queries for the launch schema.

Do not store prompts, completions, arbitrary request JSON, credentials, private runtime URLs or attempt arrays. The seed has one exact runtime target and no fallback. Generations have no TTL and are retained indefinitely at launch. Rely on ClickHouse Cloud's managed durability and backups initially; do not build a separate archival or export pipeline until retention, regulatory or recovery requirements justify one.

# Inference event contracts

This versioned closed schema decouples Rust inference from ClickHouse and PostgreSQL. `GenerationSettled` is an entry in exactly one dedicated Valkey Stream at `generation-settled:{settlement-0}`, not a standalone Valkey key or durable table. It remains available for consumer replay until acknowledged and safely trimmed; ClickHouse becomes the durable per-generation record.

One atomic Valkey finalization consumes the generation's in-flight lease, subtracts its actual charge from the synchronous account balance and appends `GenerationSettled`. The lease is the one-time settlement token: only the finalizer that removes it may charge the account or append the event. There is no reservation event or settled-generation key.

The generation-ingest loop inside the TypeScript `worker` deployment consumes the stream into ClickHouse and acknowledges each entry only after ClickHouse confirms its insert. A separately supervised loop in the same worker pulls eligible global settlement slots from ClickHouse into PostgreSQL; it does not consume or acknowledge the Valkey Stream. These loops are not separate deployed services.

The stream has no TTL. Monitor pending-entry age, consumer lag and memory, alert well before capacity pressure, and fail closed on new inference admission if the unacknowledged backlog threatens the cache. Amazon ElastiCache Serverless for Valkey supplies a managed, replicated Multi-AZ transport, but this stream is not treated as a zero-loss financial archive. The accepted launch tradeoff is a rare bounded loss of revenue and telemetry if Valkey loses an unacknowledged event before ClickHouse has it; adding Kafka or another durable broker requires measured evidence that this risk is no longer acceptable.

## 15. `GenerationSettled`

The canonical terminal-generation event carries one generation identity and one closed properties document. Its `properties` has the `GenerationProperties` shape except for `settlement`, which cannot be known until Valkey assigns the Stream ID. The ClickHouse consumer derives and adds `settlement`, while ClickHouse supplies `ingested_at` and materializes query columns from the completed JSON document.

| Field           | Type                                        |
| --------------- | ------------------------------------------- |
| `generation_id` | uuid                                        |
| `properties`    | `GenerationProperties` without `settlement` |

# Valkey hot-path models

These models exist before any inference traffic is enabled. PostgreSQL projects OpenRouter and direct credentials, organization/workspace state, billing state and serving policy into Valkey. OpenRouter is an organization like any other and uses the identical credential, in-flight lease, admission, finalization and `GenerationSettled` path. The only distinction is billing semantics: `prepaid` balances represent deposited funds, while `invoiced` balances represent remaining approved credit exposure.

## 16. `GatewayAccount`

Valkey key at seed: `account:{settlement-0}:<organization_id>`.

| Field                 | Type                               |
| --------------------- | ---------------------------------- |
| `organization_id`     | uuid                               |
| `organization_kind`   | `customer`, `distribution_channel` |
| `organization_status` | organization status                |
| `billing_mode`        | `prepaid`, `invoiced`              |
| `balance`             | bigint                             |

## 17. `GatewayWorkspace`

Valkey key: `workspace:<workspace_id>`.

| Field             | Type               |
| ----------------- | ------------------ |
| `organization_id` | uuid               |
| `workspace_id`    | uuid               |
| `archived_at`     | timestamp nullable |

## 18. `GatewayCredential`

Valkey key: `credential:<hex SHA-256 digest>`. The digest is the lookup key and is not duplicated in the value.

| Field             | Type               |
| ----------------- | ------------------ |
| `api_key_id`      | uuid               |
| `organization_id` | uuid               |
| `workspace_id`    | uuid               |
| `expires_at`      | timestamp nullable |
| `revoked_at`      | timestamp nullable |

## 19. `GatewayModel`

Valkey key: `model:<id>`.

| Field        | Type              |
| ------------ | ----------------- |
| `id`         | string            |
| `name`       | string            |
| `status`     | model status      |
| `properties` | `ModelProperties` |

This directly mirrors the serving-relevant PostgreSQL `models` row. The catalog is small, so retaining one shared model shape is simpler than maintaining a second flattened projection. Rust combines it with the locally loaded `ModelDeploymentManifest`; the deployment manifest supplies the target, measured capacity, datacenter/compliance declarations and served release digest. The `GatewayModel` supplies customer-visible identity, capabilities, advertised capacity, prices and availability.

## 20. `InFlightGenerationLease`

Valkey key at seed: `inflight:{settlement-0}:<organization_id>`. This is a sorted set, not a row or hash.

| Part   | Value              |
| ------ | ------------------ |
| member | `generation_id`    |
| score  | `lease_expires_at` |

Admission atomically verifies a positive remaining balance and counts unexpired members before adding the new generation with `ZADD NX`. It derives the organization's current limit as `min(normal_concurrency_ceiling, ceil(balance / balance_per_concurrency_slot))`, so any positive balance funds one request and concurrency falls proportionally as balance is consumed. Both inputs are operational deployment configuration, not customer-facing product controls. `balance_per_concurrency_slot` only converts current balance into a concurrency count; it is not a reservation, request-cost estimate or hard downside bound. Admission does not compare a request's theoretical maximum charge with the current balance or per-slot amount because that would reject ordinary requests whose requested output ceiling is rarely reached. No money is reserved and the lease remains only a generation ID plus expiry. Concurrent generations can move the balance below zero before their terminal charges become visible. Model context/output limits and the normal concurrency ceiling limit this operational risk, and subsequent requests are blocked until a top-up, payment or operator credit makes the balance positive.

Rust extends a live generation with `ZADD XX`. Expired members do not count toward concurrency and remain for a short grace period before cleanup so a delayed finalization can still succeed. Terminal finalization is a versioned server-side Lua script invoked with `EVALSHA`: remove the member, subtract the actual charge from `GatewayAccount.balance`, and append exactly one `GenerationSettled` event. If the member is already absent, the script performs no financial or stream mutation. This makes the lease itself the idempotency boundary even when a successful command response is lost; no `settled:<generation_id>` key is required.

The script executes without interleaving, which supplies the required conditional atomicity; `MULTI`/`EXEC` alone cannot branch on whether lease removal succeeded. Valkey scripts are not rollback transactions, so the script validates arguments and key types before its fixed writes and the application exclusively owns those key shapes. Valkey Cluster hashes only the text inside braces, so the shared `{settlement-0}` tag places `account:{settlement-0}:<organization_id>`, `inflight:{settlement-0}:<organization_id>` and `generation-settled:{settlement-0}` in the same cluster hash slot. Credential, workspace and model keys are read outside this script and do not need that tag.

Seed runs one settlement shard. Later horizontal scaling assigns each organization to a stable shard and uses the same tag for all three keys, for example `account:{settlement-7}:<organization_id>`, `inflight:{settlement-7}:<organization_id>` and `generation-settled:{settlement-7}`. Changing shard assignment is an explicit drained migration rather than an implicit modulo change.

The lease intentionally contains no request metadata. Rust carries the authenticated identities, model release, actual usage, admission-time prices and timing through the live request. It uses those captured nano-USD prices to calculate `properties.usage.charge` and emits the exact pricing snapshot and changing terminal details inside `GenerationSettled.properties`. `generation_id` identifies the durable ClickHouse row. The ClickHouse consumer adds the global settlement slot, and the PostgreSQL worker derives the per-organization source ID as `<settlement_slot_id>:<organization_id>`. The Valkey Stream has its own transport entry ID, so there is no separate event UUID. A process loss may leave an unbilled generation that expires without a terminal analytics row. That bounded revenue and observability loss is accepted at launch in exchange for eliminating monetary reservations and durable in-progress request state.

## 21. `AppliedBalanceTransactionIds`

Valkey key at seed: `applied-balance-transactions:{settlement-0}:<organization_id>`. This is a set, not a row or hash.

| Part   | Value                    |
| ------ | ------------------------ |
| member | `balance_transaction_id` |

The set contains only PostgreSQL-originated transactions whose signed amount must change the operational Valkey balance: top-ups, payments, refunds, chargebacks, credits and adjustments. It has no TTL because transaction replay must remain idempotent indefinitely; this traffic is low-volume compared with generations. The balance-projection Lua script receives the account key, this set key, transaction ID and signed amount. It validates key types and arguments, calls `SADD`, and applies the amount only when `SADD` returns one. Both keys use the same settlement hash tag and therefore share a Valkey cluster slot.

A complete Valkey rebuild closes admission and drains terminal usage until PostgreSQL and the operational balance agree. It then restores `GatewayAccount.balance` from PostgreSQL and reconstructs this set from all PostgreSQL-originated balance transactions before reopening admission. Ordinary generation settlement transactions are excluded from reconstruction.

# Explicitly excluded models

The following existed in older plans and are not part of the data model:

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
