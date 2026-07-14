# Simplified Rust gateway implementation blueprint

## Boundary and dependencies

The gateway authenticates a workspace or native-channel credential, resolves an immutable release, atomically reserves money/limits in Valkey, calls one exact direct provider or owned release, streams output, settles once and optionally emits an encrypted trace. Its only synchronous internal state/control dependency is Valkey.

It cannot call PostgreSQL, Hono, Stripe, S3/KMS private APIs, Kubernetes, research or a capacity-provider lifecycle API. Curated provider APIs and the private inference router are serving destinations, not state dependencies.

Use one Rust workspace with three crates initially:

```text
services/gateway/
  crates/
    gateway/       server, protocol/provider modules, admission, routing, trace
    contracts/     generated Protobuf for Redis and inference wire only
    testkit/       fake Valkey/providers/router, fixtures and proptest models
```

Use Tokio, Axum, Tower, Reqwest, rustls, serde, prost, tracing and checked integer wrappers. Protocol/provider modules remain private modules until compile time or ownership justifies a crate split.

## Minimal request state

```rust
enum Principal {
    Workspace { organization_id: Id, workspace_id: Id, api_key_id: Id },
    Channel { channel_id: Id, credential_id: Id },
}

struct CanonicalRequest {
    request_id: Id,
    protocol: PublicProtocol,
    requested_model: String,
    input: CanonicalInput,
    max_output_tokens: u32,
    stream: bool,
    data_mode: DataMode,
}

struct Release {
    digest: Digest,
    public_model_id: String,
    capabilities: Capabilities,
    prices: Prices,
    route: Route,
}

enum Route {
    Direct { provider: Provider, upstream_model: String, endpoints: Vec<EndpointId>, retries: u8 },
    Owned { retries: u8 },
}
```

Do not create provider/model/product/family/candidate/price-book objects inside the gateway. The immutable release projection already contains the fields needed to admit and route.

## Interfaces

```rust
trait Protocol {
    fn parse(&self, request: HttpRequest, limits: &IngressLimits) -> Result<CanonicalRequest, PublicError>;
    fn encode(&self, event: CanonicalEvent) -> Result<HttpEvent, PublicError>;
}

trait SnapshotStore {
    async fn resolve_credential(&self, raw: Secret) -> Result<Principal, AdmissionError>;
    async fn resolve_release(&self, principal: &Principal, model: &str) -> Result<Release, AdmissionError>;
}

trait Admission {
    async fn reserve(&self, command: Reserve) -> Result<Reservation, AdmissionError>;
    async fn settle(&self, command: Settle) -> Result<Receipt, AdmissionError>;
}

trait Upstream {
    async fn invoke(&self, attempt: Attempt) -> Result<CanonicalStream, UpstreamError>;
}

trait TraceCapture {
    fn prepare(&self, request: &CanonicalRequest, terminal: &Terminal) -> Result<Option<EncryptedTrace>, TraceError>;
}
```

There is one `Admission` implementation parameterized by account kind. Organization and channel keys, balances and events remain disjoint; shared code is not shared authority.

## Request lifecycle

```text
receive -> bound headers/body -> parse public protocol
 -> hash credential and resolve principal snapshot
 -> resolve one immutable release/alias generation
 -> validate workspace/channel policy and request capabilities
 -> compute conservative maximum sell exposure
 -> atomic reserve + concurrency + lease + ReservationCreated
 -> choose exact direct endpoint or owned cell
 -> invoke and stream while metering
 -> atomic settle/release + UsageSettled
 -> best-effort append encrypted trace when allowed
 -> close
```

Each step advances an in-memory enum and can occur once. Property tests generate cancellation/failure at every transition. No upstream invocation exists without a reservation token; no terminal path omits settlement or explicit lease expiry.

## Valkey model

Use one production cluster. Workspace keys share an organization hash tag; channels use a separate tag/ACL.

```text
gw:{org}:account                     status, available, held, version
gw:{org}:workspace:<id>              status, data mode, monthly limit/spend, concurrency, allowlist, version
gw:{org}:key:<id>                    digest binding, status, optional monthly/concurrency limit
gw:{org}:reservation:<id>            request, release, hold, lease, state
gw:{org}:billing                     Redis Stream

gw-channel:{channel}:account         status, exposure limit/outstanding, concurrency, version
gw-channel:{channel}:credential:<id> digest binding/status
gw-channel:{channel}:reservation:<id>
gw-channel:{channel}:billing         Redis Stream

gw:alias:<model-id>                  stable/canary digest + generation
gw:release:<digest>                  immutable release
gw:trace                             encrypted trace stream with independent memory/consumer policy
```

One versioned Lua reserve script per account kind validates credential, policy versions, release/price, available credit or exposure, one monthly window and concurrency. It creates the reservation/lease and appends `ReservationCreated` atomically. A repeated internal request ID with the same reservation inputs returns the prior reservation; conflicting inputs return `idempotency_conflict`.

Settlement verifies token/state, stores actual sell/usage, releases hold/concurrency and appends `UsageSettled` atomically. If actual exceeds reserve, close account admission and retain evidence; never silently clamp. Lease sweep uses the same terminal transition. Billing stream memory always outranks trace capture.

Low balance is one script rule: when available-before-reserve is below a small versioned multiple of this request's worst-case hold, apply the fixed organization-wide cap (initially one). The multiplier/cap are deployment constants covered by PBT, not customer fields or mutable risk state. Do not create a workspace risk model or adaptive fraud engine.

## Routing and retries

Direct releases stay on the exact provider/upstream model. Owned releases stay on the exact release digest. Alias canary selection is a deterministic hash before reservation and is included in the reservation identity.

Request-time health may remove an endpoint/cell but never add one absent from the release projection. Retry only a connection/capacity/rate/server failure before usable output, within deadline, release retry count and company buy-risk budget. Never retry a policy, capability, context, authentication, refusal/moderation or post-output failure.

For owned traffic the gateway calls the private inference router for the admitted release; it does not read cell topology. The cell request is exactly the reduced contract in [the simplicity review](../../docs/SIMPLICITY_REVIEW.md#gateway-to-cell); billing IDs and public-product fields do not cross this boundary.

## Public protocols

Launch `GET /v1/models`, OpenAI `POST /v1/responses` and Anthropic `POST /v1/messages`, streaming and non-streaming. The Responses profile is stateless (`store` omitted/false only); Anthropic Messages is naturally stateless. Both support bounded text, function tools/tool results, structured output/reasoning where qualified, protocol-native events, usage and errors. Chat Completions, Embeddings, Google GenerateContent and other hosted-product surfaces are deferred.

The protocol contract, accepted/deferred capabilities, module layout and official-client tests are [defined here](PUBLIC_INFERENCE_PROTOCOLS.md). The canonical input is a tagged ordered content-item union; it is not a lossy flattened chat message.

Public JSON/SSE remains protocol-specific and fixture-governed. The canonical request is not a claim of lossless translation. Unsupported fields/capabilities fail before reserve/upstream spend; no silent dropping, truncation or response healing.

Stable public errors include invalid request/model, unsupported capability, context overflow, unauthenticated, forbidden/suspended, insufficient credits (402), low-balance/concurrency/rate/capacity (429), upstream unavailable and internal incident. Responses disclose requested ID, actual release/provider model, request ID and terminal usage without exposing endpoints/cells.

## Streaming and traces

Bound body, content parts, tool/schema size and output tokens before admission. Stream with bounded channels and socket backpressure. Client cancellation stops upstream, settles known usage and marks uncertainty; no background generation continues for a disconnected billable request.

Product Intelligence strips credentials/headers, bounds the trace, encrypts with a random data key and wraps it to the current ingest public key. Trace append occurs after settlement and cannot fail the successful customer response. No-retention creates no payload event but still receives a cache scope. Cache scope is HMAC-derived from principal, release and retention class; raw tenant IDs do not enter cells.

## Configuration and observability

Required config is listener/timeouts/body limits, Valkey TLS/ACL, provider secret references, inference-router mTLS and trace-ingest public keys. Start by validating config, connecting Valkey, loading scripts by digest and validating projection schema epoch. Readiness fails on Valkey/schema/script mismatch; liveness checks only process/event-loop progress.

Metrics use bounded protocol, endpoint, principal-kind, release class, result, error and attempt labels. No customer IDs or payloads in metrics. Structured protected logs use pseudonymous IDs and safe error classes.

## Verification and ordered packages

Use unit fixtures, real Valkey Testcontainers, proptest state machines, fake providers/router and official SDK E2E. Required properties cover parse bounds, canonical preservation, checked exposure, reserve/settle/lease schedules, low-balance cap, organization/channel isolation, deterministic alias selection, retry/output boundary, SSE fragmentation, cancellation and trace redaction/encryption.

1. `GW-00`: one crate layout, contracts, errors, fakes and PBT replay.
2. `GW-01`: credential/release snapshots and workspace/channel isolation.
3. `GW-02`: reserve/settle/lease Lua plus state-machine PBT.
4. `GW-03`: OpenAI Models/Responses protocol and coordinator against fake provider.
5. `GW-04`: one curated direct-provider adapter and protected client smoke.
6. `GW-05`: trace encryption/no-retention and S3-drain fixture.
7. `GW-06`: owned inference-router adapter/cell selection.
8. `GW-07`: Anthropic Messages protocol and direct adapter conformance; later protocols require demand.

The first paid acceptance is one funded workspace key making streamed/non-streamed Responses and Messages requests through exact providers, producing one usage record and one credit effect under duplicate, cancellation and provider-fault schedules.
