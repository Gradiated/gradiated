# Gateway

The Rust inference data plane authenticates and admits direct and OpenRouter
requests through Valkey, calls a deployment of the exact requested model, and
settles terminal usage. Its implementation authority is
[ARCHITECTURE.md](ARCHITECTURE.md).

## Request handling

The service provides:

- strict Valkey-projected model and deployment records;
- an immutable served-release digest;
- an always cluster-aware Valkey connection;
- dependency-aware liveness and readiness routes;
- a 32 MB (32,000,000-byte) request-body ceiling;
- structured JSON startup logging and graceful shutdown;
- one atomic Valkey admission script with funded prepaid concurrency,
  the organization concurrency cap for invoiced admission, settlement-backlog
  protection, and fixed leases;
- closed terminal generation properties, checked nano-USD pricing, and one
  atomic finalization script that consumes a lease, debits the balance once,
  and appends the terminal stream event.

The request coordinator connects qualification and exact model selection to
admission, runtime dispatch and terminal settlement. Chat Completions support
streaming; native SystemOne uses the same lifecycle without streaming. No fake
inference endpoint is used.

Chat Completions, Responses, and Messages return `usage.cost` as a JSON number
in USD. This additive field uses the admission-time pricing snapshot and the same
checked calculation as settlement, including cached input, cache writes,
reasoning, and service-tier prices. Existing protocol-specific token fields are
preserved. For example, a charge of 1,234,567 nano-USD returns
`"cost": 0.001234567`.

Streaming returns cost in the final Chat Completions usage chunk, the Responses
`response.completed.response.usage` (or `response.incomplete.response.usage`),
or the Messages `message_delta.usage`. Terminal usage is withheld until settlement
succeeds; failed settlement ends with the protocol's error event. A lease already
missing on the first settlement attempt returns zero cost because no charge was
applied. SystemOne keeps its existing response contract.

The native [OpenAI Chat Completions usage schema](https://developers.openai.com/api/reference/resources/completions),
[OpenAI Responses usage schema](https://developers.openai.com/api/reference/typescript/resources/responses),
and [Anthropic Messages schema](https://platform.claude.com/docs/en/api/messages/create)
do not define a monetary cost field. `usage.cost` follows the
[OpenRouter usage accounting convention](https://openrouter.ai/docs/cookbook/administration/usage-accounting)
and is a Gradiated extension on the native endpoints. OpenRouter's optional
`cost_details.upstream_inference_*` fields describe charges from an upstream
provider; Gradiated does not invent these values for its own hosted runtime.

The token breakdown follows the requested protocol:

| Format           | Cache reads                           | Cache writes                               | Reasoning                                    |
| ---------------- | ------------------------------------- | ------------------------------------------ | -------------------------------------------- |
| Chat Completions | `prompt_tokens_details.cached_tokens` | `prompt_tokens_details.cache_write_tokens` | `completion_tokens_details.reasoning_tokens` |
| Responses        | `input_tokens_details.cached_tokens`  | `input_tokens_details.cache_write_tokens`  | `output_tokens_details.reasoning_tokens`     |
| Messages         | `cache_read_input_tokens`             | `cache_creation_input_tokens`              | `output_tokens_details.thinking_tokens`      |

Chat Completions and Responses include cached tokens in their input total.
Messages excludes cache reads and writes from `input_tokens` and reports them
separately. Cache-write details are omitted when zero. Unknown cache lifetimes,
audio/prediction counts, and server-tool charges are not fabricated. The runtime
normalizer reads the standard nested cache-write and reasoning fields, with the
legacy runtime top-level fields retained as fallbacks.

The official TypeScript SDKs preserve `cost` on parsed non-streaming usage and
raw terminal stream events. Their native TypeScript usage interfaces do not
include the extension, so read it with a property guard:

```ts
const usage = completion.usage;
if (usage && "cost" in usage && typeof usage.cost === "number") {
  console.log(usage.cost);
}
```

OpenAI's `finalChatCompletion()` and `finalResponse()` also preserve cost.
Anthropic's `messages.stream().finalMessage()` aggregates only known native
usage fields and drops cost. Read `message_delta.usage.cost` from the helper's
`streamEvent` callback instead, or iterate `messages.create({ stream: true })`.
These behaviors are exercised against pinned SDKs in
[test/integration/sdk-pricing.test.ts](test/integration/sdk-pricing.test.ts).

## Private LoRA adapters

Chat inference accepts the existing version slug or task production slug as `model`.
After authenticating the API key, the gateway resolves the selector within its
workspace using the existing PostgreSQL task/version records. Only available,
loadable versions are eligible. Each request resolves once; promotions affect
subsequent requests, while streams and retries keep the same immutable version.
Ambiguous task/version names and collisions with public catalog names fail closed.
Inference and generation records accept selectors up to 300 characters, including
the date/ordinal suffix on a 256-character task name. There is no selector cache or adapter
residency state in the gateway.

The base catalog supplies capabilities, tokenization and prices. Routing prefers
LoRA-enabled chat deployments that match the recorded base revision. When none can
serve, or its attempt fails before output, the base model serves the request
without the adapter: first its chat deployments, then OpenRouter if the base model
is mapped. The response keeps the version slug and base prices; settlement records
the base release, or OpenRouter, as what served. A pinned request does not degrade. Each
attempt sends a normal completion request through the existing authenticated ingress,
using the immutable internal model name `<workspace_uuid>/<resolved_version_slug>`.
The runtime client has no adapter preparation call or cache state. vLLM's native
resolver asks the allocation-local loader for verified files on first use; vLLM
owns registration, CPU/GPU caching and streaming. Cold loading counts against the
existing generation deadline. Host failures use the existing inference retry rules.

Responses and settlement name the resolved version slug. Settlement's served
identity hashes the base release digest, version UUID and checksum. Base health
continues to use the base release digest, and metric labels use the base model.
Private versions are not added to the public catalog. The task capture header
continues to label traces independently of adapter selection.

Hosting remains opt-in. Existing hosts need the runtime-readable renewal identity
installed before enabling LoRA; real-artifact and TP2/TP4 co-location qualification
are required. See the [loader configuration](../../inference/lora/README.md).

## Native SystemOne

`POST /v1/systemone` accepts an exact model, text/object/array `state`, and
1..64 named `choice`, `noul`, or `score` questions. Instructions and criteria
support structured JSON. Optional `noul` criteria allow only `false` and `true`
outcome keys; any other key is rejected. Unknown fields, streaming, output-token controls,
caller priority, and `fast`/`flex` are rejected; only `default` is implemented.
An optional `session_id` must contain 1..256 UTF-16 code units.

Deployments whose `release.protocol` is `system_one` use the native
SystemOne transport and cannot serve Chat Completions. They share gateway
authentication, admission, health-based routing, retries and settlement.
Session affinity takes precedence; otherwise routing hashes the first 16 KiB
of serialized state, scoped to workspace, model and served release. Questions
do not affect this state affinity. The runtime reports authoritative prefill
input and cached-input usage with exactly zero output tokens; serialized
answers are not generated tokens. The gateway validates answers and runtime
model identity before returning the requested public model ID.

## Deployment routing

An authenticated workspace can pin a request to one serving replica with
`x-gradiated-deployment-id: <UUID>`. This is the model-deployment record ID,
currently the Kubernetes Pod UID, not a Kubernetes Deployment name or provider
pod ID. The replica must belong to the requested model and have a fresh, healthy,
accepting runtime status. An isolated deployment can be selected explicitly;
draining and unknown targets are rejected. The request has no replica fallback,
and a successful response echoes the same header. Normal workspace authorization,
model access, billing, concurrency limits and production telemetry still apply.
Requests without the header continue using normal routing. Token-count endpoints
reject the selector because they do not dispatch generation to a replica.

Automated SDK checks use the same header with a short-lived key in the configured
internal verification workspace. Targeted requests authenticated to that workspace
retain verification telemetry; other workspaces retain normal production telemetry.
The retired `x-gradiated-verification-deployment` header is rejected.

The gateway selects an exact served release, then ranks its healthy, accepting
deployments by rendezvous hash, weighted by each runtime's reported
`active_requests` (replicas that do not report keep an equal share). Session affinity takes precedence; sessionless
chat requests hash their opening system/developer and first non-system messages,
while SystemOne uses its opening state prefix. Keys include workspace, model,
and release identity. Routing stores no affinity records or per-deployment concurrency leases.

The gateway resolves one affinity key before protocol translation, for both
release and replica selection. Explicit body `session_id`, header
`x-gradiated-session-id`, and body `prompt_cache_key` take priority over SDK
session signals. Claude Code, OpenCode and Codex session headers and structured
metadata are accepted in the [documented preference order](ARCHITECTURE.md#1-transport-acceptance).
SDK identifiers are bounded to 256 bytes; body session IDs retain endpoint
validation (including SystemOne UTF-16 bounds). Invalid explicit overrides return 400;
malformed optional SDK hints fall back to the next source. Request IDs and
window IDs do not drive affinity. Logs record the selected source and hash;
raw identifiers are excluded. Without a usable explicit/SDK key, the gateway
hashes the opening system/developer and first non-system messages, or the first
8192 Unicode characters of the raw request body if the opening messages cannot
be recognized. This fallback is infallible and does not bypass normal API
validation. Stable placement helps reuse resident vLLM prefix blocks but does
not guarantee cache hits or change vLLM cache configuration.

Desmond sends `POST /v1/deployment-status` every second. The API checks provider
ownership and runtime revision, timestamps the report, and writes the release's
Valkey status hash. Reports older than 15 seconds are unusable; the hash expires
after 30 seconds. The gateway caches models and status for one second and fails
closed on a refresh failure. See [DeploymentRuntimeStatus](../../../docs/DATA_MODEL.md#20-deploymentruntimestatus)
for the wire fields and timing bounds.

Having no healthy deployment returns `503`; healthy deployments that are all refusing
new work return `429`. The engine owns admission. Runtime overload (`429` or
`503`) becomes `capacity_exceeded`. There is no gateway queue.

A request can retry once on another deployment of the same release after an
unavailable or capacity failure, before output begins and with no reported
usage. It prefers a different fault domain and, for unavailability, a different
provider. Both attempts share one generation ID, deadline, service tier, price
snapshot, organization lease, and settlement. Invalid requests, protocol errors,
timeouts, and started streams are not retried.

Before generated output starts, the runtime client waits within the existing
generation deadline (630 seconds by default). It cannot distinguish an engine
queue from active prefill. A role-only or empty stream event does not start the
30-second idle limit; content, reasoning or tool-call output does. After output
starts, each event read has a 30-second idle limit, and the original generation
deadline still bounds the entire request. Buffered completions allow the same
prefill wait before response bytes begin, then retain the 30-second body-read
idle limit. Rejection bodies retain their short idle limit. Deployment probes
keep their own four-second total deadline.

For the DeepSeek vLLM runtime, the launch script bounds admission with
`--max-num-queued-reqs` and `--max-num-queued-tokens`. Size these for the deployment's
batch capacity and prefill throughput; a token bound below one full-context
prompt rejects work the engine could otherwise accept. Do not substitute
`num_requests_running` for the engine's admission limits.

OpenRouter's catalog omits a fixed `capacity` declaration: safe concurrency
varies with prompt length. Temporary saturation returns `429`; it does not
change the operator-controlled `is_ready` setting. A stale healthy report can
keep a stopped runtime eligible for up to 15 seconds.

## Run locally

For CPU-only integration tests against real Kev/vLLM HTTP mock servers and
disposable Valkey, see [runtime integration tests](test/integration/README.md).
The gateway is the actual built binary; the suite covers both successful
requests and failure/cancellation/settlement boundaries without GPUs.

From `product/`, `pnpm dev` starts the one-node Valkey cluster and the gateway
alongside the other native services. Run the local seed once to create the
PostgreSQL Qwen model/deployment rows and their aggregate Valkey projection.
SGLang remains a separate native process; until the projection exists and
SGLang is running at its projected URL, the gateway is live but correctly
reports not ready.

```sh
pnpm --filter @gradiated/api seed
```

Run only the gateway after starting the Docker dependencies:

```sh
cd product/services/gateway
VALKEY_URL=redis://127.0.0.1:6379 \
  GATEWAY_SETTLEMENT_BACKLOG_LIMIT=100000 \
  mise exec -- cargo run --locked
```

The local endpoints are:

- `http://127.0.0.1:3002/health/live`
- `http://127.0.0.1:3002/health/ready`

## Configuration

| Variable                                        | Required | Default                           |
| ----------------------------------------------- | -------- | --------------------------------- |
| `VALKEY_URL`                                    | yes      | none                              |
| `GATEWAY_SETTLEMENT_BACKLOG_LIMIT`              | yes      | none                              |
| `GATEWAY_BIND_ADDRESS`                          | no       | `127.0.0.1:3002`                  |
| `GATEWAY_GENERATION_TIMEOUT_SECONDS`            | no       | `630`                             |
| `GATEWAY_LEASE_FINALIZATION_MARGIN_SECONDS`     | no       | `60`                              |
| `GATEWAY_EXPIRED_LEASE_CLEANUP_GRACE_SECONDS`   | no       | `300`                             |
| `GATEWAY_ORGANIZATION_CONCURRENCY_CAP`          | no       | `500`                             |
| `GATEWAY_BALANCE_PER_CONCURRENCY_SLOT_NANO_USD` | no       | `1000000000`                      |
| `SGLANG_API_KEY`                                | no       | no upstream authentication        |
| `OPENROUTER_API_KEY`                            | no       | the `providers/openrouter` secret |
| `OPENROUTER_BASE_URL`                           | no       | `https://openrouter.ai/api/v1`    |

Valkey is always accessed with the cluster protocol. The local one-node
cluster owns all 16,384 slots and therefore exercises the same hash-tag and
`CROSSSLOT` behavior required by ElastiCache Serverless.

## OpenRouter capacity

With Gradiated's own OpenRouter key, the gateway serves a
catalog model whose `models.openrouter_model_id` is set through OpenRouter when
our deployments are absent, unhealthy, saturated or fail before output. Callers
need no OpenRouter key, are billed at catalog prices and see no OpenRouter
identity. The rules are in [ARCHITECTURE.md](ARCHITECTURE.md#external-capacity-openrouter).
`OPENROUTER_BASE_URL` accepts HTTPS, or HTTP on a loopback host for tests.
Every OpenRouter request requires zero data retention and no data collection,
and caps the provider price at the model's own catalog price (Kimi K3.1 Pro
alone accepts up to 120% of it); if OpenRouter
cannot serve, the caller gets our own capacity's answer.

The gateway uses `OPENROUTER_API_KEY` when it is set, as local runs and tests do.
Otherwise it reads the active slot of `gradiated/prod/providers/openrouter`
through the shared [credential loader](../../packages/credentials/README.md) on
each OpenRouter attempt, cached for five minutes, so changing `activeSlot`
rotates the key without a restart. A key that cannot be loaded fails that
attempt as `runtime_unavailable` and is logged as
`openrouter_credential_unavailable`; it never stops the gateway. A model uses
OpenRouter only when its catalog row maps it, so the mapping and the model's
status are the switch.

Mappings live in the git-owned catalog definitions under
`packages/control/src/catalog/models/`. Map only an OpenRouter entry for the same
weights: check its `hugging_face_id` in `GET https://openrouter.ai/api/v1/models`.
Verified on 2026-11-05: `z-ai/glm-5.3-flash` and `deepseek/deepseek-v4.1-flash`.
OpenRouter has no Dealign uncensored GLM and no SystemOne model; those stay
unmapped, and standard GLM must never stand in for the uncensored one.

To activate in an environment:

1. In OpenRouter, create a key for the gateway, allow only the providers that may
   serve Gradiated traffic and set its credit limit. Keep zero data retention
   enforced for the account.
2. Write two distinct keys to `gradiated/prod/providers/openrouter` as
   `{"activeSlot": "primary", "primaryApiKey": …, "secondaryApiKey": …}`.
3. Apply the `registry-secrets` and `platform-iam` units. They adopt that secret
   and let only the gateway's role read it.
4. Roll out the gateway, then mark a mapped model `available` in its catalog
   definition. It serves immediately, with or without deployments.

OpenRouter has no signed DPA with Gradiated; the Security Officer accepted that
as exception E-04 in `docs/security/risk-register.md`.

To rotate, write the new key to the inactive slot, test it, then switch
`activeSlot`; revoke the old key after five minutes.

Watch `gradiated_gateway_capacity_fallbacks_total`,
`gradiated_gateway_upstream_cost_nano_usd_total` against
`gradiated_gateway_calculated_charge_nano_usd_total{deployment="openrouter"}`,
and generations whose terminal log has `capacity="openrouter"`.

## Verify

```sh
mise exec -- cargo fmt --check
mise exec -- cargo clippy --locked --all-targets -- -D warnings
mise exec -- cargo test --locked
docker compose -f ../../docker-compose.yml up -d
mise exec -- cargo test --locked serving_state::tests -- --ignored
```

CI runs the ignored `serving_state` and `postgres_reader` suites against the complete product
Docker Compose dependency stack. It waits for the one-node Valkey cluster to
own all 16,384 slots before executing the tests.

The PostgreSQL reader suite executes every query against the migrated schema and
checks returned records, deployment discovery, ledger paging/seed behavior and
adapter selectors. Adapter cases cover exact/production names, workspace isolation,
ambiguous names, missing/cross-task pointers, legacy metadata and inactive ownership.
`GATEWAY_TEST_DATABASE_URL` can select a disposable database for the direct reader
tests; otherwise they use the local Compose database.
