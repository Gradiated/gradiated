# Cross-system contract catalog

Status: canonical interface inventory

This catalog tells implementation agents exactly where two packages or services meet. Public JSON behavior is owned by OpenAPI/JSON fixtures. Internal cross-language messages are owned by Protobuf. Database rows, Valkey keys and object manifests are not service APIs unless explicitly listed.

## 1. Contract rules

1. One contract has one source file and one owner package.
2. Public inference JSON is never generated from internal Protobuf.
3. Control REST Zod schemas generate OpenAPI and clients; there is no handwritten duplicate DTO.
4. Internal Protobuf uses Buf lint/breaking checks and checked-in TS/Rust/Python generated code.
5. Artifact manifests use canonical JSON plus JSON Schema because their bytes are content-addressed.
6. Money is signed `int64` micro-USD with checked arithmetic; token/count values are unsigned bounded integers.
7. IDs are opaque strings at public boundaries and strongly typed wrappers internally.
8. Every mutation and event defines idempotency, retry, authorization and terminal behavior.
9. Unknown enum/message variants fail safely. Senders do not emit a new required field until all readers are compatible.
10. Every contract has golden fixtures for valid, boundary-invalid and unknown-field/version behavior.

## 2. Planned contract layout

```text
product/proto/
  buf.yaml
  buf.gen.yaml
  gradiated/gateway/v1/snapshots.proto
  gradiated/gateway/v1/billing.proto
  gradiated/gateway/v1/traces.proto
  gradiated/inference/v1/serving.proto
  gradiated/inference/v1/registration.proto
  gradiated/research/v1/service.proto
  gradiated/research/v1/refs.proto

product/openapi/
  control-v1.json

product/schemas/
  inference/openai-responses-create.schema.json
  inference/anthropic-messages-create.schema.json
  inference/models.schema.json
  artifacts/model-source.schema.json
  artifacts/checkpoint.schema.json
  artifacts/operator.schema.json
  artifacts/runtime.schema.json
  artifacts/topology.schema.json
  artifacts/bundle.schema.json
  artifacts/qualification.schema.json

product/fixtures/contracts/
  control/
  billing/
  trace/
  inference/
  cell/
  research/
  artifacts/
```

Generated files live under language-specific `gen/` directories, are checked in and carry the source digest/tool version. CI regenerates in a clean tree and requires no diff.

## 3. Shared representation rules

`gradiated` is the internal Protobuf package namespace; `grad` remains the product, CLI and public model prefix. Keep value messages package-local unless two real packages exchange them; do not create a speculative common-domain package. The following representations apply wherever used:

| Type | Fields/representation | Rules |
| --- | --- | --- |
| `OpaqueId` | `string value` | non-empty, bounded ASCII; domain wrapper validates kind |
| `Digest` | algorithm enum + bytes | seed algorithm SHA-256; rendered `sha256:<hex>` |
| `MoneyMicros` | `int64 value`, currency enum | seed currency USD only; checked add/sub/mul |
| `UtcTimestamp` | protobuf timestamp | UTC, bounded sane range |
| `TokenUsage` | input, cached-input, output token counts | missing is distinct from zero at public adapters |
| `DataMode` | product-intelligence, no-retention | request may only tighten workspace mode |
| `Protocol` | OpenAI Responses, Anthropic Messages | Models is query-only, not a generation protocol |
| `ReleaseRef` | immutable digest + public model ID + alias generation | digest is routing/billing identity |

Do not add organization, actor, correlation or metadata envelopes to all messages. Each message carries only identifiers its consumer uses.

## 4. Control REST contract

### 4.1 HTTP conventions

| Concern | Contract |
| --- | --- |
| base path | `/api/v1` |
| media | JSON UTF-8 except bounded usage CSV, trace detail stream and Stripe raw webhook |
| success | resource body or documented `204`; never ad hoc `{ success: true }` |
| error | problem details with `type`, `title`, `status`, stable `code`, `request_id`, optional described `fields` |
| pagination | opaque cursor + bounded `limit`; response has `items`, `next_cursor` |
| time | RFC 3339 UTC strings |
| money | decimal string micro-USD in JSON; generated client wrapper converts to bigint |
| idempotency | `Idempotency-Key` on routes marked required; normalized bounded opaque value |
| concurrency | ETag/version only on resources with a real lost-update command |
| authentication | secure Better Auth cookie; OAuth bearer for MCP; internal deployment identity for operator routes |
| organization/workspace | selected from server context/path and reauthorized; never trusted from a browser claim |
| request IDs | accepted/generated at edge, returned in headers and safe errors |

Every operation registration must describe purpose, actor, preconditions, side effects, idempotency/retry and sensitive output. Every exposed schema field must retain `.meta({ description, examples })` after final refinement. The generated OpenAPI description gate walks parameters, bodies, responses, components and nested properties.

### 4.2 Seed route groups

Exact path naming is owned by `product/apps/control/src/http/routes`. The operation set is fixed here:

| Group | Required operations | MCP exposure |
| --- | --- | --- |
| session | current session/user/organization context; reauthentication challenge | read current context only |
| organizations | create, get, update display name, list available; request/cancel/get deletion | list/get only |
| organization members | list, invite/reissue/revoke invitation, change role, remove; accept invitation | safe reads and invite only after review |
| workspaces | list/get/create/update, archive non-Default, set model allowlist, set limits/data mode | list/get/create/update allowlisted non-secret fields; archive excluded |
| workspace members | list/add/change role/remove | read initially |
| API keys | list/create/revoke | list only; secret creation and revoke excluded |
| billing | balance, ledger/usage summaries, top-up intent/checkout | reads only; checkout excluded |
| models | list/get capability/price/status | read |
| usage | bounded list/get metadata/aggregates and bounded streaming CSV export | read metadata/aggregates; export excluded initially |
| traces | metadata and grant creation/delete | metadata read only; plaintext/grants/delete excluded |
| recommendations | list/get/accept/dismiss/start bounded evaluation | read; mutation deferred from MCP until abuse review |
| distribution | operator channel/catalog/statement commands | never customer MCP |
| research | approved read views and bounded operator commands through Python BFF | no launch MCP |
| operator | release, reconciliation, projection, account/fleet commands | never MCP |

One-time API key secret, checkout URL, trace plaintext/grant, deletion confirmation and internal evidence are marked sensitive in OpenAPI and are never copied to logs or agent docs examples.

Usage CSV requires organization/workspace authorization, an inclusive UTC range no longer than 31 days, a documented maximum row count, deterministic `(started_at, id)` order and `Cache-Control: no-store`. It streams directly from an indexed PostgreSQL cursor, emits only usage metadata already available to that actor, formula-escapes spreadsheet cells, and fails before headers if the bound cannot be satisfied. There is no export-job table or S3 export object at seed.

### 4.3 Authorization context

```ts
type SignedInActor = {
  userId: UserId;
  sessionId: SessionId;
  requestId: RequestId;
};

type OrganizationActor = SignedInActor & {
  organizationId: OrganizationId;
  organizationRole: 'owner' | 'admin' | 'billing' | 'member';
};

type WorkspaceActor = OrganizationActor & {
  workspaceId: WorkspaceId;
  workspaceRole: 'admin' | 'developer' | 'viewer';
};
```

Recent-owner commands receive a server-created `RecentOwnerActor`; a boolean request field cannot assert recent authentication. Repository methods require organization/workspace IDs in signatures and predicates. A `not_found` response is used where revealing cross-tenant existence would leak data.

## 5. Public inference contract

### 5.1 Surfaces

| Surface | Authentication | Contract source |
| --- | --- | --- |
| `GET /v1/models` | bearer workspace/channel key | Models JSON schema and fixtures |
| `POST /v1/responses` | `Authorization: Bearer` | supported OpenAI Responses profile |
| `POST /v1/messages` | `x-api-key` plus required `anthropic-version`; bearer also accepted for migration | supported Anthropic Messages profile |

If both recognized credential headers are present, they must resolve to the same principal or the request fails before reservation. Provider-specific headers are stripped and not forwarded unless explicitly synthesized by the adapter.

### 5.2 Canonical request

The gateway-internal canonical request is a Rust domain type, not a public protocol. It must preserve ordered tagged content rather than flattening chat text:

```text
CanonicalRequest
  request_id
  protocol
  requested_model_id
  ordered input items
  tools and tool-choice constraints
  structured-output constraint when supported
  reasoning/effort controls when supported
  max_output_tokens
  sampling fields supported by the exact release
  stream flag
  effective data mode
  bounded request metadata allowed by policy
```

Each protocol adapter has three responsibilities only: parse/validate public input, map canonical events to public output, and map canonical errors. Provider adapters map canonical request/events to one upstream protocol. Unsupported input must fail before admission; adapters never silently omit it.

### 5.3 Responses seed profile

Supported at launch: text input/output, ordered multi-turn input items, function tools/results, bounded structured output/reasoning only where release-qualified, stream/non-stream, usage and protocol-native errors/events.

`store` omitted behaves as false; explicit false is accepted. Explicit true, previous response, conversations, background, provider-hosted tools, file/vector-store resources and unrelated hosted products fail before reserve with a stable unsupported code.

Streaming conformance fixtures include start/in-progress, output item/content deltas, completion, failure, usage and client cancellation. Unknown future official events are rejected by the snapshot conformance adapter until reviewed.

### 5.4 Anthropic Messages seed profile

Supported at launch: system content, ordered messages, text/tool-use/tool-result blocks, bounded thinking where release-qualified, stop sequences, stream/non-stream, usage and documented message events.

The adapter validates the pinned supported `anthropic-version`; unsupported beta headers and hosted/provider-only features fail explicitly. It does not translate Messages through a lossy OpenAI chat structure.

### 5.5 Model identity

- Canonical direct IDs are namespaced, for example `openai/<published-model>` and `anthropic/<published-model>`.
- A bare compatibility alias is allowed only when exactly one active definition owns it; ambiguity is an error listing canonical choices.
- Grad IDs are published aliases matching `grad/<effort>/<speed>`; only actually qualified combinations are listed.
- A Models object exposes public ID, owner, capabilities, context/output limits, prices and availability needed by a client. It never exposes endpoint weights, provider credentials or cell topology.

## 6. Serving projection contract

`gradiated/gateway/v1/snapshots.proto` transports monotonic snapshots from PostgreSQL authority to Valkey. Each snapshot has an entity identity, integer version, status and only fields used by gateway scripts/reads.

### 6.1 Snapshot messages

| Message | Required content | Consumer |
| --- | --- | --- |
| `OrganizationAccountSnapshot` | organization, active/suspended/deletion status, available micros, version | organization reserve script |
| `WorkspacePolicySnapshot` | organization/workspace, status, data mode, retention, optional monthly limit/spend, concurrency, allowlisted models, policy version | gateway admission |
| `ApiKeySnapshot` | org/workspace/key IDs, digest binding/pepper version, status, optional limit/concurrency, expiry, version | credential resolution/admission |
| `ChannelAccountSnapshot` | channel, status, exposure limit/outstanding, concurrency, version | channel reserve script |
| `ChannelCredentialSnapshot` | channel/credential digest binding, status, expiry, version | channel credential resolution |
| `AliasSnapshot` | public model ID, stable digest, optional canary digest/basis points, generation | deterministic release selection |
| `ReleaseSnapshot` | digest, public ID, kind, capabilities, context/output limits, integer prices, retry count, exact direct endpoints or owned marker | capability, reserve and route |

Publication is at-least-once. A script accepts a higher version, accepts an identical duplicate and rejects regression or same-version/different-bytes. Deletion uses an explicit tombstone/status snapshot and epoch; it never relies on key expiry alone.

## 7. Billing event contract

`gradiated/gateway/v1/billing.proto` is written atomically by Valkey scripts and consumed by the financial role.

### 7.1 `ReservationCreated`

Required fields:

- event ID and schema version;
- request/reservation ID;
- principal kind and organization/workspace/key or channel/credential IDs;
- requested public model ID and immutable release digest;
- reserved sell micro-USD;
- start timestamp and lease expiry.

The event proves a reserve transition, not revenue or provider invocation.

### 7.2 `UsageSettled`

Required fields:

- event ID/schema, request/reservation IDs and terminal state;
- principal identity and immutable release identity;
- actual target identity safe for financial evidence;
- reserved and actual sell micros;
- optional actual buy micros when known under provider evidence policy;
- input/cached-input/output token counts when available;
- one bounded typed attempt summary with target/error/timing fields and no payload, provider secret or private endpoint;
- usable-output-delivered boolean, customer/provider cancellation owner and terminal error class;
- start/completion timestamps.

Actual sell exceeding reserve is an invariant incident: the account is suspended, evidence is retained and the financial worker does not silently clamp. Customer failed-request credit is a separate idempotent compensating ledger transaction after policy evaluation.

### 7.3 Delivery and posting

The consumer commits the usage row, balanced transaction, balance update, audit/outbox and event-business-key receipt before acknowledging. Duplicate delivery has no business effect. Poison serialization moves to a bounded protected incident path while preserving the original bytes; it is never skipped to free stream space.

## 8. Trace envelope contract

`gradiated/gateway/v1/traces.proto` is payload-ciphertext transport, never a plaintext DTO.

Required fields:

- envelope/event/schema version;
- request, organization, workspace and release IDs needed for authorization/attribution;
- capture status and effective data mode;
- ciphertext algorithm/version, nonce, ciphertext and wrapped data key;
- plaintext canonical-format version and digest;
- bounded ciphertext size and created/expiry times.

Forbidden fields include raw authorization/provider headers, plaintext prompt/completion, raw customer labels, provider credentials and reusable decrypt grants.

The intelligence consumer writes an opaque S3 object and trace metadata transaction before acknowledging. Reprocessing equal digest is success; same identity/different digest is an incident. Deletion destroys wrapped-key access before asynchronous object-version cleanup.

## 9. Gateway-to-inference serving contract

`gradiated/inference/v1/serving.proto` is a bidirectional stream between the gateway/router and cell. The router may relay without knowing public billing or customer structures.

### 9.1 `ServeRequest`

Required content:

- request ID and immutable release digest;
- canonical ordered input/tool/output constraints needed by runtime;
- max output and deadline;
- opaque cache scope derived from workspace/channel, release and retention class;
- stream/metering requirements;
- trace-free bounded diagnostic flags.

Forbidden content:

- organization/workspace display data;
- API key, balance, price or reservation token;
- provider lifecycle identity/credential;
- public route fallback policy;
- trace decrypt material.

### 9.2 `ServeEvent`

Closed variants:

- accepted/readiness;
- output item/content/tool/reasoning delta;
- usage/metering update;
- completed terminal;
- failed terminal with canonical safe class;
- heartbeat/flow-control where required by transport.

The first usable output event freezes retry eligibility. Exactly one terminal event is expected; transport loss is converted to one terminal outcome by the caller state machine.

## 10. Cell control and identity contract

`gradiated/inference/v1/registration.proto` supports enrollment, attestation, heartbeat and drain.

| Message | Required content |
| --- | --- |
| enrollment request | allocation/member token, CSR, exact bundle/release/topology digests, member ordinal/role |
| enrollment response | short-lived certificate chain, trust roots, cell-connect endpoint, bounded config and short-lived artifact access grant |
| coordinator hello | allocation/cell identity, certificate serial, exact release/bundle/topology/runtime attestation, capacity class |
| heartbeat | cell identity, monotonic sequence, readiness, active/queued requests, cache-safe aggregate capacity, member health |
| drain | reason, deadline and router acknowledgement |

Enrollment consumes one-use SQL-backed token. The artifact grant is an allocation/session-tagged short-lived AWS credential restricted to exact S3 object paths and the runtime ECR repository; it contains no provider lifecycle, customer or trace authority. The cell verifies artifact and image digest/signature after download. Worker-member credentials cannot mint coordinator/router identity. Router trusts short-lived mTLS identity plus exact attestation, not provider IP, Kubernetes namespace or self-reported model name.

## 11. Capacity-provider driver contract

The provider abstraction is an internal Rust trait over PostgreSQL commands, not a network plugin or CRD:

```rust
trait CapacityDriver {
    async fn quote(&self, request: QuoteRequest) -> Result<Quote, DriverError>;
    async fn create(&self, allocation: AllocationSpec) -> Result<ObservedResources, DriverError>;
    async fn observe(&self, allocation: AllocationRef) -> Result<ObservedResources, DriverError>;
    async fn drain(&self, allocation: AllocationRef) -> Result<(), DriverError>;
    async fn delete(&self, allocation: AllocationRef) -> Result<CleanupEvidence, DriverError>;
    async fn list_owned(&self, source: CapacitySourceRef) -> Result<Vec<OwnedResource>, DriverError>;
}
```

Every mutating call receives stable idempotency identity, ownership/expiry tags, budget/topology constraints and lease epoch. Drivers return normalized classifications but preserve a bounded provider reference for operator evidence. Unknown create outcome is observed by identity before retry. Delete is not complete until all allocation members/resources are independently absent or confirmed released.

## 12. Artifact manifest contracts

Canonical JSON serialization uses UTF-8, sorted keys, normalized numbers/strings and no insignificant whitespace. The digest is over canonical bytes excluding no fields; manifests do not contain their own digest.

| Manifest | Freezes |
| --- | --- |
| model source | upstream/repository/license/source digests and trust decision |
| checkpoint | tensor/config/tokenizer/template hashes and architecture identity |
| operator | kernel/plugin source/build digest, shape/dtype/hardware envelope and oracle evidence |
| runtime | OCI digest, command/local protocol, library/driver requirements and cache/scheduler behavior |
| topology | node/GPU counts, parallel dimensions, coordinator/collective/fabric/placement/member roles |
| bundle | references to all required manifests/artifacts and production capability surface |
| qualification | exact subject/scope/policy, gate results/evidence refs, expiry and signer/provenance |

Mutable status, alias, price, rollout, creation clock and experiment queue position are excluded from bundle identity. Product price/capability release rows reference the bundle and qualification; they are not rewritten into the runtime bundle.

## 13. Research control contract

`gradiated/research/v1/service.proto` and `refs.proto` are private and consumed by Hono BFF/operator tools. Python implements the service and owns all mutation policy.

Required commands/queries:

- create/update program within authority;
- register hypothesis;
- create immutable campaign and experiment spec;
- queue/cancel run;
- record environment/result artifact references;
- submit/review evidence report;
- build bundle;
- request/record independent qualification;
- create signed release proposal;
- read program/campaign/run/evidence/bundle/qualification views.

Every mutation carries actor/deployment identity, expected state/version where needed, idempotency key, budget authority and request ID. Temporal activities call these application commands; they never mutate research tables directly.

## 14. Object-key and secret-reference contracts

Object keys are opaque, environment-scoped and derived from random IDs/digests, never customer names, emails, model prompts or raw URLs. A database `object_key` is meaningful only inside its purpose-specific bucket.

`credential_ref` and `config_ref` are typed references to Secrets Manager/config objects. They never contain a secret value. Code accepts secret values from the runtime provider, not from Git configuration or CLI flags.

## 15. Compatibility and rollout

### 15.1 REST

Additive optional response fields remain in v1. Renaming, removal, semantic changes or making optional input required needs a new version/deprecation contract. Mutations reject unknown request keys unless a compatibility exception is explicitly tested.

### 15.2 Protobuf

Never reuse field numbers or names. Readers tolerate unknown fields but reject unknown semantic enum variants at command boundaries. Breaking checks compare against `main`. A sender rollout follows reader-first, writer-second, old-reader retirement, then field removal reservation.

### 15.3 Valkey

Scripts and key formats carry an epoch. Deploy dual readers/new writers before changing formats. Projection rebuild can create a new epoch and atomically switch admission only after comparison. Reservations remain on their admitted epoch until terminal.

### 15.4 Database

Migrations are expand, backfill/compare, switch, contract. Financial fields are never destructively backfilled without invariant reconciliation. Fleet/research workflow IDs remain stable through deployment.

### 15.5 Public inference

Official upstream schemas are version-pinned fixtures. Grad advertises only its documented subset. Adding a field/event requires parser, adapter, canonical mapping, error, stream, billing and official-client tests before it appears in model capabilities/docs.

## 16. Contract acceptance checklist

A contract package is complete only when:

- source and generated locations exist;
- owner and consumers are listed;
- valid, invalid, boundary and unknown-version fixtures exist;
- authorization and sensitive-field review passes;
- idempotency and duplicate/conflict behavior is tested;
- TS/Rust/Python round trips match where each participates;
- descriptions/examples pass for public schemas;
- Buf/OpenAPI/JSON Schema lint and drift checks pass;
- mixed-version rollout and rollback behavior is documented;
- logs/errors/metrics are proven payload- and secret-safe.
