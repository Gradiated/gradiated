# Gateway deployment routing plan

- Status: proposed
- Date: 2026-08-27
- Scope: exact-model routing, deployment status, concurrency, cache locality, and one retry

## Decision

The Rust gateway selects one runtime deployment for each request.

Provider infrastructure only runs and exposes runtimes. It does not balance or
retry requests.

Desmond sends two separate data flows:

- deployment status goes to Valkey through a small status endpoint;
- profiling metrics go to ClickHouse through the existing profiling endpoint.

The gateway uses:

- fresh deployment status;
- rendezvous hashing for stable routing;
- engine-owned admission with one retry;
- one retry before output starts.

The first version does not store affinity records. It does not reserve KV tokens.

## Service tiers

Each exact deployment supports `flex`, `default`, and `fast`. The tiers use one
shared deployment pool. Do not store tier availability on a deployment.

The request can set `service_tier`. The gateway uses `default` when the field is
absent. It maps the tiers to runtime priority as follows:

| Tier      | Runtime priority | Default-price ratio |
| --------- | ---------------- | ------------------- |
| `fast`    | `-10`            | `3 / 2`             |
| `default` | `0`              | `1 / 1`             |
| `flex`    | `10`             | `7 / 10`            |

The runtime schedules lower priority values first. Cache-affinity selection
cannot move a lower tier ahead of a higher tier. The gateway rejects a client
`priority` field and an `x-vllm-priority` header.

The gateway applies the price ratio to each nano-USD unit price and rounds down.
It captures these effective prices before admission. Retries keep the same
tier and price snapshot. Version 2 generation events store `service_tier`.
Version 1 events mean `default`. Successful responses include
`x-gradiated-service-tier`.

## Request flow

```text
authenticate
  -> load model and deployment status
  -> validate and tokenize
  -> build route key
  -> order deployments
  -> call runtime
  -> retry once if allowed
  -> settle once
```

Return:

- `429` when the engine rejects for capacity, or no deployment is accepting;
- `503` when no healthy deployment exists.

The engine rejects excess load with HTTP 503. The gateway maps 503 and 429 to
`capacity_exceeded` and returns 429 to the client.

Do not queue in the gateway.

## Durable deployment data

PostgreSQL remains the source of durable deployment data. Keep its existing
Valkey projection at `model:<model-id>`.

Add these fields to each deployment:

```json
{
  "provider": "runpod",
  "region": "sg",
  "fault_domain": "runpod:pod-123"
}
```

`fault_domain` identifies deployments that can fail together. A retry prefers a
different fault domain.

All deployments in one route set must use the same model, tokenizer, and runtime
release. A retry must not change the release.

## Deployment status

### Status endpoint

Add an authenticated `POST /v1/deployment-status` endpoint. Desmond calls it
every second.

Do not send status through ClickHouse. A ClickHouse failure must not affect
routing.

Use one credential for each provider. The endpoint checks that the provider owns
the deployment ID in the request. Desmond does not receive Valkey credentials.

### Status value

Store one Valkey hash for each exact release:

```text
deployment-status:{<served-release-digest>}
```

Each field name is a deployment ID. Each field value is:

```json
{
  "schema_version": 1,
  "deployment_id": "0198c36f-9b6a-7000-8000-000000000001",
  "runtime_revision": "vllm-revision",
  "received_at": "2026-08-27T12:00:00Z",
  "healthy": true,
  "accepting_requests": false,
  "reason_code": "kv_pressure"
}
```

The API sets `received_at` from its own clock. Desmond sends only its latest
state. It does not replay old status records.

Initial timing:

- Desmond interval: 1 second;
- maximum status age: 15 seconds;
- Valkey hash TTL: 30 seconds;
- gateway cache TTL: 1 second;
- future-dated tolerance: 5 seconds.

The gateway ignores stale, unknown, or mismatched fields.

### Status meaning

`healthy` means the runtime and GPU can serve requests.

Set `healthy: false` for conditions such as:

- runtime failure;
- GPU failure;
- failed health checks.

`accepting_requests` means the runtime can accept a new request now.

Set `accepting_requests: false` for these reasons:

- `runtime_unavailable`: the runtime is not ready or the child process stopped;
- `draining`: the deployment is shutting down;
- `metrics_unavailable`: the runtime metrics could not be read;
- `kv_pressure`: KV cache usage is at or above the limit.

Existing requests continue when `accepting_requests` becomes false.

Desmond owns these decisions. The gateway does not score raw GPU or runtime
metrics. Keep the detailed metrics in ClickHouse.

Use `reason_code` for logs, metrics, and the `429` or `503` decision. Do not send
provider details to the client.

`accepting_requests` reports runtime safety. It is not a concurrency limit.

## Simple gateway cache

Use one small lazy TTL cache implementation.

```text
if value exists and age < TTL:
    return value
else:
    load from Valkey
    replace value
    return value
```

Use it for:

- `GatewayModel`;
- the release status hash;
- the `/v1/models` catalog view.

Use a one-second TTL first. The first request after expiry loads the value.
Concurrent requests for the same key share that load. If the load fails, fail
closed.

Do not add:

- a refresh loop;
- soft and hard TTLs;
- stale-while-revalidate;
- negative caching;
- a local affinity cache.

Always use Valkey for:

- credentials and revocation;
- workspace and organization status;
- balances;
- organization admission leases;
- settlement.

The gateway keeps no per-deployment concurrency state in Valkey.

The tokenizer already lazy-loads and caches exact tokenizer releases. Keep that
code.

## Rendezvous routing

Build one stable route key.

Use an explicit session when present:

```text
SHA-256(workspace ID || model ID || release digest || session ID)
```

Without a session, hash the release and up to 4,096 rendered token IDs from the
opening messages. This gives stable routing for a conversation and for long
shared prompts. Do not store the messages or token IDs.

For each eligible deployment, calculate:

```text
score = SHA-256(route key || deployment ID)
```

Order deployments by score. Use the highest score first.

This gives:

- the same order in every gateway;
- stable routing without affinity records;
- limited movement when deployments are added or removed;
- a ready retry order.

If the first deployment cannot reserve a slot, try the next deployment. Bound
the number of reservation attempts. Start with three.

## Session input

Accept:

- the top-level request field `session_id`;
- the header `x-gradiated-session-id`;
- confirmed trusted aliases from distribution channels.

The body field wins. Limit it to 256 characters. Hash it before use. Do not log,
store, or forward the raw value.

OpenRouter may not forward a session value. The opening-message route key is the
fallback.

## Deployment concurrency

The gateway does not track deployment concurrency. The engine owns admission.

Route by rendezvous ranking. Dispatch to the highest-ranked deployment. When
that deployment is full, the runtime rejects the request and the gateway retries
once on the next candidate. No reservation is taken before dispatch.

Removed: the `deployment-inflight:{<deployment-id>}` sorted set and its Lua
scripts. The gateway no longer reserves a slot per generation.

Reason for removal:

- The engine already bounds admission atomically through `max_num_queued_reqs`
  and `max_num_queued_tokens`, counted in the API server across all ranks.
- The status document that fed the limit is sampled once per second. Two
  gateway replicas can read the same sample and dispatch together. A lease is
  needed only when the signal is a stale boolean.
- The lease outlived the request. Its reservation used the generation timeout
  plus a finalization margin, so a slot stayed reserved after the stream closed.
  That produced phantom slots and admission flapping.

The organization lease still controls billing and organization concurrency. It
is a separate limit and it stays.

### Required runtime flags

The launch scripts always pass `--max-num-queued-reqs` and
`--max-num-queued-tokens`. Both flags exist from vLLM v0.29.0.

vLLM queues without a bound when `max_num_queued_reqs` is unset. The engine then
accepts load past its batch capacity and preempts KV instead of rejecting.
Preemption collapses time to first token for every request on the deployment.
The runtime build must support both flags. A runtime that does not support them
fails at startup instead of running without a bound.

### Why no KV lease at launch

Most expected requests are long. Desmond marks a deployment as not accepting
requests when KV pressure becomes unsafe. vLLM remains the final authority.

Do not gate admission on `vllm:num_requests_running`. That counter is a proxy for
the engine batch state, not a capacity limit. It changes with prompt length and
KV budget, so a fixed threshold rejects work that the engine can accept.

Set the engine queue limits instead:

- `--max-num-queued-reqs` bounds waiting plus running requests.
- `--max-num-queued-tokens` bounds the prefill token backlog.
  Set it to `target_TTFT * prefill_throughput`.

vLLM rejects a request with HTTP 503 when either limit is reached. The gateway
maps 503 and 429 to `capacity_exceeded`, so the client can retry. A 503 never
maps to `runtime_unavailable`.

Size the two limits for the deployment:

- `max_num_queued_reqs`: `data_parallel_size * max_num_seqs + queue_depth`.
  The DeepSeek runtime uses `max_num_seqs=32`, so 64 leaves a small queue.
- `max_num_queued_tokens`: `target_TTFT * prefill_throughput`.
  A value below one full-context prompt sheds work the engine could accept.

The status document declares no concurrency value. The gateway does not publish
a capacity limit and does not gate admission on one. Readiness requires one
fresh healthy deployment status.

## One retry

Retry once only when:

- attempt 1 failed with `unavailable` or `capacity_exceeded`;
- no output reached the client;
- the client is connected;
- time remains;
- another deployment serves the same release.

Exclude the first deployment.

Prefer another fault domain. For connection or runtime failure, prefer another
provider.

Do not retry:

- invalid requests;
- protocol errors;
- timeouts;
- a stream that already started.

The two attempts share one generation ID, deadline, price, organization lease,
and settlement.

## OpenRouter capacity

The catalog omits the `capacity` array. OpenRouter treats an absent array as an
undeclared limit, not zero. A declared concurrency value would be wrong because
safe concurrency depends on prompt length, and the gateway does not enforce a
limit.

A model is ready when at least one fresh healthy deployment reports status.
Running requests do not change readiness. Temporary saturation returns `429`.
OpenRouter does not count `429` against uptime, and it prefers an early `429`
over a queued request.

Use OpenRouter `is_ready` for launch control and sustained outages. Do not change
it because the fleet is busy.

Do not report token throughput until measurements exist.

## Implementation plan

### 1. Contracts

- Add `provider`, `region`, and `fault_domain` to deployments.
- Add the status request and Valkey value contracts.
- Add `session_id` as a gateway-owned request field.

### 2. Desmond and status ingestion

- Add the latest-state status sender to Desmond.
- Add provider-scoped authentication.
- Write accepted status directly to Valkey.
- Keep the profiling path unchanged.

### 3. Gateway cache and routing

- Add the simple lazy TTL cache with single-flight loading.
- Cache model and status data for one second.
- Add the session normalizer.
- Add rendezvous ordering.

### 4. Retry and reporting

- Add one sequential retry.
- Keep one customer generation and settlement.
- Report healthy installed concurrency to OpenRouter.

### 5. Measure and roll out

- Measure one TP2 runtime first.
- Measure both TP2 runtimes together.
- Set the engine queue limits, `max_num_queued_reqs` and `max_num_queued_tokens`.
- Test status loss, saturation, cancellation, retry, and streaming.
- Enable the new route only for GLM-5.3-Flash first.

## Launch gates

- Stale status removes a deployment within 15 seconds.
- Busy healthy deployments return `429`.
- Unhealthy fleets return `503`.
- The engine rejects excess load; the gateway holds no concurrency state.
- One request makes at most two runtime attempts.
- A retry never changes the model release.
- A started stream is never retried.
- One customer request settles once.
- A 1,000-deployment status hash is not loaded for every request.
- No prompt, completion, token list, or raw session ID enters Valkey or logs.

## Deferred work

- KV-token or weighted admission limits;
- stored affinity records;
- runtime-instance cache epochs;
- latency, price, or throughput scoring;
- gateway queues;
- more than one retry;
- hedged requests;
- provider-local schedulers;
- background cache refresh;
- Pub/Sub or a routing change feed;
- token-throughput capacity reporting.

## Known limits

The status view can be up to 15 seconds old. The engine bounds admission, so a
stale healthy view can send work to a full deployment; the engine rejects it and
one retry handles it. A stale view also keeps a stopped runtime in rotation for
up to 15 seconds.

The gateway request limit is 32 MB. Test it with the largest supported JSON
request before advertising the full context window.

OpenRouter session forwarding is not confirmed. Test the field names that reach
the provider. Do not capture session values.

## Verification

```sh
cd product
pnpm --filter @gradiated/contracts check
pnpm --filter @gradiated/control check
pnpm --filter @gradiated/gateway check
python3 ../tools/devex/check.py
```
