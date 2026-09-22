# Gateway

The Rust inference data plane authenticates and admits direct and OpenRouter
requests through Valkey, calls a deployment of the exact requested model, and
settles terminal usage. Its implementation authority is
[ARCHITECTURE.md](ARCHITECTURE.md).

## Current slice

The runnable service currently provides:

- strict Valkey-projected model and deployment records;
- an immutable served-release digest;
- an always cluster-aware Valkey connection;
- dependency-aware liveness and readiness routes;
- an 8 MB request-body ceiling;
- structured JSON startup logging and graceful shutdown;
- one atomic Valkey admission script with funded prepaid concurrency,
  uncapped invoiced admission, settlement-backlog protection, and fixed leases;
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
| `GATEWAY_GENERATION_TIMEOUT_SECONDS`            | no       | `300`                      |
| `GATEWAY_LEASE_FINALIZATION_MARGIN_SECONDS`     | no       | `60`                       |
| `GATEWAY_EXPIRED_LEASE_CLEANUP_GRACE_SECONDS`   | no       | `300`                      |
| `GATEWAY_PREPAID_ORGANIZATION_CONCURRENCY_CAP`  | no       | `50`                       |
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
