# Gateway architecture

- status: current implementation authority
- scope: Rust inference data plane only
- parent architecture: [`docs/ARCHITECTURE.md`](../../../docs/ARCHITECTURE.md)
- canonical data model: [`docs/DATA_MODEL.md`](../../../docs/DATA_MODEL.md)

This document translates the repository-wide architecture and data model into
an implementation design for `product/services/gateway`. It refines those
documents but does not override them. When this document and a parent authority
disagree, the parent authority wins until the discrepancy is resolved in the
repository.

The gateway is one Rust service with one purpose: authenticate, qualify, admit,
and execute exact-model Chat Completions or native SystemOne, then record terminal usage
in Valkey. It is not a general-purpose API gateway or a model-routing platform.

## Goals

- expose OpenAI-compatible `POST /v1/chat/completions` for streaming and
  non-streaming inference;
- expose non-streaming `POST /v1/systemone` for native Kev pointer inference;
- expose the current provider `GET /v1/models` document for exact configured
  models;
- authenticate direct and OpenRouter keys through the same read-through cache;
- reject invalid, unsupported, or unpaid requests before generation and
  normalize SGLang overload responses;
- select one healthy deployment with stable rendezvous hashing;
- leave deployment admission to the engine and retry one safe failed attempt;
- preserve streaming backpressure and stop upstream work on cancellation;
- calculate charges from authoritative usage and admission-time prices;
- atomically consume the in-flight lease, debit the operational balance, and
  append one `GenerationSettled` event;
- expose bounded operational telemetry without retaining customer content.

## Non-goals

The gateway does not contain:

- PostgreSQL or ClickHouse clients;
- customer, workspace, API-key, model, or billing CRUD;
- Stripe or OpenRouter onboarding workflows;
- cross-model routing or provider discovery;
- model aliases or silent parameter translation;
- GPU provisioning or a fleet controller;
- parallel or post-output request retries;
- raw prompt, completion, unredacted request-body, or credential persistence;
- a second cache, durable queue, reservation ledger, or in-progress database.

## Design principles

### One explicit request coordinator

`CompletionService` owns the visible request lifecycle. Authentication,
qualification, admission, execution, usage, and settlement are steps in that
lifecycle, not independently deployed or independently orchestrated services.

### One owner after admission

Once a generation is admitted, exactly one `GenerationTask` owns its runtime
request, fixed lease, upstream response, observed usage, terminal outcome, and
finalization. This rule prevents two asynchronous code paths from racing to
classify or settle the same generation.

### Mutable state always comes from Valkey

Credentials, workspaces, accounts, model catalog state, balances, in-flight
leases, and terminal events are read or mutated in Valkey. The gateway uses one
lazy one-second memory cache for models, model IDs, and deployment status.
Credentials, accounts, and workspaces are read directly from Valkey.

### Exact identifiers, minimal routing

The gateway converts the request model ID to ASCII lowercase. The normalized
ID and `GatewayModel.id` must then match byte-for-byte.
`GatewayModel.deployments` may contain multiple `available` deployments. The
gateway intersects them with fresh status. It uses a session ID when present.
Otherwise, it hashes the first 4,096 actual input token IDs for token transports,
or the first 16 KiB of serialized chat messages or SystemOne state. Prompt
types have separate hash domains; every key includes workspace, model and
served-release identity. Weighted rendezvous hashing
gives one stable candidate order. A mismatch or missing route is an error.

Each candidate's weight is its share of first choices. A candidate whose status
reports `active_requests` shares, with the other reporters, the fraction of
candidates that report, in proportion to their limits. A candidate that does not
report keeps the equal share 1/N. With no reports every share is 1/N, and the
order is exactly the unweighted hash order. The release choice and the replica
choice within the chosen release use the same rule. The replica choice sees only
its own release, so while a release is part way through reporting its silent
replicas get their release's equal share rather than exactly 1/N of the model.

### Native SystemOne contract

`systemone.rs` validates the closed request envelope and rejects duplicate JSON
keys at every depth. A required exact model and text/object/array state accompany
1..64 named questions. `choice` takes 1..255 named criteria; `score` takes
2..255 ordered criteria; `noul` optionally takes a null or object criteria value
whose only permitted keys are `false` and `true`. Unknown outcome keys are
rejected, never silently dropped. Instructions and descriptions accept JSON values.
Model and question names are 1..200 UTF-16 code units; an optional, non-null
session ID is 1..256. Shared accepted/rejected fixtures test TypeScript parity.

Only `service_tier: "default"` is implemented. Streaming, output-token controls,
caller priority and unknown fields fail before dispatch. A `system_one` runtime
revision selects `/v1/systemone` and excludes Chat Completions; the prefix is a
transport discriminator within the digest-covered release, not a model alias.
The request uses the existing authentication, admission, routing, retry and
terminal-finalization lifecycle. Without a session ID, affinity follows state
alone, so changing questions does not move an otherwise identical request.

Responses must identify the selected runtime model and match the requested
question keys, answer types and options. Probability sums tolerate independent
two-decimal rounding; score indices and bounds are validated. Safe integer
usage requires `cached_input_tokens <= input_tokens` and `output_tokens == 0`.
Normalized cache-write and reasoning usage are also zero: this is prefill-only
inference, and serializing answers creates no billable generated tokens.
The returned model is rewritten to the requested public model ID.

### Atomic financial mutations

Admission and terminal finalization use versioned Lua scripts. Application-side
read/modify/write sequences are not used for concurrency or money. The
in-flight lease is the sole terminal idempotency token.

### Fail closed

Missing, malformed, inconsistent, or unavailable serving state rejects the
request. The gateway does not fall back to another datastore, a stale local
copy, a second model, or unbilled execution.

## Process and component model

The gateway is one Rust crate and one binary in every environment. Local
development connects that binary to a native SGLang process; it does not add a
second fake-runtime binary. The process uses a small set of concrete
components:

| Component                 | Kind                        | Responsibility                                                                                                |
| ------------------------- | --------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `GatewayState`            | concrete struct             | Composition root holding immutable configuration, Valkey adapter, runtime client, coordinator, and telemetry. |
| `CompletionService`       | concrete struct             | Coordinates the complete Chat Completions lifecycle. It is the only business-service object.                  |
| `ValkeyServingState`      | concrete adapter            | Reads gateway records and executes admission and finalization Lua scripts.                                    |
| `GatewayModel`            | typed Valkey record         | Carries the exact model policy and durable deployment candidates.                                             |
| `DeploymentRuntimeStatus` | typed Valkey record         | Carries current health and whether the runtime accepts requests.                                              |
| `ModelTokenizer`          | concrete struct             | Renders chat input and tokenizes it locally from the selected deployment's pinned tokenizer artifact.         |
| `SglangClient`            | concrete adapter            | Calls health and Chat Completions on the selected SGLang deployment.                                          |
| `GenerationTask`          | request-owned state machine | Owns all post-admission work and guarantees one terminal finalization path.                                   |
| `Telemetry`               | thin wrapper                | Emits metrics and structured events with bounded labels and sanitized fields.                                 |
| contract/domain modules   | data and pure functions     | Strict wire types, validation, usage normalization, pricing, release hashing, and error mapping.              |

Only external boundaries receive traits:

- `ServingState`, for replacing Valkey in focused coordinator tests;
- `ModelRuntime`, for replacing SGLang in focused coordinator tests;
- a clock interface only where deterministic lease and timestamp tests require
  it.

Production constructs concrete implementations once during startup. There is no
dependency-injection framework, service locator, generic repository layer, or
class for each step of the request lifecycle.

## HTTP surface

The gateway owns these canonical routes:

| Method | Path                   | Authentication     | Purpose                                                  |
| ------ | ---------------------- | ------------------ | -------------------------------------------------------- |
| `POST` | `/v1/chat/completions` | Bearer credential  | Streaming and non-streaming exact-model inference.       |
| `GET`  | `/v1/models`           | Bearer credential  | Provider schema for configured non-retired exact models. |
| `GET`  | `/health/live`         | none               | Process liveness only.                                   |
| `GET`  | `/health/ready`        | none               | Readiness of required serving dependencies.              |
| `GET`  | `/metrics`             | network-restricted | Prometheus metrics for the private observability stack.  |

Both SDKs use `https://api.gradiated.com` as their public base URL. The public
ALB routes the OpenAI and Anthropic request paths to this service. The gateway
accepts each inference path with or without `/v1`. The ALB keeps the legacy
`/openai/v1/*` route and removes the `/openai` prefix.

All errors use a stable OpenAI-compatible envelope:

```json
{
  "error": {
    "message": "Human-readable bounded message.",
    "type": "invalid_request_error",
    "param": "model",
    "code": "model_not_found"
  }
}
```

Internal error details, Valkey keys, private URLs, credentials, and upstream
response bodies are never returned.

## Chat Completions request lifecycle

The lifecycle has one forward direction:

```text
received
  -> authenticated
  -> qualified
  -> capacity_acquired
  -> admitted
  -> running
  -> succeeded | failed | cancelled | abandoned
  -> finalized
```

Failures before `admitted` create no in-flight lease, charge, or terminal
generation event. After `admitted`, the `GenerationTask` owns every exit and
attempts terminal finalization exactly once at the application level. Valkey
makes that attempt financially idempotent.

### 1. Transport acceptance

1. The ALB accepts TLS and routes the request to the gateway.
2. Axum matches canonical `POST /v1/chat/completions`.
3. The gateway generates a UUIDv7 `generation_id` and records `received_at` in memory.
4. It enforces a 32 MB (32,000,000-byte) body ceiling before JSON
   deserialization.
5. An oversized request returns `413 payload_too_large` without a Valkey lookup
   or SGLang call.
6. Request bodies and raw authorization headers are excluded from access logs.

The request span records a fixed, normalized header allowlist for client and
cache debugging: recognized client family, SDK package/version, bounded
`cache-control`, `cache-status`/`x-cache`, `age`, content encoding, `accept`,
`x-vllm-priority`, and presence flags for prompt-cache beta, ETag,
conditional requests and traceparent. Request and session identifiers are
stored as truncated SHA-256 hashes. Authentication headers are represented only
by a redacted final-four-character suffix. Cookies, raw credentials, arbitrary
custom headers, and header values over the bounded length are omitted.

Session diagnostics additionally record the presence of a fixed SDK header
allowlist and hashes of its identifier values: `x-opencode-session-id`,
`x-session-affinity`, `x-session-id`, `x-claude-code-session-id`, `session-id`,
`thread-id`, `x-client-request-id`, and `x-codex-window-id`. Only the
`session_id` and `thread_id` members of `x-codex-turn-metadata` are extracted;
other metadata is never logged. SDK identifier hashes accept at most 256 bytes; body session IDs retain their
endpoint-specific length contracts. JSON metadata parsing accepts at most 8192
bytes. Duplicate SDK session headers
are reported as present but are not hashed.

Before wire-format translation, the gateway observes only body `session_id`,
`prompt_cache_key`, `client_metadata.session_id`/`thread_id`, and `session_id`
inside JSON-encoded `metadata.user_id`. Values are hashed, not retained. It does
not record the whole metadata object or user identifier. Missing or malformed
metadata produces no identifier hash and does not change request validation.

`effective_session_source` and `effective_session_hash` describe the affinity
key selected once, before protocol translation, by `session_affinity::cache_key`.
The same resolved value chooses both the served release and the runtime replica;
translation cannot discard or independently change it. Preference order:

1. Body `session_id`.
2. Header `x-gradiated-session-id`.
3. Body `prompt_cache_key`.
4. Headers `x-claude-code-session-id`, `x-opencode-session-id`,
   `x-session-affinity`, `session-id`, `thread-id`, `x-session-id`, in that order.
5. Body `client_metadata.session_id`, then `client_metadata.thread_id`.
6. Header `x-codex-turn-metadata.session_id`, then its `thread_id`.
7. `session_id` inside JSON-encoded body `metadata.user_id`.

SDK identifiers and prompt cache keys must be nonempty, at most 256 bytes,
and contain no control characters. Body `session_id` retains endpoint validation:
Chat uses its scalar-count bound and SystemOne its 256-UTF-16-unit bound.
Null body fields are absent. An invalid selected explicit override
(the first three sources) returns 400; malformed, duplicate, or oversized
optional SDK hints are skipped. The remaining metadata is never an affinity key.
Request IDs and Codex window IDs are diagnostic only because they can change
within a conversation. Authenticated workspace, model and release scope the
replica hash; raw SDK header values are not forwarded as runtime cache keys.

With no usable explicit/SDK key, chat requests derive an affinity key from the
first system/developer message and the first non-system message, following
[OpenRouter's opening-message policy](https://openrouter.ai/docs/guides/best-practices/prompt-caching#provider-sticky-routing). Missing system instructions are allowed.
Chat Completions uses `messages`; Anthropic uses `system` plus `messages`;
Responses uses `instructions` plus `input` (a string or message array). Later
turns and request-level generation options do not participate. Object keys are
canonicalized before streaming into SHA-256, so JSON property order does not
change the key. Content is not copied into any persistent routing index.

If opening messages cannot be recognized, hash the first **8192 Unicode
characters** of the raw request body (the entire body if shorter), using a
separate hash domain. This fallback returns a key without a parsing error; it
does not relax the API's normal JSON, authentication, model, or schema validation.
Explicit keys continue to take precedence. The selected key is used for both
release selection and replica ranking. Workspace/model/release scoping and
health/capacity fallbacks remain in force.

`effective_session_source` reports `content_messages` or `content_prefix_8192`
for content-derived keys. SystemOne retains its existing state-prefix routing
(`state_prefix`) when no session key is supplied. Source and identifier hashes
are log fields, not Prometheus labels or durable billing fields. Session
or content affinity does not promise a cache hit: vLLM's prefix cache still
requires identical prefix tokens resident on that replica. The gateway does
not synthesize a per-session `cache_salt`.

The generation ID exists before authentication so every internal error can be
correlated without using a customer identifier. A rejected pre-admission
request is not a durable generation and does not enter the settlement stream.

### 2. Bearer authentication

1. Require exactly one `Authorization: Bearer <secret>` header.
2. Reject a missing, empty, repeated, or malformed credential with
   `401 invalid_api_key`.
3. Compute the lowercase hexadecimal SHA-256 digest of the raw secret in
   memory.
4. Read `credential:<digest>` from Valkey.
5. Strictly deserialize the `GatewayCredential`.
6. Reject a missing record, `revoked_at` value, elapsed `expires_at` value,
   malformed timestamp, or malformed UUID.
7. Discard the raw bearer value as soon as the digest has been calculated.

The resulting `AuthenticatedIdentity` contains only `api_key_id`,
`organization_id`, and `workspace_id`. Direct customers and OpenRouter use the
same code and record shape. There is no special channel authentication path;
two-key rotation is represented as two concurrently valid `GatewayCredential`
records.

### 3. Workspace and account access checks

1. Read `workspace:<workspace_id>` from Valkey.
2. Strictly deserialize the `GatewayWorkspace`.
3. Require its `workspace_id` and `organization_id` to match the credential.
4. Reject the workspace when `archived_at` is non-null or malformed.
5. Read `account:{settlement-0}:<organization_id>`.
6. Strictly parse the account hash, closed `billing_mode`, and integer balance.
7. Require its `organization_id` to match the credential.
8. Require `organization_status = active`.
9. For `prepaid`, require a positive operational balance. For `invoiced`, do
   not use balance as an admission condition.

Any unavailable, missing, malformed, or cross-tenant state fails closed. A
nonpositive prepaid balance returns `402 insufficient_balance`; unavailable or
invalid serving state returns `503 serving_state_unavailable`. This read is
only an early rejection: it neither grants a concurrency slot nor reserves
funds. The later atomic admission script rechecks status and billing mode and
performs the authoritative prepaid balance/concurrency decision.

### 4. Request envelope parsing

After authentication, the gateway parses the body once as a JSON object and
retains its fields in an owned map. It does not deserialize the complete public
request into a Rust struct with `deny_unknown_fields`. The gateway reads and
validates only the protocol fields it must understand to do its job:

- required bounded `model` string;
- required nonempty `messages` array;
- optional boolean `stream`, defaulting to false;
- optional positive `max_completion_tokens` or legacy `max_tokens`, but not
  both.

The message array and all remaining fields stay as their original JSON values
for later model-specific qualification and forwarding. The envelope parser
does not enumerate message roles, content parts, sampling controls, tool
schemas, structured-output formats, or SGLang extensions. It rejects malformed
JSON, a non-object body, duplicate top-level keys, and invalid gateway-owned
fields. It does not drop or coerce a caller field during envelope parsing.
Model qualification removes optional fields that the selected model does not
advertise.

If neither output-token field is present, the gateway uses the text output
modality's projected `default_length`. The control-plane Zod write schema
materializes 1,024 tokens capped by the model's `max_length`, so Rust never
invents this catalog default. The effective ceiling is used for bounds and
admission; other omitted parameters retain the pinned runtime/model defaults.

### 5. Canonical model and parameter qualification

1. Convert the requested model ID to ASCII lowercase.
2. Read `model:<normalized_model_id>` directly from Valkey.
3. Strictly deserialize `GatewayModel` and its closed `ModelProperties`.
4. Require `model.id` to equal the normalized request model exactly.
5. Reject `unavailable` or `retired` models for inference.
6. Read the model's projected `deployments` array from that same
   `GatewayModel` value.
7. Select the first valid `available` deployment in projection order; reject a
   missing, malformed, or empty route set.
8. Read the text output modality's `supported_parameters` and the model's
   request-scoped `passthrough_parameters` maps.
9. Validate every advertised non-envelope top-level field against its
   model-specific descriptor. Remove optional fields that the selected model
   does not advertise.
10. Apply the descriptor's outer type, range, enum, and size checks without
    recreating every nested OpenAI or SGLang type in Rust.
11. Preserve every qualified, supported JSON value unchanged in the upstream
    body and capture effective pricing and the deployment release digest.

The `GatewayModel` is the complete current PostgreSQL record of the model and its
deployments, read through Valkey. Nothing projects it: a cache miss reads
PostgreSQL and caches the row for `GATEWAY_RECORD_CACHE_TTL_SECONDS`, and a model
PostgreSQL does not have is never cached. The launch lookup has no scoring, alias expansion,
fallback, provider selection, or network discovery. The descriptor map is the
public capability list. It does not claim that every model supports the same
parameters. Adding a parameter normally changes
the model catalog and its conformance fixtures rather than the Rust request
type. Complex values such as messages, tools, multimodal content, and response
formats receive cheap gateway-owned structural and resource bounds; the pinned
SGLang/model combination owns their deep semantic validation and combination
rules. Its caller-caused validation failures are normalized to the public
`400 invalid_request` shape.

The gateway never forwards a field merely because the current SGLang version
happens to accept it. SGLang's private protocol also exposes deployment and
debug controls that are not part of the customer API, and some unknown fields
may be ignored rather than rejected. A field reaches the runtime only after an
operator has deliberately advertised it for the exact model and its
conformance test has passed.

### 6. Exact input and context bounds

The gateway must enforce token bounds using the qualified tokenizer rather than
a character-count estimate. After resolving the deployment, it obtains a
`ModelTokenizer` for the exact `tokenizer_path` and immutable
`tokenizer_revision`. The tokenizer artifact supplies the vocabulary,
special-token configuration, and chat template used by both the gateway and
that deployment's SGLang OpenAI-compatible server. A chat-template override is
not an implicit runtime default: adding one later requires an explicit,
digest-covered release field and matching gateway/SGLang conformance.

The optional, digest-covered `tokenizer_mode` release field selects a pinned
non-Hugging-Face renderer. `deepseek_v4` uses the DeepSeek V4 message encoding
with the release's exact tokenizer artifacts. A live vLLM token-ID conformance
fixture must pass before this mode can serve a deployment.

The optional, digest-covered `runtime_model_name` field maps the public model
ID to the private runtime model name. The gateway uses it only in the upstream
request body. Public requests, responses, accounting, and release selection
continue to use the public model ID.

1. Render the qualified request with the pinned chat template and the same
   generation-prompt semantics used by SGLang.
2. Tokenize the rendered input locally in the gateway process on CPU and
   require a valid `input_tokens` count.
3. Read text input `supported_inputs.max_prompt_length` and
   `max_context_length`, plus text output `max_length`, from the captured model
   properties.
4. Require the effective output-token ceiling to be at most
   output `max_length`.
5. Require `input_tokens <= max_prompt_length`.
6. Require `input_tokens + effective_output_tokens <= max_context_length` using
   checked arithmetic.
7. Return `400 context_length_exceeded` when a token bound fails.

Tokenization happens only after authentication and model qualification. It
does not call SGLang, use a GPU, or create a lease. The gateway immediately
discards the rendered prompt and token IDs after retaining the count, so they
do not remain live while generation runs. Qualification fails closed if the
selected release's pinned tokenizer or template cannot be loaded. `ModelTokenizer`
resolves artifacts through the Hugging Face local cache and caches a compiled
tokenizer for each exact `tokenizer_path` plus `tokenizer_revision`. Release
conformance compares local token IDs and counts with the pinned SGLang deployment
for representative messages, tools, special tokens, and output-prefix
behavior.

### 7. Atomic paid admission

Admission executes one versioned Lua script with these keys, which share the
settlement hash tag where atomic writes are required:

```text
account:{settlement-0}:<organization_id>
inflight:{settlement-0}:<organization_id>
generation-settled:{settlement-0}
```

The script receives the generation ID, organization ID, current time, lease
expiry, and cleanup cutoff as Unix epoch milliseconds, followed by the prepaid
organization concurrency cap, balance per concurrency slot, and maximum safe
stream backlog. It performs the following operations without interleaving:

1. Validate every numeric argument before writing.
2. Validate the account is a hash.
3. Validate the in-flight key is absent or a sorted set.
4. Validate the terminal-event key is absent or a stream.
5. Recheck organization identity, `organization_status = active`, and the
   closed `billing_mode` value.
6. For `prepaid`, recheck `balance > 0`. For `invoiced`, do not gate admission
   on balance.
7. Reject when the settlement stream length is at or above its configured
   safety ceiling, so an admitted request cannot knowingly increase an already
   full backlog.
8. Remove only leases older than the configured grace cutoff.
9. Count leases with scores later than the current time.
10. Select `organization_concurrency_cap` as the ceiling. For `prepaid`, lower
    it to `max(20, ceil(balance / balance_per_concurrency_slot))`, using checked
    positive integer arithmetic. Any positive prepaid balance allows 20 slots
    within the organization cap; additional balance above that floor increases
    concurrency proportionally.
11. Reject at or above the selected ceiling with `429 concurrency_exceeded`.
    The cap applies to `invoiced` accounts too, because it protects shared
    capacity rather than billing.
12. Add the new lease with `ZADD NX` and its expiry timestamp.
13. Return a distinct error if the generated ID already exists.

Admission does not reserve money or store request metadata. If admission fails,
the gateway makes no Chat Completions request to SGLang.
For prepaid accounts, `balance_per_concurrency_slot` is only the scale that
converts current balance into an allowed concurrency count. It is not a
request-cost estimate, reservation, or hard downside bound. A prepaid request
is not rejected merely because its theoretical maximum charge exceeds the
balance or per-slot amount. Concurrent prepaid generations can move the
operational balance below zero before terminal charges become visible;
subsequent prepaid requests are then blocked until the balance is positive.

For invoiced accounts, balance is an accounting position that starts at zero
and becomes negative as usage accrues. It does not control admission or
concurrency. Invoiced organizations use the same organization concurrency cap, defaulting
to 500, and also compete for the bounded capacity of the selected SGLang
deployment. `organization_status = suspended` is the explicit mechanism for
stopping an invoiced organization.

Initial operational defaults and requirements are:

| Setting                                  |                        Value |
| ---------------------------------------- | ---------------------------: |
| request-body ceiling                     |     32 MB (32,000,000 bytes) |
| normalized output `default_length`       | 1,024 capped by `max_length` |
| total-generation timeout                 |                  630 seconds |
| lease finalization margin                |                   60 seconds |
| expired-lease cleanup grace              |                    5 minutes |
| maximum organization concurrency         |                          500 |
| minimum prepaid concurrency (within cap) |                           20 |
| balance per concurrency slot             |  1,000,000,000 nano-USD ($1) |

Production validates every value at startup. The settlement-backlog ceiling is
required production configuration rather than a silent default.

### 8. Transfer to `GenerationTask`

After successful admission, the coordinator creates an immutable
`GenerationContext` containing:

- generation ID;
- API-key, workspace, and organization IDs;
- optional bounded external request ID;
- exact model ID and served-release digest;
- whether the response is streamed;
- captured pricing components;
- authoritative input tokens;
- received and admitted timestamps;
- absolute request deadline and lease expiry.

`GenerationContext` never contains the raw request body, messages, prompt
content, serialized upstream body, or response content. Those values are not
needed for settlement or cancellation and must not remain owned by the
generation while SGLang is running.

It then transfers ownership of the lease and upstream request to one
`GenerationTask`. From this point onward, handlers, stream bodies, timeout
tasks, and cancellation paths communicate with that owner rather than
finalizing independently.

### 9. Fixed lease lifetime

1. Before admission, the gateway derives an absolute request deadline from the
   configured total-generation timeout.
2. The lease expiry is fixed to that deadline plus the configured finalization
   margin, using checked timestamp arithmetic.
3. The gateway never renews or extends the lease.
4. Normal success, failure, or cancellation finalizes and removes the lease
   immediately rather than waiting for expiry.
5. If the process disappears, the orphaned lease continues to consume one
   concurrency slot only until its fixed expiry. It then stops counting and
   remains available during the cleanup grace period for delayed finalization.
6. The gateway's hard request timeout occurs before lease expiry and follows
   the normal server-cancellation and finalization path.

This deliberately accepts slower slot recovery after a process crash in
exchange for removing a heartbeat task, renewal traffic, and a separate
renewal-failure path. The total-generation timeout must cover the longest
supported request; an unbounded generation is not admitted.

### 10. SGLang dispatch

The gateway constructs a new qualified upstream request. It does not forward
the customer's raw JSON object.

The upstream body contains the gateway-owned envelope, every JSON field
qualified by the exact model's parameter allowlists, the effective bounded
output-token ceiling, and runtime-required usage options. For streaming, the
gateway always sends SGLang `stream_options.include_usage = true` and the
private extension `stream_options.continuous_usage_stats = true`, regardless
of the caller's public stream options. Qualified caller values are preserved
rather than translated or reconstructed field by field.

Continuous usage is an internal gateway/runtime contract. The gateway removes
intermediate SGLang usage fields from public content chunks and emits the
documented public usage shape only in the terminal chunk. Release conformance
must prove that the pinned SGLang version supplies cumulative usage on
intermediate content, reasoning, and tool-call chunks.

Request content has a deliberately short in-memory lifetime. The gateway may
temporarily hold the capped raw JSON bytes, the validated request and the
serialized upstream request while parsing and transmitting it. It must:

1. drop the raw JSON bytes immediately after successful deserialization;
2. move validated messages into the qualified upstream request without an
   additional application-level clone;
3. release the qualified request and serialized body as soon as the HTTP
   request body has been fully transmitted to SGLang; and
4. retain only `GenerationContext` and bounded response-processing state while
   waiting for generation, which may take minutes.

The transient parse-and-upload memory peak is acceptable and remains bounded
by a small constant multiple of the request-body ceiling. Prompt or message
content is never placed in the in-flight lease, another Valkey key,
`GenerationSettled`, logs, metrics, or traces. Tests with a deliberately
delayed SGLang response must prove that the gateway does not retain request
content for the duration of generation.

The client adds only the private authentication configured for that deployment.
It applies bounded connection, response-header, idle, and total-generation
timeouts. `started_at` is recorded when the generation is dispatched.

The gateway never automatically retries an inference request. A lost response
does not prove that SGLang failed to execute it, so retrying could duplicate GPU
work and billing.

The gateway waits for SGLang response headers before committing public
streaming headers. If SGLang rejects the request for runtime overload, the
gateway normalizes the response to `429 capacity_exceeded`. A post-admission
overload performs normal zero-charge terminal finalization before returning
the error. It never tries another deployment.

### 11. Non-streaming response

1. Read the bounded upstream response.
2. Reject an unsuccessful HTTP status through the normalized runtime-error
   mapping.
3. Strictly deserialize choices, finish reason, and usage.
4. Require authoritative usage before classifying success.
5. Normalize usage and calculate the charge using captured prices.
6. Construct the closed terminal properties document.
7. Atomically finalize in Valkey.
8. Return the normalized response only after finalization succeeds.
9. Include authoritative input, output, and total token usage plus
   `x-gradiated-generation-id`.

If finalization cannot be confirmed after bounded retry, the request returns
`503 finalization_unavailable`, gateway readiness becomes unhealthy, and a
high-severity metric is emitted. No alternate ledger is written.

Anthropic Messages and OpenAI Responses clients receive no reasoning, streamed
or not, and a Messages tool call carries no empty text block. Both providers
reject reasoning they did not produce, and clients send back what they receive,
so this keeps a thread able to fall back to a provider model. Chat Completions
clients keep `reasoning_content`. Usage still counts reasoning tokens. The
[proxy feature plan](../../../docs/PROXY_FEATURE_PLAN.md#thread-continuity)
records the measurements.

### 12. Streaming response

Streaming uses a producer task and a small bounded channel to the Axum response
body:

```text
SGLang byte stream
  -> strict SSE parser and response normalizer
  -> bounded channel
  -> Axum response body
  -> client
```

The `GenerationTask` is the only upstream reader and follows these rules:

1. Parse SSE framing rather than forwarding arbitrary upstream bytes.
2. Strictly validate each JSON data event.
3. Forward only OpenAI-compatible normalized chunks.
4. Record `first_token_at` when the first usable output is delivered.
5. Remember whether any usable output reached the client.
6. Strictly validate every cumulative usage snapshot supplied by SGLang,
   require token counts to be monotonic, and retain the latest snapshot.
7. Emit an SSE comment every ten seconds while the runtime is silent.
8. Stop reading upstream when the bounded response channel is full; this
   provides backpressure without an unbounded buffer.
9. Require a final usage-bearing chunk for successful completion.
10. Normalize and send the final usage chunk.
11. Finalize the generation.
12. Send `[DONE]` only after finalization is confirmed.

The gateway returns `x-gradiated-generation-id` with the initial streaming response
headers. The final streaming chunk and non-streaming response expose the same
normalized usage semantics.

### 13. Client cancellation

Client disconnection is detected when the bounded response channel closes or a
response-body send fails:

1. Stop producing client events.
2. Drop the SGLang HTTP response immediately. The closed streaming connection
   must cause the pinned SGLang runtime to abort queued or running work and
   release its scheduler/KV-cache capacity.
3. Set status `cancelled` and `cancellation_owner = client`.
4. Set `usable_output_delivered` from the owner's recorded delivery state.
5. Use the latest validated cumulative SGLang usage snapshot observed before
   cancellation; if no snapshot was observed, runtime usage is zero. Tokens
   produced after the last received snapshot are not estimated.
6. Calculate the corresponding charge.
7. Execute normal atomic terminal finalization.

The owner does not try to write another HTTP error to a disconnected client.
Continuous usage substantially reduces cancellation undercounting but cannot
eliminate the final race between SGLang generating another token and observing
the cancelled connection. That bounded undercharge is accepted at launch; the
gateway does not re-tokenize partial text and call it authoritative usage.

### 14. Runtime failure and server cancellation

Terminal classification is closed and deterministic:

| Condition                                         | Status      | Cancellation owner | Charge basis                                         |
| ------------------------------------------------- | ----------- | ------------------ | ---------------------------------------------------- |
| Valid terminal response with usage                | `succeeded` | `null`             | Authoritative terminal usage.                        |
| SGLang connection failure before accepted work    | `failed`    | `null`             | Zero unless authoritative usage exists.              |
| SGLang non-success response                       | `failed`    | `null`             | Usage in a validated error response, otherwise zero. |
| Malformed or truncated stream                     | `failed`    | `null`             | Latest authoritative observed usage.                 |
| Client disconnect                                 | `cancelled` | `client`           | Latest authoritative observed usage.                 |
| Gateway timeout or internal cancellation          | `cancelled` | `server`           | Latest authoritative observed usage.                 |
| Explicit SGLang cancellation                      | `cancelled` | `runtime`          | Latest authoritative observed usage.                 |
| Process recovery cannot classify an owned request | `abandoned` | `server`           | Only authoritative recovered usage; normally zero.   |

Raw upstream bodies, prompts, partial completions, private URLs, and attempt
arrays never enter `GenerationProperties`.

### 15. Usage normalization

SGLang usage is normalized into:

```text
input_tokens
cached_input_tokens
cache_write_tokens
output_tokens
reasoning_tokens
```

Normalization validates that all values are nonnegative, cached input does not
exceed total input, and arithmetic is representable. Public `total_tokens` is
derived with the qualified runtime semantics and checked against any upstream
total. A mismatch is a runtime-contract failure rather than a value the gateway
silently repairs.

Until reasoning behavior is qualified and advertised, reasoning-specific
request fields are rejected and `reasoning_tokens` remains zero. Cached-input
and cache-write quantities likewise remain zero until SGLang supplies their
authoritative usage and the exact behavior is qualified.

### 16. Pricing and charge calculation

During exact-model qualification, before admission or SGLang dispatch, the
gateway captures the effective unit prices from the validated `GatewayModel`
value already read from Valkey. Those prices become immutable request state in
`GenerationContext`. The gateway never refetches model pricing after
generation. It does not supply missing catalog defaults: the control-plane Zod
write schema has already normalized the PostgreSQL document and its Valkey
projection.

Pricing at finalization is a pure function over those captured prices and
normalized usage. It uses checked integer nano-USD arithmetic and emits every
configured component, including zero-quantity or zero-price components.

| Model price type     | Quantity                                                                        |
| -------------------- | ------------------------------------------------------------------------------- |
| `prompt`             | all input tokens, or uncached input when `cached_prompt` exists                 |
| `cached_prompt`      | cached input tokens                                                             |
| `cache_write`        | cache-write tokens when authoritatively reported                                |
| `completion`         | all completion tokens, or non-reasoning output when `internal_reasoning` exists |
| `internal_reasoning` | separately reported reasoning tokens                                            |

For every component, `amount = quantity * unit_price`, and component amounts
must sum exactly to `usage.charge`. The normalized model projection always
contains `prompt`, `cached_prompt`, and `completion`; defaulted cached-input
pricing equals prompt pricing. A separate reasoning component exists whenever
reasoning is advertised. A free local model uses explicit zero-cost required
pricing entries. Overflow or inconsistent pricing is a configuration error,
never a wrapped, rounded, or silently truncated amount.

A catalog price change affects only requests that qualify after the new
`GatewayModel` has been projected to Valkey. Already admitted requests retain
their captured prices, and already settled ClickHouse generations retain their
complete pricing components and charge. Neither finalization nor PostgreSQL
settlement recalculates historical charges from the current model catalog.

### 17. Atomic terminal finalization

The owner constructs the closed properties JSON without `settlement` and
invokes one versioned Lua script with:

```text
account:{settlement-0}:<organization_id>
inflight:{settlement-0}:<organization_id>
generation-settled:{settlement-0}
```

The script:

1. Validates generation ID, charge, properties JSON, and all key types before
   writing.
2. Validates the account organization identity.
3. Removes the generation from the in-flight set.
4. Returns `already_absent` without financial or stream mutation when the lease
   was not present.
5. Decrements `GatewayAccount.balance` by the nonnegative actual charge.
6. Appends exactly one stream entry containing `generation_id` and
   `properties`.
7. Returns `settled` only after both mutations have executed.

Because the lease is removed in the same script, a lost successful reply and
retry cannot create a second charge or stream entry. There is no
`settled:<generation_id>` key.

The gateway retries an unconfirmed finalization for a short bounded interval.
If the process is lost before completion, the lease eventually expires and may
remain briefly for grace-period cleanup. The resulting bounded unbilled loss is
the accepted launch tradeoff documented by the parent data model.

### 18. Response completion and cleanup

After terminal handling:

1. Record terminal metrics and a sanitized structured event.
2. Drop request-local identity, pricing, and upstream state.
3. For non-streaming success, return the buffered normalized response.
4. For streaming success, finish after `[DONE]`.
5. For a connected streaming client whose request fails mid-stream, emit one
   bounded OpenAI-compatible error event when the wire contract permits it,
   then terminate without `[DONE]`.

## `GET /v1/models` lifecycle

The models route uses the same bearer authentication and workspace/account
access checks as Chat Completions but does not create a lease.

1. Authenticate the caller and check workspace/account access.
2. Enumerate exact IDs from the bounded `gateway-model-ids` Valkey set; do not
   use `KEYS` or an unbounded Valkey scan.
3. Fetch each corresponding `GatewayModel` and its deployment status hash.
4. Exclude retired, malformed, or missing-deployment models.
5. Set `is_ready = true` when at least one deployment has fresh healthy status.
6. Include explicitly staged unavailable models with `is_ready = false` so the
   OpenRouter monitor can observe them without sending inference traffic.
7. Report healthy installed concurrency in the root `capacity` array. Include
   a healthy deployment when it is temporarily busy.
8. Convert integer nano-USD token prices to exact base-10 USD strings.
9. Require `released_at` before advertising a model because the provider
   document requires a creation timestamp.

The response never exposes `service_url`, `SGLANG_API_KEY`, artifact revisions,
or the internal served-release digest.

## Deployment records and release identity

`GatewayModel` is Zod-authored and projected from the PostgreSQL model plus all
of its deployment rows. Rust strictly validates the complete Valkey document.
An available model must have at least one valid available child deployment.
Fresh deployment status controls live routing. Missing routes fail closed.

The served-release digest is calculated over the selected deployment's closed `release`
object: SGLang runtime revision, model path and immutable revision, and
tokenizer path and immutable revision. The tokenizer revision includes its
chat template and special-token configuration. The digest excludes the
service URL, gateway-wide timeout, customer prices, and deployment status.

The gateway reads the optional upstream credential from the fixed
`SGLANG_API_KEY` process secret supplied by the deployment. It does not call
AWS Secrets Manager directly. The secret never appears in a model projection, error
response, trace, or metric.

## Runtime overload and exact dispatch

Every exact model maps to independent runtime deployment candidates. Desmond
sends status every second. The gateway rejects stale, unhealthy, draining, or
not-accepting candidates. It uses rendezvous hashing, weighted by each
runtime's reported `active_requests`, for stable placement. It does not queue
and it does not enforce a concurrency limit: the engine owns admission.

A model is ready when at least one fresh healthy deployment reports status. The
catalog publishes no capacity limit. A malformed status document drops only its
own deployment.

One request can use at most two sequential runtime attempts. A retry requires
an availability or capacity failure, no usable output, time on the shared
deadline, and another deployment for the same release. The second attempt
prefers another fault domain. A started public stream is never retried. Both
attempts use one generation ID and one settlement.

Per-organization concurrency remains separate and is always enforced by the
Valkey admission script before generation dispatch. It limits customer
financial exposure and fairness, not GPU capacity.

The runtime remains authoritative for KV cache use and exact scheduler state.
Desmond sets `accepting_requests: false` before severe KV or queue pressure.

## Error mapping

| HTTP status | Stable code examples                                                           | Meaning                                                  |
| ----------: | ------------------------------------------------------------------------------ | -------------------------------------------------------- |
|       `400` | `invalid_request`, `unsupported_parameter`, `context_length_exceeded`          | Caller input cannot be executed as requested.            |
|       `401` | `invalid_api_key`                                                              | Missing, invalid, expired, or revoked credential.        |
|       `402` | `insufficient_balance`                                                         | Prepaid operational balance is not positive.             |
|       `404` | `model_not_found`, `model_unavailable`                                         | Exact requested model cannot currently serve.            |
|       `413` | `payload_too_large`                                                            | Request exceeded the transport body ceiling.             |
|       `429` | `capacity_exceeded`, `concurrency_exceeded`, `settlement_backlog`              | SGLang overload or gateway admission rejection.          |
|       `503` | `serving_state_unavailable`, `runtime_unavailable`, `finalization_unavailable` | Required serving dependency or invariant is unavailable. |

Errors caused by caller input do not mark readiness unhealthy. Valkey
unavailability, configured-runtime unavailability, invalid loaded catalog
state, or finalization failure does.

## Health and readiness

`/health/live` reports success while the process event loop and HTTP server are
running. It performs no dependency calls.

`/health/ready` uses short bounded checks and succeeds only when:

- startup configuration remains valid;
- Valkey accepts a read command;
- every model that is currently `available` has at least one valid available
  deployment and its SGLang endpoint is healthy;
- no recent finalization failure has opened the local readiness circuit.

An empty catalog is valid while no GPU deployments are configured. The gateway
remains ready and exact inference requests return `model_not_found` until a
model is projected. Unavailable models staged with `is_ready = false` also do
not make the process unready.

Readiness recovers after dependencies pass consecutive probes and the
finalization circuit's bounded recovery condition is satisfied.

## Telemetry and privacy

Structured logs may contain:

- generation ID;
- authenticated organization, workspace, and API-key IDs;
- exact model ID;
- lifecycle phase;
- terminal status;
- bounded internal error code;
- durations and integer usage totals.

These IDs are structured correlation fields, not free-form message text. They
allow an operator to follow one generation and relate it to the organization,
workspace, and credential visible in product state. They are attached only
after the corresponding identity has been authenticated and validated. The
authenticated request identity has no user ID, so the gateway does not invent or fetch one
for inference logs.

They must not contain:

- raw or digested API keys;
- prompts, completions, or unredacted request bodies;
- private SGLang URLs or secret references;
- raw upstream response or error bodies.

The `inference_body` diagnostic retains a bounded redacted JSON envelope for
client and effective runtime requests, buffered responses, public errors and
selected streaming frames. Sensitive payload values are replaced in place;
recognized API keys, structure, numeric/boolean operational settings and known
control enums remain. Unknown field names and their values are redacted, as are
unknown free-form strings. The shared redactor also removes
credentials, schema/tool payloads, media, encoded tokens and echoed error input.
Malformed/oversized bodies produce summaries without content. See
[`docs/OBSERVABILITY.md`](../../../docs/OBSERVABILITY.md) for limits and stages.

Failure diagnostics are emitted at lifecycle boundaries, not per token. Routing
failures include candidate counts by exclusion reason (including
missing/stale status, release/revision mismatch and capacity); runtime attempts
include deployment ID, attempt, upstream HTTP status, bounded transport/failure
class, elapsed time and retry selection. Streaming failures after response startup
include a terminal reason and whether usable output was delivered. Ordinary client
disconnects do not produce warnings. Capacity cleanup and exhausted settlement
retries have explicit diagnostics; settlement errors are never sampled. Dependency
readiness logs initial failure, failure transitions and recovery, not each probe.

Request-failure warnings, including the HTTP rejection summary, are limited to ten
per second per call site per gateway process. The next emitted event reports the
number suppressed at that site; no payloads or per-customer maps are retained.
Metrics remain unsampled. Under this limit, use `generation_id` (also returned as
`x-gradiated-generation-id`) to correlate the HTTP summary with the detailed lifecycle event.
During an outage a sampled generation may have only one of those events. These
logs do not create ClickHouse generation rows for pre-admission rejections.

Initial Prometheus instruments cover:

- request totals by route, HTTP status, and bounded error class;
- admissions, active generations, and terminal outcomes by exact model,
  deployment ID, and streaming mode;
- admission rejections by the same serving labels and a bounded reason;
- gateway-receipt-to-dispatch latency, runtime latency, and end-to-end
  generation latency;
- TTFT from gateway receipt and from runtime dispatch for streamed responses;
- TPOT after the first delivered token and output-token throughput over the
  complete runtime interval;
- authoritative token totals and per-generation input/output distributions;
- calculated terminal charge totals in integer nano-USD;
- finalization attempts, retries, no-ops, and failures;
- gateway, Valkey, catalog, and SGLang readiness.

TTFT and TPOT are emitted only when the gateway observes streamed token
delivery. Non-streaming responses do not invent a first-token timestamp. TPOT
is `(terminal_time - first_token_time) / (output_tokens - 1)` when at least two
authoritative output tokens exist. Output throughput is authoritative output
tokens divided by the full runtime interval, including TTFT. Calculated charge
is operational telemetry, not the billing ledger; ClickHouse settlement state
remains authoritative for billed revenue.

Metric labels use closed enums or the bounded configured model and deployment
sets. Deployment IDs are allowed because they identify the small serving fleet
and are required to compare runtimes. Organization, workspace, API-key, user,
and generation IDs, free-form messages, served-release digests, private URLs,
and upstream status text are never metric labels even when an ID is present in
structured logs.

## Local native SGLang

The canonical local workflow runs both the gateway and SGLang as native host
processes under mprocs. Docker Compose remains limited to PostgreSQL, Valkey
and ClickHouse. A checked-in mise task backed by a pinned uv environment starts
SGLang on `http://127.0.0.1:30000`; the local PostgreSQL deployment row is
projected into `GatewayModel` with that address, so the gateway uses the same
HTTP adapter and request lifecycle as production.

The supported Apple Silicon profile uses SGLang's Metal/MLX backend with a
pinned quantized `mlx-community/Qwen3-0.6B-4bit` model and tokenizer revision.
Local seed state declares it under its own exact ID, for example
`mlx-community/qwen3-0.6b-4bit`. It must not reuse `moonshotai/kimi-k3`, because
exact model identity is an invariant rather than a convenient alias. The local
profile exercises real SGLang:

- liveness and readiness;
- parity between gateway-local tokenization and the pinned SGLang release;
- gateway-local context-bound enforcement without an SGLang tokenization call;
- non-streaming Chat Completions and terminal usage;
- streaming SSE, final usage, backpressure and cancellation.

Focused coordinator and lifecycle tests replace `ModelRuntime` in process to
produce deterministic overload, HTTP error, malformed payload, truncated
stream and timeout cases. This test double is not an HTTP service, is not part
of mprocs, and cannot be selected in a production build. Local MLX conformance
proves the gateway/SGLang protocol boundary; final release conformance uses the
pinned production CUDA SGLang image, tokenizer and exact Kimi K3 revision.

## Contract ownership

The TypeScript contracts package authors:

- the small gateway-owned Chat Completions envelope;
- the closed parameter-descriptor grammar used by each model's supported and
  pass-through parameter maps;
- strict Chat Completions response schemas;
- streaming event schemas;
- provider `/v1/models` schema version `2.4`;
- `ModelDeploymentRelease` and the deployment children of `GatewayModel`;
- `GenerationProperties` and `GenerationSettled`;
- accepted and rejected cross-language fixtures.

Generation produces OpenAPI/JSON Schema and fixtures. Rust uses strict
handwritten Serde types with unknown-field denial for internal gateway records,
deployment releases, and events. The customer request instead uses a small typed envelope
over an owned JSON map plus the selected model's descriptor map. Fixtures prove
the envelope and descriptor behavior across languages, while per-model
conformance proves that advertised pass-through parameters work against the
pinned runtime. This avoids both a brittle generated Rust API and a blind JSON
proxy.

## Verification plan

### Contract tests

- accepted and rejected TypeScript/Rust envelope fixtures;
- model-specific advertised-parameter acceptance and unadvertised-parameter
  removal;
- preservation of qualified nested JSON values without coercion or silent
  field loss;
- provider schema `2.4` model-document validation;
- generated artifacts have no diff after regeneration.

### Authentication and access tests

- missing and malformed bearer values;
- unknown, expired, and revoked credentials;
- archived workspace and suspended organization;
- cross-workspace and cross-organization gateway-record mismatch;
- missing, malformed, and unavailable Valkey state;
- direct and OpenRouter organizations following the identical path.

### Model and bounds tests

- exact available model success;
- unknown, unavailable, retired, and missing-deployment rejection;
- output and context-bound rejection;
- tokenizer/template load failure at startup and caller-caused local
  tokenization failure;
- token-ID and token-count parity with the pinned SGLang release;
- proof that every pre-admission rejection causes zero generation calls.

### Valkey state-machine tests

- positive and nonpositive prepaid balance admission;
- prepaid balance-derived concurrency boundaries, including proportional
  reduction as balance falls, the floor of 20, and the default cap of 500;
- invoiced admission at zero or negative balance with the same organization
  concurrency cap;
- admission does not compare theoretical maximum request cost with balance or
  the per-slot concurrency scale;
- early settlement-backlog closure;
- simultaneous admissions at the same boundary;
- duplicate generation ID;
- fixed lease expiry covering the request deadline and finalization margin;
- expired orphaned leases stopping concurrency before grace-period cleanup;
- terminal finalization charging and appending exactly once;
- repeated finalization producing no second mutation;
- expired or missing lease producing no financial or stream mutation;
- account, in-flight, and stream keys sharing the same cluster hash slot.

These tests run against real local Valkey in addition to focused coordinator
tests with a fake `ServingState`.

### Runtime lifecycle tests

- official OpenAI clients calling streaming and non-streaming routes;
- final input, output, and total usage;
- `x-gradiated-generation-id` on both response modes;
- slow-token keep-alives;
- bounded streaming backpressure;
- client disconnect cancelling the upstream request, with conformance proving
  the pinned SGLang runtime releases the corresponding queued/running slot;
- cumulative intermediate SGLang usage being monotonic and retained without
  being exposed as public per-chunk usage;
- cancellation charging the latest observed cumulative usage, and
  cancellation before the first usage snapshot charging zero;
- runtime overload normalized to `429 capacity_exceeded`;
- runtime timeout, other HTTP error, malformed response, and truncated SSE;
- one pre-output retry on another deployment.

### Usage and pricing tests

- input, cached-input, output, reasoning, request, free, and discounted price
  components;
- zero-quantity components;
- arithmetic overflow and inconsistent usage rejection;
- component sum exactly matching terminal charge;
- success, failure, cancellation, and abandonment event shapes.

### Operations and privacy tests

- liveness independent of dependencies;
- readiness transitions for Valkey, available models, and finalization failure;
- bounded metric label cardinality;
- assertions that logs and metrics contain no secret or request content;
- shutdown immediately closes readiness and admission while allowing owned
  generations to finish naturally for the configured 630-second request
  window; only generations still active after that bounded drain are cancelled
  and finalized as server-owned cancellations;
- rolling deployment conformance with two replicas, zero unavailable pods, a
  670-second ALB deregistration delay, a short pre-stop propagation pause, and
  a 670-second Kubernetes termination grace period.

### End-to-end checks

- `pnpm dev` starts datastore containers plus the native gateway and SGLang;
- the gateway resolves the local model's projected deployment and reaches SGLang over
  localhost HTTP;
- seeded direct and OpenRouter credentials both complete real local inference;
- unadvertised optional parameters are removed before any `ModelRuntime`
  invocation;
- parameters advertised by the local model reach SGLang unchanged;
- Rust format, Clippy, unit, integration, and conformance checks pass;
- repository DevEx and whitespace checks pass.

## Implementation sequence

1. Author inference, event, and model-deployment contracts plus cross-language fixtures.
2. Scaffold the Rust crate, configuration, Valkey model projection, HTTP shell, health,
   telemetry, native SGLang task, and local exact-model seed.
3. Implement authentication, workspace/account access checks, exact model
   resolution, and request bounds.
4. Implement atomic admission, fixed leases, non-streaming execution, usage,
   pricing, and finalization.
5. Add the streaming owner task, bounded SSE pump, keep-alives, cancellation,
   and mid-stream failure behavior.
6. Integrate the datastore Compose stack, native-service mprocs workflow,
   production gateway image, ingress rewrite, dashboards, and alerts.
7. Run local conformance and state-machine tests before connecting an external
   Kimi K3 deployment.

Each step must leave the narrow behavior tested and keep the gateway runnable
against native local SGLang. Production inference is not enabled until the
same contract passes against the pinned Kimi K3 model and tokenizer release.

## Review checklist

Review comments should focus on whether:

- component boundaries are still smaller than the behavior they organize;
- every post-admission exit has one terminal owner;
- any proposed behavior violates the canonical Valkey data model;
- public contract fields match the intended Kimi K3 launch subset;
- failure and partial-usage charging semantics are acceptable;
- operational defaults should be changed before implementation;
- the ALB prefix-rewrite and single-replica launch assumptions match the
  production deployment contract.
