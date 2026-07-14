# Rust gateway implementation blueprint

## Scope and invariants

The gateway is the only public inference server. It translates supported OpenAI, Anthropic and Google wire protocols into one canonical request; authenticates a workspace or distribution-channel principal; validates policy/capability/model/price; atomically reserves money and limits in Redis; invokes the exact direct provider or Grad release; streams output; settles once; and optionally emits an encrypted trace.

It must never:

- call PostgreSQL, Hono, Stripe, ClickHouse, S3/KMS private APIs, Kubernetes, Temporal or a capacity-provider lifecycle API;
- dispatch before a durable atomic reservation/event succeeds;
- infer a capability from “OpenAI compatible,” silently drop a field, cross provider/model/version, or change Grad effort/speed;
- expose provider credentials, raw API keys, internal endpoint/cell identities or customer content in logs/metrics;
- replay after usable output or make trace success a prerequisite for financial settlement.

## Workspace and crate graph

```text
product/services/gateway/
  Cargo.toml
  crates/
    gateway-server/              # Axum listener, middleware, config, shutdown
    gateway-core/                # canonical types, lifecycle, errors, clocks/IDs
    gateway-protocol-openai/     # Models, Chat, Responses, Embeddings, SSE
    gateway-protocol-anthropic/  # Messages and native event stream
    gateway-protocol-google/     # GenerateContent skins
    gateway-auth/                # key/channel credential parsing and principal
    gateway-catalog/             # model/capability/price/release resolution
    gateway-admission/           # Redis projection, scripts and leases
    gateway-routing/             # direct endpoint / exact Grad target planning
    gateway-provider/            # provider trait and shared transport
    gateway-provider-openai/
    gateway-provider-anthropic/
    gateway-provider-google/
    gateway-provider-owned/
    gateway-distribution/        # channel profile/catalog/exposure handling
    gateway-trace/               # capture policy, redaction, envelope encryption
    gateway-contracts/           # generated Protobuf only
    gateway-observability/       # bounded metrics/tracing helpers
    gateway-testkit/             # fake Redis/providers/edge, fixtures, PBT model
```

Dependency direction:

```text
server -> protocol adapters -> request coordinator (core)
core -> auth/catalog/admission/routing/provider/trace traits
implementations -> core + generated contracts
contracts -> no application crate
```

No provider crate imports public protocol structs. No protocol crate imports Redis/provider clients. `gateway-core` contains no Axum, Redis or Reqwest concrete client.

## Core request types

```rust
pub struct RequestIdentity {
    pub request_id: RequestId,
    pub ingress_protocol: IngressProtocol,
    pub idempotency_key: Option<IdempotencyKey>,
    pub client_request_id: Option<BoundedString>,
}

pub enum Principal {
    Workspace(WorkspacePrincipal),
    DistributionChannel(ChannelPrincipal),
}

pub struct WorkspacePrincipal {
    pub organization_id: OrganizationId,
    pub workspace_id: WorkspaceId,
    pub api_key_id: ApiKeyId,
    pub projection_epoch: ProjectionEpoch,
    pub policy: EffectiveWorkspacePolicy,
}

pub struct ChannelPrincipal {
    pub channel_id: DistributionChannelId,
    pub credential_id: ChannelCredentialId,
    pub profile_version: ChannelProfileVersion,
    pub policy: EffectiveChannelPolicy,
}

pub struct CanonicalRequest {
    pub requested_model: RequestedModel,
    pub input: CanonicalInput,
    pub tools: Vec<ToolDefinition>,
    pub response_format: ResponseFormat,
    pub sampling: SamplingParameters,
    pub reasoning: ReasoningRequest,
    pub max_output_tokens: TokenCount,
    pub stream: bool,
    pub data_mode_request: Option<DataMode>,
    pub session_key: Option<SessionKey>,
    pub migration_experiment: Option<MigrationExperimentToken>,
}

pub struct RequestPlan {
    pub identity: RequestIdentity,
    pub principal: Principal,
    pub effective_data_mode: DataMode,
    pub model: ResolvedModel,
    pub release: RouteReleaseProjection,
    pub capabilities: CapabilityPlan,
    pub price: PriceQuote,
    pub route: RoutePlan,
    pub deadlines: RequestDeadlines,
}
```

Canonical input preserves role/content-part order and explicit presence where semantics differ. Images/files are bounded descriptors or validated inline bytes according to the protocol profile. The gateway never downloads an arbitrary customer URL at seed; URL-bearing inputs are accepted only when the selected provider's qualified protocol passes them through without server-side fetch, otherwise reject.

## Primary traits

```rust
#[async_trait]
pub trait ProtocolAdapter: Send + Sync {
    type WireRequest;
    fn parse(&self, headers: &HeaderMap, body: Bytes) -> Result<ParsedRequest, ProtocolError>;
    fn requirements(&self, request: &ParsedRequest) -> Result<CapabilityRequirements, ProtocolError>;
    fn encoder(&self, request: &ParsedRequest) -> Box<dyn ResponseEncoder>;
}

#[async_trait]
pub trait CredentialResolver: Send + Sync {
    async fn resolve(&self, presented: PresentedCredential) -> Result<Principal, AuthError>;
}

pub trait CatalogResolver: Send + Sync {
    fn resolve(&self, principal: &Principal, requested: &RequestedModel,
               requirements: &CapabilityRequirements) -> Result<ResolvedRelease, CatalogError>;
}

pub trait ExposureEstimator: Send + Sync {
    fn quote(&self, request: &CanonicalRequest, release: &ResolvedRelease)
        -> Result<PriceQuote, PricingError>;
}

#[async_trait]
pub trait AdmissionStore: Send + Sync {
    async fn reserve(&self, command: ReserveCommand) -> Result<Reservation, AdmissionError>;
    async fn renew(&self, command: RenewCommand) -> Result<LeaseExpiry, AdmissionError>;
    async fn settle(&self, command: SettleCommand) -> Result<SettlementReceipt, SettlementError>;
    async fn abandon(&self, command: AbandonCommand) -> Result<SettlementReceipt, SettlementError>;
}

pub trait RoutePlanner: Send + Sync {
    fn plan(&self, release: &ResolvedRelease, principal: &Principal,
            request: &CanonicalRequest, health: &HealthSnapshot) -> Result<RoutePlan, RouteError>;
}

#[async_trait]
pub trait UpstreamAdapter: Send + Sync {
    fn profile(&self) -> &AdapterProfile;
    async fn start(&self, attempt: AttemptRequest,
                   cancellation: CancellationToken) -> Result<UpstreamStream, UpstreamError>;
}

#[async_trait]
pub trait TraceSink: Send + Sync {
    async fn emit(&self, trace: EncryptedTraceCapture) -> Result<TraceAppendReceipt, TraceError>;
}
```

`RequestCoordinator` is the only orchestrator using all traits. Protocol handlers call it once and encode its ordered canonical events. There is no second “fast path” for channels, direct models, non-streaming or tests.

## Request lifecycle state machine

```text
Received
 -> Parsed
 -> Authenticated
 -> Planned
 -> Reserved
 -> Dispatching(attempt=1)
 -> Streaming(output_visible=false|true)
 -> Settling
 -> Completed

Any pre-reserve error -> Rejected(no financial effect)
Reserved pre-output retryable failure -> Dispatching(next bounded attempt)
Reserved terminal/cancel/error -> Settling -> Completed
Lease uncertainty -> SettlementUncertain + fail-closed repair event
```

The coordinator owns a `RequestLifecycle` value whose transition methods consume `self` and return the next typed state where practical. A terminal guard ensures exactly one settlement attempt is produced even when client cancellation, upstream error, timeout and response-write failure race.

Detailed order:

1. Apply connection/header/body/content-type/decompression/time bounds.
2. Parse credential syntax without logging it; resolve principal from Redis.
3. Parse wire request and compute explicit capabilities/data policy.
4. Resolve model/release/catalog and reject unsupported/ineligible behavior.
5. Validate context/output bounds and calculate conservative maximum fixed sell exposure with checked integer arithmetic.
6. Select route candidates from the same immutable release projection. This selection creates no cost.
7. Call `reserve`; no network dispatch method is reachable without the returned unforgeable `ReservationToken`.
8. Start one bounded attempt. Renew long-stream lease before safety margin; renewal failure cancels upstream and settles conservatively.
9. Relay events with backpressure while accumulating monotonic usage and `usable_output_delivered`.
10. Retry only an eligible pre-output transient failure inside deadline/attempt/buy-risk bounds.
11. Settle terminal usage/reason once; response completion does not wait for PostgreSQL.
12. Build and append encrypted trace asynchronously/bounded after credential stripping. Trace append failure changes capture status/metrics only.

## Redis projections and atomic operations

All keys touched by workspace financial admission share `gw:{<organization_id>}`. Channel financial keys share `gw-channel:{<channel_id>}` and never enter a workspace script. Use versioned Lua scripts loaded by SHA at startup first; switch to Valkey Functions only after managed-service qualification without changing `AdmissionStore` semantics.

### Reserve command

```rust
pub struct ReserveCommand {
    pub event_id: EventId,
    pub request_id: RequestId,
    pub principal: PrincipalRef,
    pub expected_projection_epoch: ProjectionEpoch,
    pub key_digest_lookup: KeyLookup,
    pub required_policy_versions: RequiredPolicyVersions,
    pub release_id: RouteReleaseId,
    pub price_book_id: PriceBookId,
    pub maximum_sell_micros: i64,
    pub workspace_window_debits: Vec<WindowDebit>,
    pub key_window_debits: Vec<WindowDebit>,
    pub concurrency_units: u32,
    pub lease_ttl_ms: u64,
    pub idempotency_digest: Digest,
}

pub struct Reservation {
    pub reservation_id: ReservationId,
    pub token: ReservationToken,
    pub reserved_micros: i64,
    pub lease_expiry: Instant,
    pub admitted_release_id: RouteReleaseId,
    pub admitted_price_book_id: PriceBookId,
}
```

One script validates credential/status/epoch/config/release/price, checks spendable credit or channel exposure, all period windows and concurrency (including low-balance cap), creates reservation/lease/idempotency record, increments holds/in-flight and appends `ReservationCreated` to the billing stream. Any failure mutates nothing. Duplicate same digest returns the original reservation; duplicate different digest returns `idempotency_conflict`.

### Settlement command

`SettleCommand` carries reservation token, terminal event ID, attempt summaries, usage units/evidence class, actual fixed sell amount, usable-output fact, terminal reason and safe trace status. One script verifies active lease/token/epoch compatibility, caps or records explicit overage debt, releases remaining hold and all concurrency/window reservations, records terminal idempotency and appends `UsageSettled`. A duplicate returns the original receipt. It never deletes the stream fact needed for PostgreSQL posting.

If known actual sell exceeds reserve, close new organization/channel admission and append the overage evidence; do not silently clamp and reopen. Lease sweep uses the same settlement/abandon transition and cannot race into a second financial effect.

### Projection contract

Redis contains immutable versioned snapshots:

- credential lookup -> principal reference/status/pepper epoch;
- organization billing -> spendable/status/risk/credit epoch/low-balance policy;
- workspace/key policy -> status, model/data/output/limit versions;
- model catalog/release/price -> immutable definitions and active alias generation;
- signed cell target set -> exact Grad release, target epochs and expiry;
- trace ingest public key -> version/expiry only.

Projectors build new versions and atomically activate pointers. Gateway readiness requires script SHA/schema compatibility and a minimum safe projection set, not any particular customer being loaded.

## Model, capability and route planning

Resolution order is exact Grad pin, Grad family head, Grad managed product, canonical direct provider/model, then unique bare alias. `x-grad-provider` may disambiguate only a bare direct alias. Request fields cannot provide endpoint URLs, provider arrays or routing weights.

`CapabilityPlan` checks endpoint, modalities, tools, structured output, reasoning, sampling fields, context/output, data mode, cache semantics and ingress response obligations. The plan records every accepted field; a debug/test assertion proves no parsed field is neither consumed nor explicitly rejected.

Direct `RoutePlan` contains qualified endpoints for one provider/model/version and bounded same-identity retries. Grad `RoutePlan` contains signed cell targets for one route release and speed. Deterministic canary/session assignment is computed before reservation and included in the admitted release/price identity. In-process health/circuit state may remove a candidate but never add one absent from Redis.

The migration experiment header is validated against a Redis projection bound to workspace/source model/workload/budget/expiry. It deterministically selects direct baseline or exact Grad candidate before pricing/reserve and discloses the selection. Without a valid header, direct identity remains a hard pin.

## Provider adapter contract

Each adapter has an immutable `AdapterProfile` generated from qualified catalog data:

```rust
pub struct AdapterProfile {
    pub provider: ModelProvider,
    pub adapter_version: AdapterVersion,
    pub supported_protocols: BTreeSet<IngressProtocol>,
    pub supported_capabilities: CapabilityMatrix,
    pub retry_policy: RetryPolicy,
    pub usage_policy: UsageEvidencePolicy,
    pub cancellation_policy: CancellationPolicy,
    pub data_policy: ProviderDataPolicy,
}
```

An `AttemptRequest` carries exact endpoint reference and secret handle resolved from process secret config, canonical request, absolute deadline, reservation/attempt IDs for correlation and an allowlisted outbound-header map. It never carries another customer's endpoint or arbitrary URL.

`UpstreamEvent` is `Accepted`, `OutputDelta`, `UsageUpdate`, `Finish` or `Error`. Usage updates are cumulative or normalized to cumulative before reaching the coordinator. Adapter error classification includes stage, retryable-before-output, provider status/code, emitted output, usage certainty and safe request ID. Raw response bodies are excluded from ordinary error text.

Reqwest clients are built once per adapter with fixed scheme/host allowlist, TLS roots, connect/header/idle/total bounds, redirect disabled, pool limits and sanitized DNS behavior. Provider credentials are mounted/read into a secret type whose `Debug`/`Display` are redacted.

## Public protocols and errors

Public schema/fixture authority is separate from canonical/internal Protobuf. Freeze one support matrix per endpoint/version. Unknown JSON fields are rejected unless the selected public protocol explicitly requires forward-compatible ignore behavior; tests record that choice. Request body limits apply before full allocation where possible.

Implementation order is OpenAI `GET /v1/models` + Chat, then Responses and Embeddings, Anthropic Messages, then Google GenerateContent. All remain seed targets, but no unfinished skin blocks first paid Chat traffic.

Stable internal error codes map through a protocol encoder:

| Internal code | Default HTTP | Notes |
| --- | ---: | --- |
| `invalid_api_key` | 401 | no key existence disclosure |
| `organization_suspended`, `workspace_suspended`, `policy_forbidden` | 403 | channel equivalents are separate |
| `insufficient_credits` | 402 | workspace principals only |
| `low_balance_concurrency_limit`, `rate_limit`, `route_capacity_exhausted` | 429 | bounded `Retry-After` where known |
| `model_not_found`, `provider_not_supported` | 404 | catalog-scoped |
| `unsupported_parameter`, `unsupported_capability`, `context_too_large` | 400 | fail before reserve |
| `payload_too_large` | 413 | no payload echo |
| `admission_unavailable` | 503 | Redis/script/config uncertain; fail closed |
| `route_unavailable` | 503 | exact release has no safe route |
| `upstream_interrupted` | 502 | may be midstream protocol terminal |
| `deadline_exceeded` | 504 | settle known usage |
| `idempotency_conflict` | 409 | management-style semantic; protocol envelope remains stable |

Every error includes request ID and safe message; only errors after reservation include internal settlement correlation. Do not expose balance, provider key, endpoint, capacity provider or cell host.

## Streaming, backpressure and cancellation

- One bounded channel connects upstream reader to response encoder; slow clients eventually cancel upstream rather than unbounded-buffering content.
- The encoder writes protocol-required event ordering and terminal markers. UTF-8/codepoint boundaries and JSON fragments are fixture-tested.
- Client disconnect races through one cancellation token. Adapter cancellation is best effort; coordinator waits a bounded usage grace period, then settles known/uncertain usage according to profile.
- SSE keepalive comments are protocol/profile policy and never count as usable model output.
- `usable_output_delivered` is set only after protocol-specific content/tool output bytes are accepted by the client writer, not merely received upstream.
- Once usable output is delivered, no other upstream attempt begins.

## Trace capture

`TraceBuilder` receives the parsed canonical request and canonical output events, never raw authorization/provider headers. It enforces data mode before allocation, allowlists metadata, limits payload/event/tool/file sizes and records omissions. Product Intelligence output is encrypted into the envelope defined by the control blueprint using a pinned crypto implementation and test vectors. Private/No Retention creates no payload builder or trace-stream entry.

Trace append uses a separate Redis connection pool, stream/key quota and timeout. It can be shed when billing memory/latency headroom crosses threshold. Settlement records `eligible|captured|skipped_<reason>|no_retain`; it does not include ciphertext.

## Configuration, startup and shutdown

`GatewayConfig` contains listener/timeouts/body limits, Redis endpoints/TLS/ACL reference, script digests/schema versions, provider endpoint allowlists/secret-file paths, trace public-key projection requirements, observability and feature gates. Catalog, prices, customer policy and routes are never environment variables.

Startup sequence: parse config -> initialize crypto/TLS -> connect Redis -> load/verify scripts -> verify projection schema -> build fixed provider clients -> bind listener -> ready. `/readyz` fails on Redis/script/schema incompatibility but does not call providers. During shutdown, stop accepts, drain bounded requests, keep lease renew/settle alive until deadline, then emit uncertainty for any forced termination. Kubernetes grace period exceeds gateway drain deadline.

## Observability

Metrics have bounded labels: protocol/endpoint, principal kind, canonical model class or allowlisted model ID, release, result/error class, data mode, attempt count, cache usage class and region. Organization/workspace/request IDs belong only in protected structured logs/traces as HMAC/pseudonymous lookup fields, never metrics. Payloads, tools, prompts and completions are forbidden.

Record parse/auth/plan/reserve/queue/TTFT/stream/settle durations separately. Gateway overhead excludes upstream time. Counters prove `dispatch_without_reservation == 0`, cross-identity route violations `== 0`, duplicate settlement effects `== 0` and plaintext trace fallback `== 0`.

## Verification and junior-agent packages

Properties and fixtures cover parsers, canonical conversion, capability accounting, checked money, identity resolution, admission scripts, concurrency schedules, route determinism, provider fault streams, SSE encoding, cancellation and trace redaction/encryption.

Implement in this order:

1. `GW-00`: core IDs/types/errors/traits, generated contracts and deterministic testkit.
2. `GW-01`: Redis schema/scripts, workspace/channel auth and admission state-machine PBT.
3. `GW-02`: OpenAI Models/Chat parser/encoder plus fake adapter vertical request.
4. `GW-03`: request coordinator, settlement guard, retry/cancel/lease logic.
5. `GW-04`: model/capability/price/route projection and deterministic release selection.
6. `GW-05`: OpenAI direct adapter and protected tiny smoke.
7. `GW-06`: owned inference adapter against fake edge/cell.
8. `GW-07`: trace builder/encryption/append and no-retain properties.
9. `GW-08`: Responses/Embeddings, Anthropic and Google as separate fixture-owned changes.
10. `GW-09`: distribution-channel profile, load/fault/soak and operations.

Acceptance for the first paid vertical: official OpenAI client funds a fake organization, calls streamed/non-streamed Chat, receives exact model/usage, posts one ledger charge and survives duplicate settle/cancel/provider faults. Real provider smoke is protected, capped and additive. Every later protocol reuses the coordinator/admission core and cannot introduce a bypass.
