# Product handoff

## Current decision

Build the exact-model product in [ARCHITECTURE.md](../docs/ARCHITECTURE.md), the [Kimi K3 provider launch plan](../docs/KIMI_K3_PROVIDER_LAUNCH_PLAN.md), the [canonical data model](../docs/DATA_MODEL.md), and the [product API contract](../docs/API.md).

The direct product remains: Vite/React/shadcn UI served by a TypeScript/Hono API, a TypeScript worker from the same image, organizations/workspaces, API keys, usage and billing. OpenRouter and direct customers use the same Rust gateway. Kimi K3 is the first model and SGLang is the initial external GPU runtime.

## Current implementation

The application slice includes Better Auth, organizations, workspaces, API
keys, the model/deployment catalog, durable balances, Stripe Checkout top-ups,
and the TypeScript settlement worker foundations. Model writes pass through a
normalizing Zod schema before PostgreSQL and Valkey, so the Rust gateway reads a
complete `GatewayModel` projection without supplying catalog defaults.

The Rust gateway includes its HTTP health shell, typed configuration, Valkey
Cluster reads, authentication/access primitives, strict model/deployment
contracts, request-envelope parsing, and the pre-admission
`RequestCoordinator`. The coordinator performs credential, workspace, account,
balance, exact-model, deployment, streaming, output-limit, and model-parameter
qualification. The concrete `ModelTokenizer` resolves and caches the selected
deployment's pinned Hugging Face tokenizer artifacts, renders its
Transformers-compatible chat template, counts locally on CPU, and enforces
prompt and combined context limits. The downstream value retains only
`input_tokens`; rendered prompts and token IDs are discarded. The pinned local
Qwen artifact smoke test passes.

`ValkeyServingState::admit` now executes one versioned Lua script across the
co-slotted account, in-flight lease, and settlement-stream keys. It validates
the complete mutable serving state before writing, applies balance-funded
prepaid concurrency with the default cap of 50, leaves invoiced concurrency
uncapped even at negative balance, applies settlement backlog pressure, removes
only leases beyond the cleanup grace period, and creates the fixed lease with
`ZADD NX`. Request identity and timestamps are passed directly to admission,
configuration is read only while constructing the Lua invocation, and the
method returns the small lease needed by the remaining request lifecycle.
Focused tests run the script against the real one-node Valkey
Cluster, including simultaneous boundary admissions and `CROSSSLOT` behavior.
The gateway also has the closed Rust `GenerationProperties` contract, pure
checked nano-USD usage pricing, and a versioned atomic finalization script. The
request-lifecycle value types keep their fields private and validate usage,
captured pricing, terminal identity, outcome, timing, and lease invariants when
they are constructed, so pricing and finalization accept only validated state.
The script validates all state before writing, consumes the lease, writes the
updated operational balance, and appends exactly one terminal stream event;
retrying after success returns `already_absent` without a second charge or
event. Real-cluster tests cover successful idempotent finalization and
failure-before-mutation behavior.
The product-only `tests.yml` workflow has independent unit, integration, and
end-to-end jobs so all three run in parallel. Its integration job starts the
complete product Docker Compose dependency stack, waits for Valkey cluster
initialization and service health, and runs this ignored real-cluster suite.
The workflow runs on pull requests and main pushes only when `product/**`
changes. The E2E suite uses an automatic per-test fixture that creates and funds
a unique user, organization, and workspace, allowing its spec files to execute
concurrently without shared account state. The concrete `SglangClient` now
implements the non-streaming
`ModelRuntime` boundary: it constructs a fresh qualified request, consumes the
validated request while serializing it, adds the effective output-token ceiling
without translating the caller's selected field, sends exactly one authenticated
Chat Completions request, and applies bounded header, idle, response-size, and
absolute-deadline limits. Its serialized request body is a non-replayable
one-shot stream and redirects are disabled, so request content is released after
upload and the HTTP stack cannot replay inference while awaiting a non-streaming
response. It strictly normalizes terminal choices and authoritative SGLang
usage, checks upstream total-token arithmetic, removes private response
extensions, and classifies overload as `capacity_exceeded` without retrying.
Focused in-process HTTP tests cover field preservation, private upstream
authentication, non-replayable bodies, redirect rejection, usage normalization,
overload/no-retry, malformed usage, and elapsed deadlines.

`CompletionService` now joins qualification, local bounds, atomic admission,
and the non-streaming runtime path. It constructs every fallible identity value
before admission, proves admission before dispatch, and transfers the lease and
request to one spawned `GenerationTask`. Dropping the awaiting handler signals
that owner; it drops the runtime future before recording a client-owned
cancellation. Success, overload, timeout, runtime failure, usage mismatch, and
client cancellation all pass through one pricing and terminal-properties path.
The owner makes up to three finalization attempts over 50 milliseconds, treats
the lease-backed `already_absent` result as idempotent confirmation, and never
returns a successful response before finalization is confirmed. Focused tests
cover ordering, exact charging, cancellation/runtime drop, overload, successful
retry, and withholding output after an unconfirmed finalization. The public HTTP
route now constructs UUIDv7/`received_at` metadata before transport handling,
enforces the 8,000,000-byte body limit before Valkey, calls `CompletionService`,
and returns the stable error envelope and `X-Generation-Id` on both success and
failure. Axum's owned byte buffer passes directly into qualification without a
second request-body allocation. Focused HTTP tests cover route matching, the
public authentication error, UUIDv7 response metadata, and `413
payload_too_large` before any serving-state lookup. Spawned generation tasks are
not yet tracked for bounded process shutdown.

Production observability now covers the API, worker, gateway, SGLang runtime,
console edge, and Kubernetes workloads. API and worker expose private
Prometheus listeners with bounded-cardinality HTTP, dependency, loop, lag,
business-pipeline, and Node runtime metrics. The gateway's existing generation
and runtime metrics include a telemetry heartbeat. Argo provisions six Grafana
dashboards, HTTPS blackbox probes, failure-oriented Prometheus rules, and
severity-routed Alertmanager webhook delivery. The metric catalog and runbooks
are in [`docs/OBSERVABILITY.md`](../docs/OBSERVABILITY.md).

The canonical `mprocs` stack now includes the native SGLang Metal/MLX process.
The `sglang-local` mise task checks out exact SGLang revision
`8bb106cee94c1ccb5625cdb78ef0ee3e0cad3918` into the ignored cache, installs its
Apple dependency set into an isolated Python 3.12 environment, and serves pinned
`mlx-community/Qwen3-0.6B-4bit` revision
`73e3e38d981303bc594367cd910ea6eb48349da8` on port 30000 with bounded running
and queued requests. `pnpm smoke:gateway` creates and later revokes a real local
API key and exercises API/Valkey/gateway/local-tokenizer/SGLang/finalization.
The measured smoke returned HTTP 200, UUIDv7 `X-Generation-Id`, normalized
14-input/32-output-token usage, and a matching succeeded `GenerationSettled`
entry. First setup took about three and a half minutes for packages and 53
seconds for the 336 MB model; cached restarts avoid those downloads.

## Next product work

Add tracked shutdown and the streaming owner, bounded SSE pump, continuous
usage, keep-alives, and client-cancellation delivery semantics. Then implement
the remaining authenticated `/v1/models` behavior. Calibrate the launch alert
thresholds after seven days of representative production telemetry.

Do not add a second or general gateway, provider router, alias system, generalized fleet service or speculative product surface without a new decision record.
