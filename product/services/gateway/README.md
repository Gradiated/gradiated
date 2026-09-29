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

The gateway selects an exact served release, then ranks its healthy, accepting
deployments by rendezvous hash. Session affinity takes precedence; otherwise
routing uses the opening prompt. Keys include workspace, model, and release
identity. Routing stores no affinity records or per-deployment concurrency leases.

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

| Variable                                        | Required | Default                    |
| ----------------------------------------------- | -------- | -------------------------- |
| `VALKEY_URL`                                    | yes      | none                       |
| `GATEWAY_SETTLEMENT_BACKLOG_LIMIT`              | yes      | none                       |
| `GATEWAY_BIND_ADDRESS`                          | no       | `127.0.0.1:3002`           |
| `GATEWAY_GENERATION_TIMEOUT_SECONDS`            | no       | `630`                      |
| `GATEWAY_LEASE_FINALIZATION_MARGIN_SECONDS`     | no       | `60`                       |
| `GATEWAY_EXPIRED_LEASE_CLEANUP_GRACE_SECONDS`   | no       | `300`                      |
| `GATEWAY_ORGANIZATION_CONCURRENCY_CAP`          | no       | `50`                       |
| `GATEWAY_BALANCE_PER_CONCURRENCY_SLOT_NANO_USD` | no       | `1000000000`               |
| `SGLANG_API_KEY`                                | no       | no upstream authentication |

Valkey is always accessed with the cluster protocol. The local one-node
cluster owns all 16,384 slots and therefore exercises the same hash-tag and
`CROSSSLOT` behavior required by ElastiCache Serverless.

## Verify

```sh
mise exec -- cargo fmt --check
mise exec -- cargo clippy --locked --all-targets -- -D warnings
mise exec -- cargo test --locked
docker compose -f ../../docker-compose.yml up -d
mise exec -- cargo test --locked serving_state::tests -- --ignored
```

CI runs the same ignored `serving_state` suite against the complete product
Docker Compose dependency stack. It waits for the one-node Valkey cluster to
own all 16,384 slots before executing the tests.
