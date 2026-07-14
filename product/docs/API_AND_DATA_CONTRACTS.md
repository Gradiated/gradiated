# Simplified API and data contracts

## Authority map

| Fact | Authority | Projection/artifact |
| --- | --- | --- |
| identity/session | Better Auth tables in PostgreSQL | signed session cookie |
| organizations/workspaces/members/keys | PostgreSQL | bounded Valkey serving snapshots |
| prepaid credit and settled usage | PostgreSQL double-entry ledger/balance/usage records | Valkey hot balance/reservations/billing stream |
| model catalog/releases/aliases | PostgreSQL immutable releases | Valkey alias/release snapshots |
| retained trace authorization/metadata | PostgreSQL | encrypted S3 object; Valkey trace stream/grant nonce |
| capacity targets/allocations/members/cells | PostgreSQL | ephemeral authenticated in-memory router registry |
| research experiments/jobs/bundles/qualification | PostgreSQL | S3 CAS/reports and ECR images |
| research workflow execution/timers/retries | Temporal | PostgreSQL domain IDs and S3 artifact refs |
| customer usage/workload analytics | PostgreSQL indexed queries/rollups | none at seed |

ClickHouse, fleet CRDs and Kubernetes etcd are not application authorities or seed dependencies. Temporal is a seed execution dependency but never evidence, budget or release authority.

## Public APIs

### Customer control API

The Vite application, CLI and automation use the versioned Hono REST API under `/api/v1`. Described Zod v4 request/response schemas generate the OpenAPI 3.1 artifact, Scalar reference, typed TypeScript client and an explicitly allowlisted MCP adapter. There is no tRPC surface or second MCP business implementation. The complete route, description, error, generation and authorization contract is [REST, OpenAPI and MCP](REST_OPENAPI_MCP_IMPLEMENTATION.md).

Every protected call receives organization/workspace context from the authenticated session or short-lived OAuth token. URL/body IDs select a resource but never establish authority. Unsafe cookie-authenticated calls enforce Origin/Fetch Metadata and CSRF policy. Stripe webhook remains raw-body signed REST. Every externally visible schema property, operation and error must be described and example-checked in generated OpenAPI.

### Public inference API

Wire authority is versioned JSON/OpenAPI plus golden fixtures. Launch `GET /v1/models`, OpenAI Responses Create and Anthropic Messages, streaming and non-streaming. Chat Completions, Embeddings, Google GenerateContent and other hosted-product surfaces are deferred. Unsupported fields/capabilities fail before admission; internal Protobuf never defines public JSON behavior. The exact stateless Responses and Messages profiles are [specified here](PUBLIC_INFERENCE_PROTOCOLS.md).

### Native channel API

OpenRouter uses the normal public inference path with a channel credential plus a channel-authenticated catalog renderer. Channel credentials never work at inference router/cells or the management REST/MCP surface.

## Minimal PostgreSQL schema

The exhaustive required-field and removal rationale is [the simplicity review](../../docs/SIMPLICITY_REVIEW.md#minimal-persistent-model). Canonical seed tables are:

```text
Better Auth user/session/recovery/OAuth-provider tables
organizations, organization_members, invitations, organization_deletions
workspaces, workspace_members, workspace_models, api_keys
organization_balances, channel_balances, ledger_accounts, ledger_transactions, ledger_entries
topup_intents, payment_events, usage_records, channel_usage_records
provider_endpoints, model_definitions, model_releases, release_endpoints
model_aliases, qualification_runs
traces, recommendations, evaluations
distribution_channels, channel_credentials, channel_catalog
channel_statements                         # only with first native contract
capacity_sources, capacity_targets, allocations, allocation_members, cells
research_programs, research_hypotheses, research_campaigns
experiment_specs, experiment_runs, evidence_reports
bundles, bundle_qualifications
outbox, audit_records
```

Rules:

- USD integer micro-units only at seed; JavaScript uses `bigint`, Rust/Python checked integer types.
- Tables use explicit foreign keys and unique business/idempotency keys. Tenant indexes start organization/workspace.
- Exactly one Default workspace per organization; key organization must match workspace; workspace membership requires organization membership.
- Organization deletion is a self-service, idempotent workflow that suspends admission immediately, reconciles/refunds money, destroys payload keys and preserves only pseudonymized legally required financial evidence.
- No free-form metadata column without an implemented bounded consumer. Validated JSON is used only for release capabilities, bounded usage-attempt summaries, evaluation authority/stops/results, bounded research scopes/specifications and immutable provider statements.
- Mutable operational rows are allowed for usage/job/allocation status; money/evidence artifacts remain append-only or content-addressed.
- Every new field must name its writer, reader, retention, migration default and property/example test.

## Credit and usage contract

Use a fixed-chart append-only double-entry ledger. `organization_balances` is a locked, transactionally updated and rebuildable projection of the customer-credit account.

Invariant:

```text
every ledger transaction sums to zero by currency
customer_credit_liability balance
  = organization_balances.available_micros + currently_held_in_Valkey
```

Valkey reserves/holds synchronously; PostgreSQL receives reservation and settlement events asynchronously. Reconciliation compares PostgreSQL settled truth plus active reservation evidence with the projected epoch and fail-closes the organization before repair if equality cannot be proven.

`usage_records` owns one organization request's operational identity, admitted release, bounded attempt summary, terminal usage and sell amount. `channel_usage_records` owns the corresponding channel/credential/release/external-model facts without nullable customer principal columns. Usage, corrections, refunds and chargebacks are immutable balanced transactions linked by source fields; there is no mutable charge/correction hierarchy.

## Cross-language contracts

Use Protobuf only where at least two runtime languages exchange a hot/streaming contract:

```text
product/proto/gradiated/
  gateway/v1/
    snapshots.proto     # key/workspace/account/release snapshots
    billing.proto       # ReservationCreated, UsageSettled
    traces.proto        # encrypted trace envelope metadata
  inference/v1/
    serving.proto       # GenerateRequest/Event
    registration.proto  # authenticated cell registration/heartbeat
  research/v1/
    service.proto       # private Hono/Python commands and views
    refs.proto          # program/spec/run/evidence/bundle references
```

Remove model-family/candidate/rollout, generic principal/event, migration, Temporal-history and fleet-CRD Protobuf packages. TypeScript-only domain/outbox payloads are typed TS/Zod/JSON. Research API commands/refs use generated Protobuf; research domain state is PostgreSQL and workflow execution is Temporal.

Rules:

- package root is `gradiated`; reserve removed Protobuf fields/numbers;
- timestamps use standard Timestamp and money is checked signed `int64` micros;
- generated TypeScript/Rust (and Python only if a real consumer exists) are committed and drift-checked;
- public inference JSON is never generated from internal Protobuf;
- Redis stream fields keep inspectable event ID/type/version while binary payload is explicitly encoded.

Generation uses pinned Buf/Prost/Protobuf-ES. `contracts:check` formats/lints, compares breaking changes, regenerates, checks Git drift and runs cross-language goldens. Do not generate a language client that has no consumer.

## Serving snapshots

Minimal Valkey keys are defined in the [gateway blueprint](GATEWAY_IMPLEMENTATION.md#valkey-model). Snapshots flatten PostgreSQL joins so the gateway performs no relational work:

- organization account: status, available/held and epoch/version;
- workspace: status, data mode, monthly spend/limit, concurrency, model allowlist and version;
- key/channel credential: digest binding, status and optional tighter monthly/concurrency limits;
- alias: stable/canary digest and generation;
- release: immutable capabilities/prices/direct endpoints or owned marker and retry count.

Projection updates use monotonically increasing source versions. The projector may rebuild all keys from PostgreSQL under a new epoch; gateway rejects mixed/incompatible epochs. No projection has a second durable meaning.

## Serving events

There is no universal `PrincipalRef` or aggregate envelope.

```text
ReservationCreated
  event_id, request_id, reservation_id
  organization_id, workspace_id, api_key_id
  requested_model_id, release_digest
  reserved_micros, started_at, expires_at

UsageSettled
  event_id, request_id, reservation_id
  organization_id, workspace_id, api_key_id
  release_digest, actual_target
  input/cached_input/output tokens
  sell_micros, buy_micros?, attempts_json
  terminal_status, usable_output_delivered, cancellation_owner?
  completed_at
```

Channel variants replace organization/workspace/key with channel/credential. Each payload contains only fields consumed by usage posting, failed-request credit policy and reconciliation. Attempts remain one bounded typed JSON summary on `usage_records`; provider secrets, raw provider bodies and customer payload never enter billing events.

## Gateway-to-cell contract

```text
GenerateRequest
  request_id, attempt_id, release_digest
  canonical_input, max_output_tokens, deadline
  cache_scope, traceparent

GenerateEvent
  output_delta(sequence, bytes)
  usage_update(input_tokens, cached_input_tokens, output_tokens)
  completed(finish_reason, authoritative_usage)
  failed(code, retryable_before_output, authoritative_usage_if_known)
```

Release digest determines public product, effort/speed, bundle, capabilities and placement. Billing IDs, data mode, queue deadline, public model ID and provider lifecycle objects are forbidden. Cache scope is opaque. Events and cumulative usage are monotonic; no retry after usable output.

## Bundle contract

RFC 8785-canonical generic artifact, checkpoint, runtime and bundle manifests plus an immutable qualification report are authoritative. Required fields are in [the artifact contract](../../docs/SIMPLICITY_REVIEW.md#artifact-and-runtime-contract). Bundle identity excludes timestamps, experiment/campaign IDs, qualification, pricing, rollout and mutable status.

S3 object refs are content-addressed. Runtime image is an ECR digest and implements the local serving protocol; its language is not modeled. Bundle/report/image signatures/provenance protect the execution boundary without signing every component independently.

## Trace contract

Gateway envelope contains trace/request/tenant IDs, capture policy/version, ciphertext, wrapped data key, nonce/algorithm/key ID, bounded safe metadata and created/expiry. The trace worker stores ciphertext in S3 and metadata/key state in PostgreSQL. No plaintext enters Valkey, PostgreSQL, logs or analytics.

No-retention emits no payload but usage remains. Trace detail authorization checks PostgreSQL membership/deletion, issues a short-lived signed single-object grant and consumes its nonce once in Valkey. Deletion destroys the wrapped key and object; usage facts remain unless the [organization-deletion policy](ORGANIZATION_DELETION.md) removes or pseudonymizes them. Organization deletion also rotates cache scope so old ephemeral KV state is unreachable before TTL/drain cleanup.

## PostgreSQL analytics contract

Hono accepts a closed query object: organization/workspace from auth, bounded time range, cursor, model/status filters and predeclared aggregate. Repositories use fixed SQL with limits/timeouts; no browser SQL/column expressions.

Seed queries read `usage_records` and `traces`. If measured volume requires it, add date partitioning and a small daily/hourly rollup in PostgreSQL. ClickHouse can be reconsidered only after those changes fail a recorded SLO/cost benchmark.

## Schema evolution

- Expand first: nullable/defaulted field or new table, dual-read only when necessary, backfill with checkpoint, then enforce.
- Never repurpose an enum/string meaning or Protobuf number.
- Immutable release/bundle/event versions remain readable for their support/retention lifetime.
- Destructive migrations require backup/restore evidence and one-release delay.
- Contract fixtures include previous-version decode and unknown/additive fields.

## Verification

Properties cover tenant foreign keys, Default workspace uniqueness, self-service organization deletion/refund/purge, balanced transactions/credit projection/reconciliation equality, event idempotency/reorder, snapshot epoch rebuild, REST/OpenAPI/MCP generation and authorization, both launch inference protocols, alias canary determinism, trace encryption/delete, Temporal replay/domain reconciliation, single/multi-node allocation leases/member cleanup, canonical manifest digests and cross-language serving events.

The schema is complete when every persisted field has a writer, reader and test—not when it models every future possibility.
