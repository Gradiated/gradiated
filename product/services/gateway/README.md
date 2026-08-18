# Gateway

The Rust inference data plane authenticates and admits direct and OpenRouter
requests through Valkey, calls one exact SGLang deployment per model, and
settles terminal usage. Its implementation authority is
[ARCHITECTURE.md](ARCHITECTURE.md).

## Current slice

The runnable service currently provides:

- strict Valkey-projected model and deployment records;
- an immutable served-release digest;
- an always cluster-aware Valkey connection;
- dependency-aware liveness and readiness routes;
- an 8 MB request-body ceiling;
- structured JSON startup logging and graceful shutdown.

Chat Completions, bearer authentication, admission, SGLang dispatch and
settlement are the next implementation slices. No fake inference endpoint is
used.

## Run locally

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
VALKEY_URL=redis://127.0.0.1:6379 mise exec -- cargo run --locked
```

The local endpoints are:

- `http://127.0.0.1:3002/health/live`
- `http://127.0.0.1:3002/health/ready`

## Configuration

| Variable                             | Required | Default                    |
| ------------------------------------ | -------- | -------------------------- |
| `VALKEY_URL`                         | yes      | none                       |
| `GATEWAY_BIND_ADDRESS`               | no       | `127.0.0.1:3002`           |
| `GATEWAY_GENERATION_TIMEOUT_SECONDS` | no       | `300`                      |
| `SGLANG_API_KEY`                     | no       | no upstream authentication |

Valkey is always accessed with the cluster protocol. The local one-node
cluster owns all 16,384 slots and therefore exercises the same hash-tag and
`CROSSSLOT` behavior required by ElastiCache Serverless.

## Verify

```sh
mise exec -- cargo fmt --check
mise exec -- cargo clippy --locked --all-targets -- -D warnings
mise exec -- cargo test --locked
mise exec -- cargo test --locked local_cluster_enforces_settlement_hash_tag -- --ignored
```
