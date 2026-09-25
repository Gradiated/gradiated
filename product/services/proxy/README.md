# Proxy

The proxy is the public inference front door. It relays requests to Anthropic
and OpenAI with the customer's own provider key, and forwards every other
inference request to the gateway unchanged. The
[proxy feature plan](../../../docs/PROXY_FEATURE_PLAN.md) owns its scope,
availability target and rollout.

```text
customer ── ALB ──> proxy ─┬─ hosted model ─────────────> gateway
                           └─ provider model with key ──> Anthropic or OpenAI
```

The proxy must change rarely. It does no billing, translation, tokenization or
usage parsing. It has no Valkey or ClickHouse client and shares no code with
the gateway.

## Request handling

The rule: with a provider key, a request relays to that key's provider unless it
names a model we host. Everything else goes to the gateway. The key alone picks
the provider (`sk-ant-` is Anthropic, other `sk-` keys are OpenAI), so the proxy
needs no list of paths or provider models. Audio, images, files and new
endpoints relay with no proxy change.

1. Take an in-flight slot, read the body within the byte limit, then reserve its
   bytes in the process budget. A full slot count or budget returns
   `proxy_overloaded`.
2. Read the Gradiated key and the provider key. Either can be in
   `Authorization` or `x-api-key`; the Gradiated key can also be in
   `x-gradiated-api-key`. The format of each value decides what it is.
3. With a provider key and a body that does not name a hosted model,
   authenticate the Gradiated key, then relay the same method, path, query and
   bytes to the provider. The provider key stays in the header the client used,
   so OAuth tokens work.
4. Everything else goes to the gateway. Credentials that are not Gradiated keys
   are removed first, so the gateway never holds a provider key.
5. `/health` and `/metrics` get a local 404, because the gateway serves them on
   its public port. This goes away when the gateway moves them to an admin port.

A path without the `/v1` prefix, which the gateway also accepts, gains it on the
way to a provider. Relayed bodies are buffered, so the request byte limit also
applies to provider uploads. WebSocket upgrades, such as OpenAI's Realtime API,
are not supported.

## Local development

`pnpm dev` in `product/` starts the proxy on `127.0.0.1:3003`, the gateway on
3002 and the collector on 3004. Use `http://127.0.0.1:3003/v1` as the local SDK
base URL. Capture is wired to the local collector and SeaweedFS bucket; it still
requires the workspace capture switch and a task header. `pnpm smoke:capture`
checks the chain without real provider calls. See [Product](../../README.md).

## Capture

The proxy sends relayed generations to the collector when the workspace has
`trace_capture_enabled` and the request has a non-empty `x-gradiated-task`
header. Only unencoded UTF-8 JSON and event-stream responses are captured. Encoded or invalid UTF-8 bodies are skipped and counted as `unsupported`; the client still receives the original bytes. The proxy does not
parse the bodies: each line of the `application/x-ndjson` batch holds the raw
request and response text with the generation's identifiers, and the collector
does the parsing. See the [traces plan](../../../docs/TRACES_PLAN.md).

- The response is copied as it streams, and the generation is queued when the
  stream completes, fails or is cancelled.
- One byte budget (`PROXY_CAPTURE_BUFFER_BYTES`) covers generations that are
  being recorded, queued or sent. A generation that does not fit, or that is
  larger than 16 MiB, is dropped.
- One background task sends a batch at 1 MiB or after 100 ms. Each post has a
  5-second timeout. A failed post is retried once, then dropped.
- On SIGTERM, queued generations are sent after the open streams finish, for at
  most 15 seconds.

Capture never delays or fails a customer request.

## Failure behavior

| Failure                     | Behavior                                                                                                                                    |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| PostgreSQL unavailable      | Keys seen within the stale grace keep relaying. Unseen keys get `serving_state_unavailable`. Hosted traffic and readiness are not affected. |
| Catalog refresh fails       | The last good catalog stays in use.                                                                                                         |
| Gateway refuses or resets   | Hosted requests get `gateway_unavailable`. Relays continue.                                                                                 |
| Gateway silent              | Hosted requests get `gateway_timeout` at the header deadline.                                                                               |
| Upstream stream goes silent | The stream fails at the idle deadline and the upstream connection closes.                                                                   |
| Customer disconnects        | The upstream connection closes, which cancels the provider call or the hosted generation.                                                   |
| SIGTERM                     | Readiness fails, the listener closes, and open streams run to the total deadline.                                                           |
| Collector unavailable       | Captured generations are dropped and counted. Customer requests are not affected.                                                           |

## Configuration

| Variable                              | Default                     | Meaning                                               |
| ------------------------------------- | --------------------------- | ----------------------------------------------------- |
| `PROXY_GATEWAY_ORIGIN`                | required                    | Gateway origin inside the cluster                     |
| `DATABASE_URL`                        | required                    | Read-only PostgreSQL connection                       |
| `DATABASE_CA_BUNDLE_PATH`             | none                        | Extra certificate authorities, such as the RDS bundle |
| `PROXY_BIND_ADDRESS`                  | `0.0.0.0:3003`              | Public listener                                       |
| `PROXY_ADMIN_ADDRESS`                 | `0.0.0.0:9003`              | Health, readiness and metrics                         |
| `PROXY_ANTHROPIC_ORIGIN`              | `https://api.anthropic.com` | HTTPS unless loopback                                 |
| `PROXY_OPENAI_ORIGIN`                 | `https://api.openai.com`    | HTTPS unless loopback                                 |
| `PROXY_RELAY_ENABLED`                 | `true`                      | `false` sends every request to the gateway            |
| `PROXY_IDENTITY_FRESH_SECONDS`        | `15`                        | Revocation latency while PostgreSQL is healthy        |
| `PROXY_IDENTITY_STALE_GRACE_SECONDS`  | `3600`                      | How long a known key works during a PostgreSQL outage |
| `PROXY_IDENTITY_CAPACITY`             | `100000`                    | Cached keys                                           |
| `PROXY_IDENTITY_MAX_CONCURRENT_LOADS` | `128`                       | Concurrent key queries                                |
| `PROXY_CATALOG_REFRESH_SECONDS`       | `5`                         | Hosted catalog refresh interval                       |
| `PROXY_MAX_REQUEST_BYTES`             | `32000000`                  | Largest request body                                  |
| `PROXY_REQUEST_BUFFER_BYTES`          | `268435456`                 | Bytes buffered across all requests                    |
| `PROXY_MAX_IN_FLIGHT`                 | `4000`                      | Open requests                                         |
| `PROXY_GATEWAY_CONNECT_SECONDS`       | `2`                         |                                                       |
| `PROXY_GATEWAY_HEADER_SECONDS`        | total                       | Covers a whole non-streaming hosted generation        |
| `PROXY_PROVIDER_CONNECT_SECONDS`      | `10`                        |                                                       |
| `PROXY_PROVIDER_HEADER_SECONDS`       | total                       | Never shorter than the client SDK's wait              |
| `PROXY_IDLE_SECONDS`                  | total                       | Largest gap between response chunks                   |
| `PROXY_TOTAL_SECONDS`                 | `630`                       | Whole exchange, and the drain window                  |
| `PROXY_BODY_READ_SECONDS`             | `60`                        | Time allowed to receive the request body              |
| `PROXY_COLLECTOR_URL`                 | unset                       | Collector intake URL; unset turns capture off         |
| `PROXY_COLLECTOR_TOKEN`               | unset                       | Collector bearer token; required with the URL         |
| `PROXY_CAPTURE_BUFFER_BYTES`          | `268435456`                 | Bytes held across all captured generations            |

The collector secret must be provisioned before deploying a proxy with capture configured. The capture byte budget includes queued record overhead and task, trace, session, path and content-type strings.

## Metrics

The admin port serves Prometheus metrics with the `gradiated_proxy_` prefix. Labels are
fixed values; keys, tenants and model names never appear.

| Metric                                           | Labels                                                                       |
| ------------------------------------------------ | ---------------------------------------------------------------------------- |
| `gradiated_proxy_service_info`                   |                                                                              |
| `gradiated_proxy_requests_total`                 | `destination` (`gateway`, `anthropic`, `openai`, `local`), `status`          |
| `gradiated_proxy_upstream_header_seconds`        | `destination`                                                                |
| `gradiated_proxy_in_flight`                      | `destination`                                                                |
| `gradiated_proxy_identity_lookups_total`         | `result` (`fresh`, `loaded`, `stale`, `not_found`, `unavailable`)            |
| `gradiated_proxy_identity_queries_total`         |                                                                              |
| `gradiated_proxy_catalog_age_seconds`            |                                                                              |
| `gradiated_proxy_catalog_refresh_failures_total` |                                                                              |
| `gradiated_proxy_captures_total`                 | `result` (`sent`, `full`, `too_large`, `closed`, `collector`, `unsupported`) |

## Tests

Run the commands from `product/`. The end-to-end suite needs Docker.

```sh
pnpm --filter @gradiated/proxy check      # format, Clippy, unit tests, TypeScript
pnpm --filter @gradiated/proxy test:e2e   # builds both binaries, then runs the suite
```

The end-to-end suite runs the real proxy binary in front of the real gateway
binary. It reuses the gateway suite's stack: PostgreSQL, Valkey and mock
runtimes. A loopback mock provider stands in for Anthropic and OpenAI, and
breakable TCP links in front of PostgreSQL and the gateway make outages real
connection failures.

| Path                                 | Contents                                                                     |
| ------------------------------------ | ---------------------------------------------------------------------------- |
| `test/e2e/routing.test.ts`           | Where each request goes, and parity with direct gateway calls                |
| `test/e2e/credentials.test.ts`       | Every placement of the Gradiated and provider keys, and refused combinations |
| `test/e2e/relay.test.ts`             | Byte-exact bodies, header isolation, provider statuses, streaming            |
| `test/e2e/identity.test.ts`          | Relay authorization and revocation timing                                    |
| `test/e2e/outages.test.ts`           | PostgreSQL and gateway outages                                               |
| `test/e2e/capacity.test.ts`          | In-flight cap, body limit and byte budget                                    |
| `test/e2e/lifecycle.test.ts`         | Cancellation through both hops and draining on SIGTERM                       |
| `test/e2e/operations.test.ts`        | Kill switch, metrics and logs                                                |
| `test/e2e/capture.test.ts`           | Relayed generations reaching the collector, a hung collector, SIGTERM drain  |
| `test/e2e/thread-continuity.test.ts` | What our model returns, and provider history arriving at our model           |
| `test/e2e/sdk/*.test.ts`             | One file for each official SDK, with only the base URL changed               |
| `test/e2e/support/`                  | Mock provider and collector, TCP link, proxy process, fixtures, wire bodies  |

Proxy logs are written to `<repository>/.agents/runtime/proxy-e2e/`.
