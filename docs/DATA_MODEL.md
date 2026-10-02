# Data model

- status: current implementation authority
- date: 2026-08-15
- architecture: [ARCHITECTURE.md](ARCHITECTURE.md)

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
- Prompts and responses are kept only when a workspace enables trace capture,
  as generation contents in regional S3 batches with 90-day default retention. No
  database table holds them. See [TRACES_PLAN.md](TRACES_PLAN.md).
- Organization membership is the human authorization boundary. Workspaces are
  policy and cost-attribution boundaries available to all active members.
- Prepaid and invoiced organizations share the same account, lease,
  finalization, and settlement records. Billing mode changes admission:
  prepaid balance limits serving, while invoiced balance is accounting-only at
  launch. All internal monetary values use integer nano-USD.

## Global conventions

- Application IDs are UUIDv7. Public model IDs are stable bounded lowercase
  text identifiers. The gateway converts request model IDs to ASCII lowercase
  before lookup.
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
| `trace_capture_enabled` | boolean | no | Opt-in content capture; defaults to false |
| `trace_retention_days` | smallint | no | 30, 90 or 180; defaults to 90 |
| `created_at`      | timestamptz | no   | Creation time                                           |
| `updated_at`      | timestamptz | no   | Last mutation time                                      |

In addition to the primary key, `workspaces` has a unique `(organization_id, id)` constraint. `api_keys(organization_id, workspace_id)` references that composite key, so PostgreSQL enforces that an API key and its workspace belong to the same organization rather than relying only on application checks.

A workspace is a policy and cost-attribution boundary, not an authorization boundary. Active organization members can access every workspace in their organization. Each organization is created with one default workspace; the product can hide workspace selection while only that workspace exists.

Workspaces group API keys, usage and captured generation content. Every unarchived workspace can access every active hosted model, with no workspace spend, rate or concurrency limits. Future model allowlists and per-model limits belong in a workspace-model policy table rather than on API keys.

Content capture is disabled by default. Organization owners and admins can enable relay capture and choose retention. Retention changes apply only to new captures. Content reads enforce the retention recorded on each generation; S3 lifecycle expires batches by their retention tags. Archiving disables capture and blocks reads immediately. The worker deletes archived or deleted workspace content asynchronously, including late collector writes. See [TRACES_PLAN.md](TRACES_PLAN.md) for the storage and capture contract.

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

Global hosted-model catalog. It is not organization-scoped. The primary key is the immutable human-readable model identifier used in direct requests and returned to OpenRouter, for example `google/gemma-4-31b-it`.

| Field        | Type        | Null | Rules                                        |
| ------------ | ----------- | ---- | -------------------------------------------- |
| `id`         | text        | no   | Primary key; lowercase immutable public model ID |
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

The public API offers `flex`, `default`, and `fast` service tiers. The stored
model prices are the `default` prices. The gateway derives each effective
nano-USD unit price before admission. It uses `floor(default * 7 / 10)` for
`flex`, the stored price for `default`, and `floor(default * 3 / 2)` for
`fast`. It applies the ratio independently to `prompt`, `cached_prompt`,
`cache_write`, `completion`, and `internal_reasoning`. A derived unit price can
be zero. The Models API returns this global policy with the model catalog.

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

PostgreSQL is authoritative for identity, the catalog and prices, and the gateway reads it through a Valkey cache. Every change, restrictive or permissive, is a committed PostgreSQL write and needs no serving-state write beside it. A restriction takes effect once the cached record's lifetime elapses, so revocation, suspension, model unavailability and price changes are bounded by that lifetime rather than by a projection succeeding. Key creation, model creation and top-ups are visible as soon as they commit, because a record PostgreSQL does not have is never cached. Invoiced balance movements remain accounting changes and do not change serving admission.

No reconciliation loop is required for identity, the catalog or prices: a Valkey loss costs cache misses, and the next read repopulates from PostgreSQL. The operational balance is the exception, because settlement moves it in Valkey before it posts to PostgreSQL. The gateway seeds an absent account hash from `billing_accounts.balance`, stores the source timestamp that seed included, and applies later ledger entries past that watermark exactly once.

PostgreSQL-originated money changes reach the operational balance through the gateway, from immutable `balance_transactions` and a versioned Lua script. The script atomically adds the PostgreSQL transaction ID to `AppliedBalanceTransactionIds` and changes `GatewayAccount.balance` only when the ID was newly added, so a repeated or concurrent apply cannot count the same top-up, payment, refund, chargeback or operator adjustment twice. It reads past a watermark that only moves forward and never overwrites an operational balance containing terminal usage not yet posted to PostgreSQL. A top-up therefore lands on the organization's next request, which is the only moment the balance has to be right. Valkey-originated `generation_settlement_batch` postings do not echo back into Valkey and are never added to this set because Rust already applied their charges.

The reconciler exports its last-success time, failures and mismatches as metrics. Missing or unavailable required projection state rejects every request. Do not add CDC, Debezium, Kafka, a projection queue or a standalone projector at launch.

## 13. `model_deployments`

Durable registry of concrete runtime deployments for hosted models. One model
may have multiple rows. The gateway combines these rows with fresh deployment
status from Valkey. It uses rendezvous hashing for stable placement and one
shared concurrency lease for admission.

| Field          | Type        | Null | Rules                                                     |
| -------------- | ----------- | ---- | --------------------------------------------------------- |
| `id`           | uuid        | no   | Primary key; stable deployment identity                   |
| `model_id`     | text        | no   | FK `models.id`                                            |
| `status`       | text        | no   | `available`, `unavailable`, `draining`                    |
| `provider`     | text        | no   | GPU provider identifier                                   |
| `region`       | text        | no   | Provider region identifier                                |
| `fault_domain` | text        | no   | Failure boundary used for retry placement                 |
| `service_url`  | text        | no   | Bounded private or restricted absolute HTTP(S) runtime URL |
| `release`      | jsonb       | no   | Closed Zod `ModelDeploymentRelease` document              |
| `created_at`   | timestamptz | no   | Creation time                                             |
| `updated_at`   | timestamptz | no   | Last durable mutation                                     |

`ModelDeploymentRelease` contains `schema_version`, initially `1`, plus
`runtime_revision`, `model_path`, `model_revision`, `tokenizer_path`, and
`tokenizer_revision`. All identifiers are required and bounded even when the
tokenizer identity equals the model identity. `runtime_revision` is a native
SGLang source revision locally and an immutable runtime release identifier in
production. An explicit `protocol` of `system_one` selects native SystemOne
transport, and an absent `protocol` means the ordinary OpenAI chat transport;
it must identify the pinned Kev release and cannot serve Chat Completions.
This transport discriminator is included in the release digest, not stored in
an additional routing record.
Rust serializes this typed object canonically and hashes only it to produce the
`served_release_digest` captured by each admitted generation.

There is no generic deployment metadata. A field that affects routing,
availability, capacity, compliance, or cost becomes an explicit column or part
of another closed versioned document. Volatile status remains in Valkey. It is
not a durable PostgreSQL field.

Git continues to own the Kubernetes/SGLang workload declaration that creates a
deployment. The deployment workflow registers the resulting route and exact
release in PostgreSQL only after the endpoint is ready, and marks the old row
`draining` before removal. Secret values and secret-location indirection never
appear in this table; the gateway reads the optional upstream credential from
the fixed `SGLANG_API_KEY` process secret. One gateway-wide hard generation
timeout applies to every model and defaults to 630 seconds.

Chat deployments support all three service tiers. Native SystemOne currently
supports only `default`; requests for `fast` or `flex` are rejected because
its tier scheduler is not implemented. Do not add service-tier
capability fields to `model_deployments`. The tiers share the same deployment
pool, release, capacity lease, and retry candidates. The runtime scheduler uses
request priority to give `fast` work precedence over `default` work and
`default` work precedence over `flex` work.

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
  service_tier: "flex" | "default" | "fast",
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

Version 2 requires `service_tier`. Version 1 omits it and means `default`.
Native SystemOne uses this same generation event with `service_tier: "default"`.
Its authoritative prefill usage has nonnegative safe-integer input tokens and
cached input no greater than input. Output, cache-write and reasoning quantities
are zero; answer serialization is not generated-token usage. No new event or
storage table is required. State, questions and answers remain request-local.
The optional 1..256 UTF-16-code-unit session ID selects affinity; otherwise the
gateway hashes the first 16 KiB of serialized state, scoped to workspace, model
and served release. Neither state nor session affinity introduces durable
customer-content storage.

`pricing` contains every effective price component used for the generation,
including configured zero-quantity or zero-price components. Terminal generation
units remain normalized as `input_token`, `cached_input_token`,
`cache_write_token`, `output_token`, or `reasoning_token`; model-catalog pricing
types map from `prompt`, `cached_prompt`, `cache_write`, `completion`, and
`internal_reasoning` respectively. Under the global nano-USD convention, each
component's `amount` is exactly `quantity * unit_price`, and all component
amounts sum exactly to `usage.charge`. Service-tier unit-price adjustment uses
the floor rule before this multiplication. No later monetary rounding occurs.
This preserves the complete billing calculation when the global model price
later changes without copying unrelated model descriptions, capabilities,
capacity, or availability.

The application validates the complete properties document before insertion; it is not arbitrary JSON. New optional properties and new closed schema versions do not require a ClickHouse table migration. The initial materialized columns exist because they define tenant filtering, ordering, common status filtering or PostgreSQL settlement. Add another materialized column from a JSON path only when a measured filtering, grouping or indexing pattern justifies it. The original value remains in `properties`, so a materialization is a query optimization rather than another source of truth.

One TypeScript ClickHouse-ingestion consumer group reads `GenerationSettled` from Valkey. For each event it derives the global `settlement.slot_id` from the Valkey Stream ID's time bucket and settlement schema. Every organization in that time bucket receives the same slot ID; ClickHouse materializes it for chronological reconciliation. The worker issues one logical insert per generation with ClickHouse `async_insert = 1` and `wait_for_async_insert = 1`; ClickHouse combines those inserts server-side. Retries use a generation-ID-based insert deduplication token as a normal-path optimization, but billing correctness never depends on the lifetime of that token. The worker acknowledges a stream entry only after ClickHouse confirms the asynchronous insert was flushed, uses `XAUTOCLAIM` to recover abandoned pending entries, and trims only through the contiguous acknowledged watermark. That watermark is derived from the consumer group's last-delivered ID and oldest pending ID rather than stored in another database table. Do not use `ReplacingMergeTree`, lifecycle updates or `FINAL` queries for the launch schema.

Do not store prompts, completions, arbitrary request JSON, credentials, private runtime URLs, or attempt arrays. One customer-visible generation can have one safe runtime retry. Generations have no TTL and are retained indefinitely at launch. Rely on ClickHouse Cloud's managed durability and backups initially; do not build a separate archival or export pipeline until retention, regulatory or recovery requirements justify one.

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
`status`, `provider`, `region`, `fault_domain`, `service_url`, and the closed
`ModelDeploymentRelease`. The projector replaces the complete document with
one `SET`. `gateway-model-ids` is the enumeration index for readiness and
`/v1/models`.

The gateway caches this projection in memory for one second. A miss reloads it
from Valkey. A missing route fails closed.

## 20. `DeploymentRuntimeStatus`

Valkey key: `deployment-status:{<served_release_digest>}`. This is a hash. The
field is `deployment_id`. The value is one closed status document.

The document contains `deployment_id`, `runtime_revision`, `received_at`,
`healthy`, `accepting_requests`, and `reason_code`.
`accepting_requests` reports runtime safety only: KV pressure and draining.
It is not a concurrency limit. The engine owns admission.
The reader ignores unknown fields so a newer producer cannot break an older
gateway. A malformed document drops only its own deployment.
Desmond sends it every second. The ingest service checks provider ownership and
the durable runtime revision before it writes the field.

Timing values, as implemented:

| Stage | Value |
| ----- | ----- |
| Desmond send interval | 1 second |
| Gateway in-memory status cache | 1 second |
| Gateway accepts status age | 15 seconds |
| Valkey key TTL | 30 seconds |
| Desmond ready gate after last upload | 10 seconds |
| Future-dated tolerance | 5 seconds |

The key TTL is longer than the acceptance window. The gateway staleness check is
the binding limit, so the key can outlive its usability. The gateway also
rejects a `received_at` more than five seconds in the future.

## 21. `InFlightGenerationLease`

Valkey key at seed: `inflight:{settlement-0}:<organization_id>`. This is a sorted set, not a row or hash.

| Part   | Value              |
| ------ | ------------------ |
| member | `generation_id`    |
| score  | `lease_expires_at` |

Admission always verifies active organization state, protects settlement backlog, cleans old leases, and adds the new generation with `ZADD NX`. It counts unexpired members and rejects at `organization_concurrency_cap`, which defaults to 50 and applies to every billing mode. For `prepaid`, it additionally requires a positive remaining balance, derives `balance_funded_limit = ceil(balance / balance_per_concurrency_slot)`, and selects `min(organization_concurrency_cap, balance_funded_limit)`. For `invoiced`, it ignores balance. SGLang's bounded runtime capacity remains the ultimate ceiling and may reject excess admitted demand with `429`.

The prepaid inputs are operational deployment configuration, not customer-facing product controls. `balance_per_concurrency_slot` only converts prepaid balance into a concurrency count; it is not a reservation, request-cost estimate or hard downside bound. Admission does not compare a prepaid request's theoretical maximum charge with the current balance or per-slot amount because that would reject ordinary requests whose requested output ceiling is rarely reached. No money is reserved and the lease remains only a generation ID plus expiry. Concurrent prepaid generations can move the balance below zero before their terminal charges become visible, and subsequent prepaid requests are blocked until a top-up or operator credit makes the balance positive. Invoiced usage drives its accounting balance negative without affecting admission; suspension is the explicit stop.

At admission, Rust fixes `lease_expires_at` to the gateway's hard total-generation deadline plus a short finalization margin. It does not renew or extend the lease. Normal success, failure or cancellation finalizes and removes it immediately. If the process disappears, the orphaned lease consumes concurrency until that fixed expiry; expired members then stop counting and remain for a short grace period before cleanup so delayed finalization can still succeed. This accepts slower slot recovery after a process crash in exchange for eliminating a heartbeat and renewal-failure path. Terminal finalization is a versioned server-side Lua script invoked with `EVALSHA`: remove the member, subtract the actual charge from `GatewayAccount.balance`, and append exactly one `GenerationSettled` event. If the member is already absent, the script performs no financial or stream mutation. This makes the lease itself the idempotency boundary even when a successful command response is lost; no `settled:<generation_id>` key is required.

The script executes without interleaving, which supplies the required conditional atomicity; `MULTI`/`EXEC` alone cannot branch on whether lease removal succeeded. Valkey scripts are not rollback transactions, so the script validates arguments and key types before its fixed writes and the application exclusively owns those key shapes. Valkey Cluster hashes only the text inside braces, so the shared `{settlement-0}` tag places `account:{settlement-0}:<organization_id>`, `inflight:{settlement-0}:<organization_id>` and `generation-settled:{settlement-0}` in the same cluster hash slot. Credential, workspace and model keys are read outside this script and do not need that tag.

Seed runs one settlement shard. Later horizontal scaling assigns each organization to a stable shard and uses the same tag for all three keys, for example `account:{settlement-7}:<organization_id>`, `inflight:{settlement-7}:<organization_id>` and `generation-settled:{settlement-7}`. Changing shard assignment is an explicit drained migration rather than an implicit modulo change.

The lease intentionally contains no request metadata. Rust carries the authenticated identities, model release, actual usage, admission-time prices and timing through the live request. It uses those captured nano-USD prices to calculate `properties.usage.charge` and emits the exact pricing snapshot and changing terminal details inside `GenerationSettled.properties`. `generation_id` identifies the durable ClickHouse row. The ClickHouse consumer adds the global settlement slot, and the PostgreSQL worker derives the per-organization source ID as `<settlement_slot_id>:<organization_id>`. The Valkey Stream has its own transport entry ID, so there is no separate event UUID. A process loss may leave an unbilled generation that expires without a terminal analytics row. That bounded revenue and observability loss is accepted at launch in exchange for eliminating monetary reservations and durable in-progress request state.

## 23. `AppliedBalanceTransactionIds`

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
- `recommendations`
- `evaluations`
- `capacity_sources`
- `capacity_targets`
- `allocations`
- `allocation_members`
- `cells`
- all research program, campaign and experiment tables
- a custom scheduler or a second store of Nomad allocation state

## Instance inventory (migration pending)

The Nomad pilot adds `instances` in migration 0005. One row represents one
provider pod or machine. Provider, account, and provider instance ID form the
unique provider identity. Region and fault domain can be unknown. `sku` identifies
the hardware offering, such as `4xb300` or `cpu-32vcpu`.

The nullable, unique `nomad_node_id` links the inventory record to Nomad.
Creation and update timestamps describe the record. Retirement additionally
blocks GPU certificate renewal. Credential issuance and revocation are stored
separately. Nomad owns
device discovery, scheduling eligibility, resource availability, and allocations.

The optional `model_deployments.instance_id` foreign key preserves manual deployment
compatibility. It does not assign jobs to hosts. The control service can register
inventory and set or clear a Nomad node link. Authentication and verification of
that link remain pending. The application database migration remains pending.

Migration 0011 adds nullable `instances.certificate` JSONB state.
It holds `tokenHash` (the separately enrolled renewal-token SHA-256 digest), authorized
Nomad node ID, revocation time, last successful issuance time, and last
host-reported installed certificate expiry (`expiresAt`), renewal due time
(`renewalDueAt`), and heartbeat (`observedAt`). JSON dates are ISO-8601 strings
validated with the shared certificate schema. Inventory responses omit this field. No private key or raw
renewal token is stored. Renewal requires a non-retired instance, the current
node binding, and a matching unrevoked credential. Re-enrollment replaces the
credential. The instance row is locked through signing, so revocation and
retirement serialize with issuance; failed signing rolls back the issuance
limit. Monitoring includes active bound hosts without credentials so unenrolled agents
cannot disappear from alerts. Host reports support overdue-renewal, expiry, and
missing-agent alerts, and do not attest
to host integrity. See the Nomad README for rollout and compromise limits.

## Task training

Migration 0008 adds workspace-owned `tasks`, named uniquely within a workspace.
Task names cannot be `.` or `..`, because task routes use the name as a URL path
segment. The collector registers a task when it accepts its first captured trace,
using an idempotent insert keyed by workspace and task name. PostgreSQL outages
do not block capture or uploads: pending registrations remain on local disk and
retry in the background, including after process restart. A bounded one-hour
in-memory cache avoids repeated writes for known tasks. Task listing reads
PostgreSQL directly and never discovers or creates tasks from trace storage.

Migration 0009 adds a nullable `training_schedule` cron expression to each task.
Expressions have five fields and use UTC; null disables automatic training.
Defaults are weekly, with minute, hour and weekday sampled once at insertion
and stored durably. Task updates save the PostgreSQL configuration and directly
attempt to create, update or delete the per-task Temporal Schedule. Temporal
failures are logged without rolling back PostgreSQL; resubmitting task settings
retries the schedule update. Workspace and organization eligibility is checked
when the scheduled workflow runs.

`training_runs` belong to a task and record the trigger, requester, base model,
input cutoff, stage, dataset summary and evaluation summary. The internal
`workflow_id` records the exact Temporal execution identity for cancellation;
older records use the per-task workflow ID fallback. A partial unique index
permits only one unfinished run per task and arbitrates concurrent manual and
scheduled admission. Training reads reject archived
workspaces immediately, before reading traces or tasks.

`training_run_events` belong to a run and have monotonically increasing IDs for
pagination. Their source names the emitting service. Workflow lifecycle events
and recovery checkpoints have typed payloads; trainer observations carry an
extensible name, message, metrics and details. Observations cannot authorize
workflow transitions. See [the run contract](TASK_FINE_TUNING_RUN_CONTRACT.md).

`task_versions` reference their workspace, task and training run. Composite
foreign keys require that the workspace owns the task and that the run belongs
to that same task. Each run produces at most one version; version names are
workspace-unique. Adapter metadata records an immutable URI, digest, byte size,
format and rank. Large artifacts and datasets remain in object storage.

The task's production-version pointer is changed explicitly by an editor, only
to an available version of the same task. Promotion uses last-write-wins semantics
for concurrent authorized requests. Availability means durable serving eligibility,
not residency in an inference runtime's adapter cache. Comparison model IDs may
name external providers; they are not restricted to the hosted-model table.
Executor-specific support is checked when admitting a run.

Workspace `default_judge_model` seeds `tasks.judge_model_id` when a task is first captured. Each task can override its judge independently; changing the workspace default never rewrites existing tasks. Migration 0013 renames the workspace field and backfills existing tasks from their workspace’s current default. Training admission snapshots the saved task judge.

## Private LoRA serving

Private LoRA inference reuses `task_versions` for workspace ownership, immutable
artifact URI/checksum/rank and durable serving eligibility. The existing
`tasks.production_version_id` is the production selector. There are no additional
hosting-intent or promotion-audit tables. Cache residency belongs to each serving
allocation and is recovered lazily after a process restart.

Qualified runtime configuration pins the base/runtime/tokenizer release, TP
geometry, supported target modules and cache/admission limits. See
[the implementation stack](LORA_HOSTING_PR_STACK.md).
