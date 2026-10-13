# Isolated Kev gateway E2E

Prerequisites: Rust, Node and pnpm, Docker on a local unix socket, and two
running Kev gateway-protocol adapters, such as the two pods of the
Kev Kubernetes Rollout. The
separately maintained `product/scripts/test-kev-gateway.test.ts` must be present.
Remote Docker contexts are refused; the launcher resolves this host's own socket.

Build the actual Rust gateway from the repository root:

```sh
cargo build --locked --manifest-path product/services/gateway/Cargo.toml \
  --bin gradiated-gateway
```

Set `KEV_SSH_HOST`, `KEV_SSH_PORT`, and `KEV_SSH_KEY` to the pod's current SSH
connection, and `KEV_PORT_0` and `KEV_PORT_1` to the two pods' loopback runtime
ports from the host agent's `/var/lib/gradiated-kubelet/pods/<Pod UID>/runtime.json`, then keep this tunnel running in a separate
terminal:

```sh
ssh -i "${KEV_SSH_KEY:?Set the authorized SSH key path}" \
  -p "${KEV_SSH_PORT:?Set the current pod SSH port}" \
  -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -L "127.0.0.1:18009:127.0.0.1:${KEV_PORT_0:?}" \
  -L "127.0.0.1:18010:127.0.0.1:${KEV_PORT_1:?}" \
  -N "root@${KEV_SSH_HOST:?Set the current pod SSH host}"
```

Both adapters warm their uncached and cached inference paths before opening the
HTTP listener. Wait for readiness, then run from the repository root:

```sh
KEV_GATEWAY_EXECUTABLE="$PWD/product/services/gateway/target/debug/gradiated-gateway" \
  pnpm --dir product e2e:kev
```

The launcher does not build Rust, deploy adapters, create tunnels, or register
anything in production. Complete the prerequisites above before invoking it.
Docker host networking is required. Dependencies come from the workspace lockfile:
`redis` and the official `@typesafe-ai/sdk`, matching the independently authored
SDK harness.

| Environment variable      | Default / purpose                                                                                                |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `KEV_RUNTIME_URLS`        | `http://127.0.0.1:18009,http://127.0.0.1:18010`; exactly two distinct plain HTTP loopback SSH forwards           |
| `KEV_GATEWAY_EXECUTABLE`  | Repository `product/services/gateway/target/debug/gradiated-gateway`; override for a different Cargo output path |
| `KEV_GATEWAY_PORT`        | `18080`; `0` selects an available port                                                                           |
| `KEV_E2E_TIMEOUT_SECONDS` | `900`; SDK suite deadline                                                                                        |

Ports 16379 and 26379 must be free for Valkey and its cluster bus. The launcher
creates a uniquely named `valkey/valkey:8.1.9-alpine3.24` container (matching the
repository Compose pin), bound to 127.0.0.1 with all 16,384 slots assigned through
`valkey-cli`. Its cluster configuration and data live in container tmpfs. Only
this empty disposable instance receives a model projection, two deployments,
workspace/account records, and a digest of a freshly generated random key.
There is no configurable external Redis URL and no flush operation.

The model is exactly `jaredpalmer/kev-9b`. Release metadata declares
`protocol: "system_one"`, runtime revision
`kev-f0ae8fb9-systemone-v1` (production derives it from the bundle digest), adapter revision
`2629c06a5aeb0feb3b9783bafed17ed8f39ecf5c`, and tokenizer
`Qwen/Qwen3.5-9B-Base@68c46c4b3498877f3ef123c856ecfde50c39f404`, as pinned in
`product/inference/gpu/runtimes.json`. Release JSON preserves the Rust
`ModelDeploymentRelease` field order and omits absent `runtime_model_name` and
`tokenizer_mode` before SHA-256 hashing. Local deployment status timestamps are
refreshed every second; these are synthetic availability declarations, not a
production health publisher. Real request success is verified by the suite.

Prices are **synthetic** nano-USD per token: 10 uncached input, 2 cached input,
0 output. The prepaid account starts with 1,000,000,000,000 nano-USD. The projection
uses a positive output-length metadata placeholder required by the model schema;
the native decision protocol must nevertheless settle zero generated output tokens.

## Harness contract and settlement checks

The vitest subprocess receives `KEV_GATEWAY_API_KEY` (generated, never printed),
`KEV_GATEWAY_BASE_URL` (`http://127.0.0.1:<port>` origin, without `/v1`), and
`KEV_GATEWAY_MODEL` (`jaredpalmer/kev-9b`). It also receives `KEV_RUNTIME_URLS`.
The harness must use these values for its TypeSafe clients and exercise a repeated
long prefix so at least one successful generation reports cached input tokens.
Ambient credentials, gateway settings, proxy configuration, and SDK defaults are
not inherited: the child receives an explicit environment. The harness enforces
its own per-test deadline through vitest's `testTimeout`.

The launcher runs vitest in a child process with a setup file
(`product/scripts/kev-e2e-ledger.ts`) that wraps the global `fetch`. Successful
POST responses at the local SystemOne endpoint record only `x-gradiated-generation-id` into
a temporary JSON-lines ledger. This requires no harness edits, and the setup file
is inert unless `KEV_E2E_RESPONSE_LEDGER` is set, so the harness runs unchanged on
its own. No request bodies or API keys are written to the ledger.

After the suite passes, the launcher checks `generation-settled:{settlement-0}`:

- Every observed success has exactly one successful settlement, with no extra
  successful events or duplicate generation IDs.
- Model, organization and release digest match; output and reasoning tokens are
  zero, and at least one successful event has cached input.
- Each charge follows the synthetic prices and equals its pricing-component sum.
- Final balance equals initial balance minus all event charges, with no remaining
  admission leases.
- Both deployment IDs appear if settlement identity exposes them. The current
  identity does not, so replica coverage is explicitly reported as skipped;
  this run does not prove both replicas received traffic.

Before creating Valkey or starting the gateway, each forwarded replica must return
HTTP 200 from `/health` within 60 seconds (each attempt has a 2-second timeout).
Readiness includes startup inference warmup. The suite's HTTP phase timeout is
10 seconds; the launcher does not issue additional inference requests during preflight.

Gateway readiness and cluster initialization each have a 60-second deadline; finalization
has 30 seconds. Success, failure, timeout, SIGINT and SIGTERM stop the child process
groups and remove only the labelled disposable container, including its data.
Logs and the ledger live in a private `/tmp` directory and are removed afterwards.
Test output is buffered and the ephemeral key is redacted before display. No AWS
calls or production writes are part of this workflow. Uncatchable termination
(SIGKILL or host failure) can leave a `kev-gateway-e2e-*` container; inspect its
`kev-e2e` label and remove that specific container before retrying.
