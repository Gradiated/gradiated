# Gateway integration tests

These tests run the real gateway binary against disposable dependencies. The
default suite uses only the CPU, without model downloads, cloud credentials or
production endpoints, except the opt-in live OpenRouter tests. An explicit SGLang option connects to a resident runtime
through a loopback forward; it does not allocate or launch a GPU runtime.

```text
HTTP client or official SDK
        |
        v
real gateway binary ----> loopback Kev or vLLM mock runtime
   |          |
   v          v
PostgreSQL   Valkey cluster
(tenants,    (admission, operational balance,
 catalog)     record cache, settlement stream)
```

## What the suite runs

- The gateway binary from `target/debug`. The test process gives it an explicit
  environment, so no ambient cloud or runtime credential reaches it.
- One PostgreSQL container. Global setup applies the product migrations, so the
  schema is the same one that the gateway queries.
- One Valkey container as a one-node cluster that holds all slots.
- Mock Kev and vLLM runtimes as HTTP servers on loopback ports. Each case starts
  its own runtimes.

Each container has a random port, tmpfs storage and a `gateway-contract` label
with the run's owner name. Teardown removes only the containers whose label
matches. If a run is killed, a container named `gateway-contract-*` can stay.
Examine its label before you remove it.

Process tests also run two gateways against the same tenant to check their shared
admission cap and recovery of leases abandoned by a crashed process.

The shared gateway has a three-second generation deadline, a concurrency cap
of two for each organization and a one-second record cache.
`gateway-process.ts` exports these settings. Tests derive their limits from
these constants.

## Layout

| Path                  | Contents                                                              |
| --------------------- | --------------------------------------------------------------------- |
| `global-setup.ts`     | Starts the stack, provides its URLs and tears it down.                |
| `stack/`              | Local Docker client, PostgreSQL, Valkey and the real CPU runtimes.    |
| `gateway-process.ts`  | Starts, waits for and stops one gateway process, and its settings.    |
| `case.ts`             | The `Case` fixture and `useCases`.                                    |
| `catalog.ts`          | The model, release and deployment records that a case publishes.      |
| `assertions.ts`       | Public error and propagation assertions.                              |
| `admission.ts`        | Gated requests that hold admission slots.                             |
| `chat.ts`             | The official chat client and checked stream chunks.                   |
| `typesafe.ts`         | The official TypeSafe SDK client and its error assertions.            |
| `mock-runtimes/`      | The Kev, vLLM and OpenRouter wire profiles and the fault server.      |
| `adapter-versions.ts` | Private adapter versions and LoRA-enabled deployments for a case.     |
| `http-client.ts`      | A raw HTTP client for repeated headers, large bodies and cut streams. |
| `eventually.ts`       | Polling and timeouts.                                                 |
| `json.ts`, `ports.ts` | JSON guards and loopback port probes.                                 |
| `*.test.ts`           | One file for each gateway behavior area.                              |

`sdk-pricing.test.ts` uses the official OpenAI and Anthropic TypeScript SDKs to
read pricing from Chat Completions, Responses, and Messages. It checks buffered
responses, raw terminal stream events, and SDK stream helpers against the durable
settled charge, including cached input, service tiers, free models, cache writes,
and reasoning. Anthropic's final-message helper drops extension fields; its
`streamEvent` callback is the tested path for reading cost.

`typesafe-sdk.test.ts` uses the official TypeSafe SDK (`@typesafe-ai/sdk`, the
version pinned in `package.json`) against `/v1/systemone`. It covers every
question type and its typed answer, usage and settled charge, the question and
option bounds, state shapes, the SDK's error classes for gateway and runtime
failures, its retry policy (each attempt is a generation, and only the answer is
billed), timeouts and aborts settled as client cancellations, protocol mismatch
and deployment pinning. The SDK cannot send list-form choice criteria, so those
tests use raw HTTP and check that the runtime receives the object form. Tests
named `known gap` pin a current incompatibility and say what should replace
them. `proxy/test/e2e/sdk/typesafe.test.ts` runs the SDK through the proxy.

## OpenRouter capacity

`openrouter-capacity.test.ts` starts its own gateway with `OPENROUTER_API_KEY`
and `OPENROUTER_BASE_URL` pointed at a loopback OpenRouter mock, so each case
controls OpenRouter in the test process. `mock-runtimes/openrouter.ts` reproduces
the measured OpenRouter wire shape: `gen-` IDs, provider names, `cost`,
`reasoning_details`, a usage frame that repeats the finish reason, reasoning
counts above completion counts and SSE keepalive comments. The mock rejects a
request without privacy routing, opaque `user` and `session_id` values or the
platform key. A case maps its model with `openRouterModel` and can have no
deployments with `replicas: 0`.

The file covers serving with no deployments, unhealthy and saturated capacity,
local success, pre-output failure in both modes, both capacities failing, the
shared deadline, partial-stream failure, cancellation, Messages, Responses and
the official SDKs, catalog-priced billing against a higher upstream cost,
balance, status, pins, OpenRouter's own and other channel traffic, listing and
adapter degradation.
Every assertion also checks that no OpenRouter detail reaches the caller.

`openrouter-live.test.ts` runs a few of these cases against the live API with
`meta-llama/llama-3.1-8b-instruct`, which has several ZDR providers and costs
about $0.00001 a request. It runs only when `OPENROUTER_LIVE_API_KEY` is set:

```sh
OPENROUTER_LIVE_API_KEY=... pnpm --filter @gradiated/gateway exec vitest run \
  test/integration/openrouter-live.test.ts
```

CI sets it from the `OPENROUTER_CI_API_KEY` Actions secret and fails without it,
except on fork and Dependabot runs, which get no secrets. Locally, the
`OPENROUTER_API_KEY` in `gradiated/dev/env` works.

## Run the suite

Run the commands from `product/`. You must have Docker, Cargo and pnpm.

```sh
pnpm --filter @gradiated/gateway test:integration
pnpm --filter @gradiated/gateway exec vitest run streaming
```

`test:integration` builds the gateway binary first. The second command does not
build the binary. A missing binary or Docker daemon fails the run. It does not
skip tests.

Docker must use a local unix socket. The suite refuses a remote Docker endpoint.

## Gateway logs

Each gateway process writes its log to
`<repository>/.agents/runtime/gateway-integration/`. Global setup clears this
directory at the start of a run. Teardown keeps it and prints its path.

## Write a case

`useCases()` gives a test file a `makeCase` function and checks each case after
each test. A case has its own organization, workspace, key, model, release and
runtimes. Thus test files can run in parallel.

```ts
const { makeCase } = useCases();

const instance = await makeCase("vllm");
const replicated = await makeCase("kev", { replicas: 2 });
```

The gateway reads tenants and models from PostgreSQL and caches them in Valkey.
Tests change rows, not the cache.

| Function                                       | Use                                                                       |
| ---------------------------------------------- | ------------------------------------------------------------------------- |
| `post(changes)`                                | Sends the default body for the case, with changes.                        |
| `setTenant(changes)`                           | Writes tenant rows and clears the cache, so the next request sees them.   |
| `writeTenantRows(changes)`                     | Writes tenant rows only. Use it to test cache expiry.                     |
| `setCredential(changes)`, `writeCredentialRow` | The same pair for the API key row.                                        |
| `recordBalanceTransaction(entry)`              | Adds a ledger entry.                                                      |
| `publish()`, `status(overrides)`               | Writes the model rows and the deployment status.                          |
| `settled(response, { status, charge })`        | Waits for one settlement and checks it.                                   |
| `ready(matches?)`                              | Waits until this model is ready in the authenticated gateway catalog.     |
| `expectNotDispatched()`                        | Checks that no runtime call and no settlement occurred.                   |
| `expectRejected(response, { code, param })`    | Checks the status, type and code of a public error and its generation ID. |
| `fillConcurrencyCap(instance)`                 | Holds requests open in the runtime until the organization cap is full.    |

After each test, the fixture checks that the mocks recorded no contract error,
that no admission lease stays, that each generation settled once and that the
balance equals the start balance less the charges.

Real runtime cases can share the same pinned release. Deployment-status reads
are cached by release digest for one second, so publishing a new deployment does
not make it visible to the next request immediately. Real cases call `ready()`
through the gateway's catalog before inference. The native burst refreshes all
ten organizations' deployment statuses together after setup, then checks
readiness again so the earliest status has not become stale while setup waits.

### Runtime faults

`runtime.enqueue(options)` sets the result of the next request to that runtime.
The options are `status`, `fault`, `mutateBody`, `mutateEvents`, `cached`,
`fragment`, `errorUsage` and `gate`. A `gate` holds the request open until the
test releases it. If the request does not use an option, the mock records a
contract error. For example, a `stall` fault on a request that does not stream
fails the test. Test controls stay in the test process. They never use request
headers or an admin endpoint.

`runtime.calls` records each request that the gateway sent. Use it to check
what the gateway put on the wire.

## Real runtimes

`real-runtime.test.ts` runs the gateway against a real SGLang server and a real
Kev server on the CPU. The SGLang server is upstream's CPU release, while
production runs GPU SGLang bundles. Its cases use the `vllm` mock profile's
deployment, which is the gateway's single OpenAI-compatible runtime wire. These
tests find differences between the mocks and the real runtimes. They check wire
shape and that billing uses the token counts from the runtime. They do not check
exact token counts.

```sh
GATEWAY_REAL_RUNTIME=sglang-cpu,kev pnpm --filter @gradiated/gateway test:integration
```

`GATEWAY_REAL_RUNTIME` names the runtimes to start. The tests for a runtime
that is not named are skipped. The images are built from
`product/inference/runtimes/sglang-cpu/Dockerfile` and
`product/inference/runtimes/kev/Dockerfile.cpu` with the weights included. To use
a server that already runs, set `GATEWAY_REAL_RUNTIME_URL_SGLANG_CPU` or
`GATEWAY_REAL_RUNTIME_URL_KEV`. The SGLang CPU image is amd64 only. On Apple
Silicon, use the URL variable or let CI run these tests.

When a real runtime is enabled, global setup also starts a second gateway with a
120-second deadline for real CPU inference.

### Resident SGLang and SMG

Point the loopback URL at the ordinary OpenAI API exposed by the resident
SGLang/SMG frontend, rather than the native `/generate` backend. The suite starts
its own PostgreSQL, Valkey and local gateway, with synthetic tenants and balances.
It never connects the gateway to a production database or billing account.

```sh
pnpm --filter @gradiated/gateway build
GATEWAY_REAL_RUNTIME=sglang \
GATEWAY_REAL_RUNTIME_URL_SGLANG=http://127.0.0.1:32800 \
GATEWAY_REAL_SGLANG_MODEL=dealignai/GLM-5.3-Flash-UNCENSORED-NVFP4 \
GATEWAY_REAL_SGLANG_MODEL_REVISION=745aac2ff0f10acf961f396df3f9418598aa7327 \
GATEWAY_REAL_SGLANG_RUNTIME_REVISION=sglang-f1718592-smg-1.13.0 \
pnpm --filter @gradiated/gateway exec vitest run real-sglang
```

Use the model advertised by `/v1/models` and the actual runtime source identity
for the resident release. Model and tokenizer revisions use the checkpoint SHA;
`RUNTIME_REVISION` records the separate runtime identity, not an image claim.
If upstream authentication is enabled, provide `GATEWAY_REAL_SGLANG_API_KEY`
through the environment. The local proxy forwards it without replacing the
gateway's own test authentication token.

`real-sglang.test.ts` checks buffered chat, streamed reasoning and visible output,
fragmented tool arguments, authoritative usage and local settlement, prefix-cache
reuse with more than 1,024 input tokens, and cancellation of the upstream HTTP
connection. Requests run sequentially. The overload case injects admission
rejections at the observing proxy to verify bounded gateway failover; it does not
claim that the GPU runtime's queue was saturated.

The real fallback case uses two observing proxy deployments and one resident
frontend: it pins a primary, injects that primary's HTTP 503, and observes the
backup complete against SGLang. It checks call order, authoritative usage and one
settlement for the retried generation. The large-fixture option also runs a
joined cold-long/short mix, with the short request arriving after two seconds,
and prints generated and visible TTFT without imposing a prefill-speed target.

`sglang-contract.test.ts` runs without a GPU. It exercises SGLang-shaped reasoning,
nullable tool deltas and running usage, including its first-event HTTP-200/SSE-503
queue rejection. Immediate admission failures can become an HTTP 429 after the
bounded backup attempt. After a one-second startup grace, the gateway exposes
headers and its existing 15-second keepalives even if the runtime withholds HTTP
headers throughout prefill. A later zero-usage first-event capacity failure can
still use the remaining backup attempt, but cannot change the committed HTTP
status; exhausted capacity then becomes an SSE error. Any delivered data frame,
including a role-only frame, prevents replay. Both paths share a two-attempt cap.
`sglang-proxy.test.ts` verifies upstream HTTP 429, socket cancellation and delayed
upstream headers through an actual keepalive interval.

Optional public synthetic long-context fixtures stay outside version control:

```sh
GATEWAY_REAL_SGLANG_LONG_FIXTURE=/absolute/ignored/cold-500k.json
GATEWAY_REAL_SGLANG_CANCEL_FIXTURE=/absolute/ignored/cold-128k.json
GATEWAY_REAL_SGLANG_METRICS_URL=http://127.0.0.1:32803/metrics
```

Set these alongside the previous environment when running `real-sglang`. Each
fixture is one JSON object with `messages: [{role: "user", content: "..."}]` and
`marker: "tamarind"`, exported from a public synthetic fixture. The suite adds a
fresh leading UUID and publishes a one-million-token context limit only in its
disposable catalog. The large case requires public headers within five seconds,
observes keepalives while waiting for output, checks zero cached tokens and the
exact answer, and prints timings and token counts without the prompt. It does not
require a minimum prefill time when the GPU is faster than a keepalive interval.

The cancellation fixture must keep upstream headers pending after public headers
arrive. The test cancels there and checks local settlement and upstream connection
abort. When the optional metrics forward is supplied, it also requires a present
native `sglang:num_running_reqs` gauge to return to zero within ten seconds;
missing metrics are an error, not evidence of zero active work.

For a bounded native SMG admission burst, additionally set
`GATEWAY_REAL_SGLANG_OVERLOAD=1`. The opt-in test sends 19 streamed, cold synthetic
requests through the local gateway across ten disposable organizations, with at
most two per organization. Each request has a few thousand input tokens and a
256-token output cap with normal EOS. Every started request is joined; a slow
request is not cancelled to improve the result. The test has a 180-second limit.

`GATEWAY_REAL_SMG_METRICS_URL=http://127.0.0.1:26805/metrics` enables sampling of
the frontend's native `smg_admission_inflight` and `smg_admission_queue_depth`
gauges during the burst. Their observed maxima must stay within 16 and 2. The
test prints HTTP status counts and simultaneous measured peaks. If a simultaneous
16+2 peak is observed, at least one public HTTP 429 must be observed too. It does
not demand exactly one rejection when requests finish before the whole burst
arrives, or claim saturation from missing samples. Successful streams must end
normally with consistent usage and settlement; HTTP 5xx and stream failures fail
the test. The metrics URL is separate from the optional engine/warmup metrics URL.
SMG creates the queue gauge on the first enqueue. Before that, partial samples
record queue depth as unknown, rather than zero. A real queue rejection requires
an observed queue gauge; an unexercised queue is not claimed to be saturated.

## Mock fidelity

- `mock-runtimes/kev.ts` and `vllm.ts` are separate synthetic wire profiles.
  They do not import gateway code.
- The vLLM profile builds its responses as the OpenAI client types, so `tsc`
  checks their shape.
- The official OpenAI and TypeSafe clients decode gateway responses in some
  tests.
- Expected charges are fixed numbers. The tests do not call gateway pricing
  code.
- When a runtime image changes, run the real-runtime tests. Add a synthetic
  test for each incompatibility that you find.

## What a green run does not prove

A default CPU run does not test production registration, health publishing, TLS,
ingress, IAM, settlement workers, Valkey failover,
kernel correctness, tokenizer templates, long contexts or sustained load. The
Rust unit tests and the ignored Valkey tests are also necessary. A green run
does not certify an SGLang version or GPU type.

## Session diagnostics

`session-telemetry.test.ts` starts an info-level gateway and checks its actual
terminal JSON logs, correlated by the public generation ID. It exercises the
OpenAI and Anthropic SDKs, captured OpenCode/Codex header shapes, body/header
routing precedence, stable identifier hashes across turns, and exclusion of
unrelated metadata. The other gateways retain their default warning log level.

Loopback-only wire captures with synthetic inputs established these client
conventions (these are measured versions, not a cross-provider standard):

- OpenAI JS 7.5.0: no session header by default; an explicit Responses
  `prompt_cache_key` is sent in the JSON body.
- Anthropic JS 0.131.0: no session header by default; caller-supplied
  `metadata.user_id` is sent in the body.
- OpenCode SDK/server 1.19.5, using `@ai-sdk/openai-compatible`: two prompts in
  one SDK session sent the same `x-opencode-session-id`, `x-session-affinity`,
  and `x-session-id` to the model endpoint. The SDK's own session URL is an
  OpenCode control-plane identifier; inspecting that URL alone does not prove
  which headers the model endpoint receives.
- Claude Code 2.1.299 (`--bare`): `x-claude-code-session-id` and JSON-encoded
  `metadata.user_id.session_id` matched.
- Codex CLI 0.166.0: `session-id`, `thread-id`, `x-client-request-id`, the
  session/thread members of `x-codex-turn-metadata`, and body
  `prompt_cache_key`/`client_metadata` identify the session. Window IDs have
  their own hash. The rest of the metadata, including device IDs and workspace
  paths, is excluded.

`session-affinity.test.ts` verifies that each accepted SDK source chooses the
same replica and served release as an equivalent explicit `session_id`, across
Chat Completions, Responses and Messages. It uses four replicas split between
two runtime revisions, multiple sessions, and changing prompt suffixes. Rust
tests check every source pair's precedence, malformed keys, bounded parsing,
and exclusion of request/window IDs. Existing routing tests cover workspace,
model and release scoping, health, retries and content-based distribution.

The resolver selects a key once before translation and reuses it for release
and replica selection. `effective_session_source` records the selected source,
`content_messages` or `content_prefix_8192` for sessionless chat affinity,
or `state_prefix` for sessionless SystemOne. A cache hit still requires the same
token prefix resident on the selected runtime; mock runtime tests establish routing behavior, not GPU
KV-cache speed or hit rate. No prompt or completion content is retained by the
wire-capture probes.

`content-affinity.test.ts` checks growing keyless conversations through Chat,
Messages and Responses across four replicas and two served revisions. It also
checks malformed optional metadata, explicit-key precedence over changed
content, the 8192-character fallback, and capacity failover. Distinct opening
questions still spread across the fleet, while repeated openings stay cache-local.
