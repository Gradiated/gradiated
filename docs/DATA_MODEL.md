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
- PostgreSQL owns the global hosted-model catalog, pricing, availability and
  durable model-deployment registry. Git owns the infrastructure declarations
  that create the corresponding SGLang workloads, not a second routing record.
- The launch has universal zero prompt/response retention and no trace tables.
  Configurable retention requires a later explicit product decision.
- Organization membership is the human authorization boundary. Workspaces are
  policy and cost-attribution boundaries available to all active members.
- Prepaid and invoiced organizations share the same account, lease,
  finalization, and settlement records. Billing mode changes admission:
  prepaid balance limits serving, while invoiced balance is accounting-only at
  launch. All internal monetary values use integer nano-USD.

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

`ModelProperties` is a closed, versioned Zod document inspired by OpenRouter's
current provider schema. It keeps model capabilities, limits, and prices in the
same modality-owned structure used to advertise the model, without storing the
OpenRouter wire response verbatim. Exact deployed model and tokenizer artifacts
belong to `model_deployments`, not to this customer-facing document.

| Property                 | Type                    | Rules                                                        |
| ------------------------ | ----------------------- | ------------------------------------------------------------ |
| `schema_version`         | integer                 | Initially `1`                                                |
| `description`            | string                  | Bounded customer-facing description                          |
| `released_at`            | timestamp nullable      | Upstream model release time                                  |
| `hugging_face_id`        | string nullable         | Upstream repository identity                                 |
| `quantization`           | string nullable         | Closed OpenRouter-compatible quantization                    |
| `tokenizer`              | string nullable         | Tokenizer family exposed to OpenRouter                       |
| `input_modalities`       | input-modality[]        | Nonempty typed modality documents                            |
| `output_modalities`      | output-modality[]       | Nonempty typed modality documents                            |
| `passthrough_parameters` | capability-descriptor map | Bounded request-scoped extension allowlist                 |
| `deprecation_date`       | timestamp nullable      | Optional scheduled retirement                                |

The launch text input modality contains `supported_inputs.max_context_length`
and `max_prompt_length`, both expressed as positive token measures. Its pricing
entries use `prompt`, `cached_prompt`, and optional `cache_write`. The launch
text output modality contains its positive token `max_length`, positive
`default_length`, a `streaming` flag, `supported_parameters`, and pricing
entries for `completion` and optional `internal_reasoning`. `default_length`
cannot exceed `max_length`. Each pricing entry has `unit = token` and a
nonnegative integer `cost` in nano-USD. Pricing types are unique within their
modality; `prompt`, `cached_prompt`, and `completion` are present in every
stored document.

The Zod write schema is the normalization boundary. Before PostgreSQL is
written it materializes `schema_version = 1`, nullable catalog metadata,
`deprecation_date = null`, empty parameter maps, `streaming = true`, and an
output `default_length` of 1,024 tokens capped by `max_length`. If
`max_prompt_length` is omitted it becomes `max_context_length`; if
`cached_prompt` pricing is omitted it becomes the `prompt` price. When the
model advertises a `reasoning` parameter without a separate
`internal_reasoning` price, that price becomes the `completion` price. The
closed stored/read schema then requires this normalized shape. Consequently the
Valkey projection is complete and the Rust gateway never invents catalog
defaults or interprets missing fields.

Capability descriptors use the OpenRouter-inspired `range`, `integer`,
`boolean`, `enum`, or `unknown` grammar. Presence in `supported_parameters` or
`passthrough_parameters` is the public allowlist. The gateway applies scalar
bounds when the descriptor directly describes the wire value, preserves
qualified JSON unchanged, and leaves complex tool, content, structured-output,
and cross-field semantics to the pinned SGLang/model combination. Unadvertised
fields are rejected rather than silently dropped or blindly exposed from
SGLang's larger private protocol.

OpenRouter's `capacity` entries describe measured throughput, not context-window
or output-length limits. They are omitted at launch until the availability
service owns measured capacity. The provider response derives `id`, `name`,
`created`, and `is_ready` from relational model state and converts nano-USD
prices to exact decimal `cost_usd` strings. Discounts, free variants,
OpenRouter aliases, datacenter declarations, and compliance declarations are
not stored until the product implements them. This is a cohesive domain
document, not arbitrary metadata.

The TypeScript API service owns model changes. After a price or status mutation commits, it reloads the current row from the PostgreSQL primary and synchronously projects it to Valkey before reporting success. A capacity monitor or operator may set `status = 'unavailable'` when qualified GPU capacity is unavailable and restore `available` when service is ready. Rust receives the current `GatewayModel` through Valkey and rejects unavailable, retired or unknown model IDs before GPU work.

## Billing

### 11. `billing_accounts`

One record per organization.

| Field                | Type        | Null | Rules                        |
| -------------------- | ----------- | ---- | ---------------------------- |
| `organization_id`    | uuid        | no   | PK and FK `organizations.id` |
| `mode`               | text        | no   | `prepaid`, `invoiced`        |
| `stripe_customer_id` | text        | yes  | Unique when present          |
| `balance`            | bigint      | no   | Signed account position      |
| `created_at`         | timestamptz | no   | Creation time                |
| `updated_at`         | timestamptz | no   | Last mutation time           |

PostgreSQL owns the durable posted balance, while Valkey owns the synchronous balance including terminal usage not yet posted to PostgreSQL. Inference never reads this row. For a prepaid organization, `balance` is its remaining prepaid funds and Stripe top-ups replenish it; a nonpositive value blocks new admission. For an invoiced organization such as OpenRouter, `balance` is its net accounting position: it starts at zero, usage makes it negative, and payments or operator credits move it back toward zero. Invoiced admission ignores this value at launch. Prepaid final in-flight generations may move the balance slightly below zero, and chargebacks or adjustments may also make it negative. An invoiced organization is stopped explicitly with `organizations.status = 'suspended'`, not implicitly through its balance.

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

There is no projection queue or outbox table. Most serving projections are low-volume, level-triggered copies of current PostgreSQL state. After an ordinary control-plane mutation commits, the TypeScript application reloads the latest authoritative row from the PostgreSQL primary, updates its stable Valkey key and reports success only after Valkey acknowledges. If projection fails, the operation returns `503`; retrying projects the already-committed current state.

Projection behavior is explicit by state:

| Valkey state | Ordinary synchronization rule |
| ------------ | ----------------------------- |
| `GatewayCredential` | Replace from the current PostgreSQL API-key row. |
| `GatewayWorkspace` | Replace from the current PostgreSQL workspace row. |
| `GatewayModel` | Replace from the current PostgreSQL model row and all of its deployment rows. |
| `GatewayAccount.organization_id`, `organization_kind`, `organization_status`, `billing_mode` | Replace the selected nonmonetary hash fields from current PostgreSQL state. |
| `GatewayAccount.balance` | Never overwrite from the current PostgreSQL row during ordinary operation; apply eligible PostgreSQL `balance_transactions` exactly once as deltas. |

This distinction prevents an account metadata update or periodic reconciliation
from erasing finalized Valkey usage that has not yet reached PostgreSQL.

Restrictive changes fail closed. API-key revocation, organization suspension, model unavailability or price changes, and prepaid negative balance adjustments first block the affected Valkey scope, then commit PostgreSQL, then publish the final state and reopen only when appropriate. A failure leaves that scope blocked. Permissive changes such as key creation, model creation and prepaid positive top-ups commit PostgreSQL first, so a projection failure withholds access or credit rather than granting too much. Invoiced balance movements remain accounting changes and do not change serving admission.

The reconciliation loop inside the TypeScript `worker` deployment periodically reconciles PostgreSQL with Valkey and performs a complete rebuild at startup or after Valkey loss. It always reloads current rows instead of replaying mutation payloads, so a delayed operation cannot overwrite newer state. Each logical object has one stable Valkey key. Rebuilds close all admission, drain and post terminal generation events, wait for or expire in-flight leases, rewrite projections in place and then reopen.

PostgreSQL-originated money changes are reconciled from immutable `balance_transactions` and applied to Valkey through a versioned Lua script. The script atomically adds the PostgreSQL transaction ID to `AppliedBalanceTransactionIds` and changes `GatewayAccount.balance` only when the ID was newly added. A lost acknowledgement and retry therefore cannot apply the same top-up, payment, refund, chargeback or operator adjustment twice. The reconciler never overwrites an operational Valkey balance containing terminal usage not yet posted to PostgreSQL. Valkey-originated `generation_settlement_batch` postings do not echo back into Valkey and are never added to this set because Rust already applied their charges.

The reconciler exports its last-success time, failures and mismatches as metrics. Missing or unavailable required projection state rejects every request. Do not add CDC, Debezium, Kafka, a projection queue or a standalone projector at launch.

## 13. `model_deployments`

Durable registry of concrete SGLang deployments for hosted models. One model
may have multiple rows so releases can overlap during draining and a future
availability service can manage capacity without changing the model catalog.
The gateway accepts multiple `available` rows and selects the first available
child in projection order. The current order is deterministic; a future
availability service may make that order capacity-aware.

| Field         | Type        | Null | Rules                                                        |
| ------------- | ----------- | ---- | ------------------------------------------------------------ |
| `id`          | uuid        | no   | Primary key; stable deployment identity                      |
| `model_id`    | text        | no   | FK `models.id`                                               |
| `status`      | text        | no   | `available`, `unavailable`, `draining`                       |
| `service_url` | text        | no   | Bounded private or restricted absolute HTTP(S) SGLang URL    |
| `release`     | jsonb       | no   | Closed Zod `ModelDeploymentRelease` document                 |
| `created_at`  | timestamptz | no   | Creation time                                                |
| `updated_at`  | timestamptz | no   | Last routing/status mutation                                 |

`ModelDeploymentRelease` contains `schema_version`, initially `1`, plus
`runtime_revision`, `model_path`, `model_revision`, `tokenizer_path`, and
`tokenizer_revision`. All identifiers are required and bounded even when the
tokenizer identity equals the model identity. `runtime_revision` is a native
SGLang source revision locally and an immutable OCI image digest in production.
Rust serializes this typed object canonically and hashes only it to produce the
`served_release_digest` captured by each admitted generation.

There is no generic deployment metadata. A field that later affects routing,
availability, capacity, compliance or cost becomes an explicit column or part
of another closed versioned document. Provider, region, GPU shape and configured
capacity are added only when the availability service consumes them. Volatile
health, queue depth and free capacity remain operational observations rather
than durable PostgreSQL fields.

Git continues to own the Kubernetes/SGLang workload declaration that creates a
deployment. The deployment workflow registers the resulting route and exact
release in PostgreSQL only after the endpoint is ready, and marks the old row
`draining` before removal. Secret values and secret-location indirection never
appear in this table; the gateway reads the optional upstream credential from
the fixed `SGLANG_API_KEY` process secret. One gateway-wide hard generation
timeout applies to every model and defaults to 300 seconds at launch.

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
    cache_write_tokens: integer,
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

`pricing` contains every effective price component used for the generation,
including configured zero-quantity or zero-price components. Terminal generation
units remain normalized as `input_token`, `cached_input_token`,
`cache_write_token`, `output_token`, or `reasoning_token`; model-catalog pricing
types map from `prompt`, `cached_prompt`, `cache_write`, `completion`, and
`internal_reasoning` respectively. Under the global nano-USD convention, each
component's `amount` is exactly `quantity * unit_price`, and all component
amounts sum exactly to `usage.charge`; no monetary rounding policy is needed.
This preserves the complete billing calculation when the global model price
later changes without copying unrelated model descriptions, capabilities,
capacity, or availability.

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

These models exist before any inference traffic is enabled. PostgreSQL projects OpenRouter and direct credentials, organization/workspace state, billing state and serving policy into Valkey. OpenRouter is an organization like any other and uses the identical credential, in-flight lease, admission, finalization and `GenerationSettled` script path. The billing-mode branch is explicit: `prepaid` balance gates admission and scales concurrency, while `invoiced` balance records the net accounting position and does not gate serving at launch.

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
| `deployments` | `GatewayModelDeployment[]` |

This is the route-ready projection of one PostgreSQL `models` row and all of
its `model_deployments` rows. Each `GatewayModelDeployment` contains `id`,
`status`, `service_url`, and the closed `ModelDeploymentRelease`; `model_id` is
not duplicated inside each child because the parent key and `GatewayModel.id`
already fix it. The projector replaces the complete document with one `SET`
after either the model or one of its deployments changes. `gateway-model-ids`
is a Valkey set containing projected model IDs; it is an enumeration index for
readiness and `/v1/models`, not another authority.

An available model is ready for inference when at least one valid child
deployment has `status = available`. The gateway selects the first such child
in the projected array. The projector currently orders rows deterministically
by creation time and ID; a future availability service may publish a
capacity-aware order. A missing route fails closed as
`serving_state_unavailable`.

## 20. `InFlightGenerationLease`

Valkey key at seed: `inflight:{settlement-0}:<organization_id>`. This is a sorted set, not a row or hash.

| Part   | Value              |
| ------ | ------------------ |
| member | `generation_id`    |
| score  | `lease_expires_at` |

Admission always verifies active organization state, protects settlement backlog, cleans old leases, and adds the new generation with `ZADD NX`. For `prepaid`, it additionally requires a positive remaining balance, counts unexpired members, derives `balance_funded_limit = ceil(balance / balance_per_concurrency_slot)`, and selects `min(prepaid_organization_concurrency_cap, balance_funded_limit)`; the launch-wide prepaid cap defaults to 50. For `invoiced`, it ignores balance and skips the organization concurrency check. SGLang's bounded runtime capacity remains the ultimate ceiling and may reject excess admitted demand with `429`.

The prepaid inputs are operational deployment configuration, not customer-facing product controls. `balance_per_concurrency_slot` only converts prepaid balance into a concurrency count; it is not a reservation, request-cost estimate or hard downside bound. Admission does not compare a prepaid request's theoretical maximum charge with the current balance or per-slot amount because that would reject ordinary requests whose requested output ceiling is rarely reached. No money is reserved and the lease remains only a generation ID plus expiry. Concurrent prepaid generations can move the balance below zero before their terminal charges become visible, and subsequent prepaid requests are blocked until a top-up or operator credit makes the balance positive. Invoiced usage drives its accounting balance negative without affecting admission; suspension is the explicit stop.

At admission, Rust fixes `lease_expires_at` to the gateway's hard total-generation deadline plus a short finalization margin. It does not renew or extend the lease. Normal success, failure or cancellation finalizes and removes it immediately. If the process disappears, the orphaned lease consumes concurrency until that fixed expiry; expired members then stop counting and remain for a short grace period before cleanup so delayed finalization can still succeed. This accepts slower slot recovery after a process crash in exchange for eliminating a heartbeat and renewal-failure path. Terminal finalization is a versioned server-side Lua script invoked with `EVALSHA`: remove the member, subtract the actual charge from `GatewayAccount.balance`, and append exactly one `GenerationSettled` event. If the member is already absent, the script performs no financial or stream mutation. This makes the lease itself the idempotency boundary even when a successful command response is lost; no `settled:<generation_id>` key is required.

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
- a generic fleet registry beyond the explicit `model_deployments` rows
