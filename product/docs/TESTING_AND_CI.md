# Testing and CI

The product owner will not run this repository locally. Therefore the acceptance authority is automated CI plus durable artifacts, and every implementation packet must expose the same commands to coding agents in containers/devboxes.

## Test pyramid

### TypeScript

- Vitest for domain/unit and Hono integration tests.
- `fast-check` for property and model-based state-machine tests.
- Hono `app.request()` for transport tests without a listening socket.
- Testing Library and MSW for components, hooks, and server-state failure modes.
- Playwright for browser flows against built Vite assets, API, PostgreSQL, Redis, and Stripe fixtures.
- Testcontainers where process isolation is needed; CI service containers are acceptable when tests reset namespaces deterministically.

### Rust

- standard unit/doc tests plus `cargo nextest` for workspace execution.
- `proptest` for parsers, arithmetic, protocol transformations, and generated inputs.
- `proptest-state-machine` for Redis admission/settlement/reconciliation transitions.
- Redis Testcontainers for real script/function behavior, concurrency, failover-compatible key slotting, and stream semantics.
- Wiremock or a purpose-built Axum fake provider for timeouts, malformed SSE, disconnects, usage variants, and retries.
- Criterion benchmarks for admission script load and parser/stream hot paths after correctness.

## Property suites

| Suite | Generator/actions | Required properties |
| --- | --- | --- |
| Money | arbitrary valid prices, units, limits, extreme `i64`/`bigint` values | no float conversion; checked overflow; nonnegative reserve; reserve covers valid bounded charge. |
| Ledger | top-ups, charges, refunds, promotions, chargebacks, duplicates | entries balance; idempotency; append-only corrections; derived balance matches model. |
| Authorization | users, organizations, workspaces, both memberships, roles, invitations, keys | no cross-organization/workspace read/write; one Default workspace; membership implications; last organization owner retained; revoked key always fails. |
| Payments | valid/invalid/reordered/duplicate Stripe event traces | redirects have no effect; exactly-once financial effect; impossible transitions quarantine. |
| Admission | organization top-up, workspace/key limits, cross-workspace reserve, settle, cancel, renew, overage | invariants in `BILLING_AND_REDIS.md`; no unfunded dispatch; organization credit and nested caps. |
| Streams/reconciliation | redelivery, consumer crash, sequence gap, lag, rebuild, epoch change | posting once; stale events fenced; equality or closed state; no blind refund. |
| Contracts | generated valid/invalid Protobuf values, additive unknown fields | TS/Rust encode/decode agreement; deterministic generation; compatibility. |
| Protocols | valid support-subset JSON/SSE and malformed variants | lossless supported normalization; explicit unsupported rejection; terminal/event ordering. |
| Routing | target health/weights/capabilities and bounded failures | deterministic seed; policy respected; cost never exceeds admitted attempt exposure. |

PBT complements examples: each bug found by a property receives a small example/regression fixture after shrinking. Do not encode exact framework implementation details as properties; test externally meaningful invariants.

## Stateful model architecture

Maintain a small pure reference model in `packages/testkit` and a parallel Rust model in `gateway-testkit`. Define a language-neutral `PropertyTrace` Protobuf containing initial organization credit/policy, workspaces/keys/limits, ordered commands, concurrency barriers, injected faults, expected coarse outcomes, seed, and shrink path.

Fast-check can generate and shrink a trace against TypeScript domain services. Rust can generate against Redis, and both can replay a stored trace. This does not require both test frameworks to share a PRNG; the minimized command trace is the portable artifact.

Concurrency cases use explicit barriers/schedules rather than wall-clock sleeps:

- N simultaneous reserves from several workspaces against one remaining organization balance;
- settle versus duplicate settle;
- lease sweeper versus heartbeat/settle;
- organization refund projection versus workspace admissions;
- stale projection version versus newer top-up;
- stream claim/redelivery versus first consumer commit.

## Seeds, shrinking, and replay

Every property invocation reads optional `PBT_SEED` and `PBT_PATH`; otherwise CI derives a logged seed from run identity. On failure:

- print framework seed and shrink path;
- serialize minimized `PropertyTrace` when applicable;
- write JUnit/test output and relevant safe Redis/PostgreSQL state hashes;
- upload artifacts for at least 30 days;
- print exact commands such as:

```sh
PBT_SEED=123 PBT_PATH='2:1:0' pnpm test:pbt -- billing
cargo test -p gateway-pbt admission -- --nocapture proptest-seed=...
pnpm test:pbt:replay artifacts/property-trace.pb
```

The scaffold work package must verify the exact proptest replay syntax supported by the pinned version and wrap it in `./tools/pbt/replay`, so later agents do not need to remember framework flags.

## Run depths

Exact counts are tuned to CI duration using recorded timings, but start with:

- pull request: deterministic unit/integration plus at least 1,000 simple cases per critical property and 100 state-machine traces, total PBT target under 8 minutes;
- main: 10,000 simple cases and 1,000 state-machine traces, target under 15 minutes;
- nightly: time-budgeted deep run (at least 100,000 simple cases where throughput permits), fault injection, and cross-language replay corpus, target under 45 minutes;
- release: main suite plus protocol conformance and real-provider smoke.

Shard by stable property suite, not random test file distribution, so failures replay. A timeout is a failed/recorded result; the job never silently truncates a property and reports success.

## Official-client E2E

### Always-on fake-provider job

On every pull request, boot Redis, Rust gateway, and deterministic fake OpenAI/Anthropic upstreams. Run official `openai` and `@anthropic-ai/sdk` TypeScript clients with base URL pointed at the gateway. Cover:

- model list where client supports it;
- non-stream and stream Chat Completions;
- non-stream and stream Anthropic Messages;
- 402, 429, key revocation, timeout, cancellation, malformed upstream, and duplicate settlement;
- usage/ledger assertion after the worker posts events.

No provider secret is present, including on forked/untrusted pull requests.

### Protected real-provider job

On pushes to main, nightly schedule, and manual dispatch, use GitHub environment `provider-e2e` with encrypted `OPENAI_API_KEY` and `ANTHROPIC_API_KEY`. The same official clients point to the Rust gateway, which routes to the real providers.

- Models are controlled by reviewed environment variables `OPENAI_E2E_MODEL` and `ANTHROPIC_E2E_MODEL`; choose the provider's current cheapest capable model and pin it in environment configuration.
- Prompt requests an exact tiny response; output cap is 8 tokens or the smallest supported value.
- Run one non-stream and one stream request per provider, concurrency one, at most one network retry, five-minute job timeout.
- A preflight allowlist rejects expensive models or high token limits.
- Budget target is below $0.05 per run, with a monthly GitHub/environment and provider-account cap.
- Log request IDs, model, status, schema assertions, metered units, and response hash only—never body or credentials.
- Missing protected secrets fail the protected job with a clear configuration error; they are not silently skipped.

Real smoke proves current external compatibility but is not a replacement for deterministic fault coverage. Model aliases and API behavior can change, so the implementation owner verifies current official docs when pinning model IDs.

## GitHub Actions graph

```text
devex + formatting
  ├── contracts lint/breaking/generate/drift/golden
  ├── TypeScript typecheck/lint/unit/PBT
  ├── Rust fmt/clippy/nextest/PBT
  ├── integration: PostgreSQL + Redis + fake providers
  ├── Vite build + Playwright
  └── fake official-client E2E

main/nightly/manual after required jobs
  ├── deep PBT/fault injection
  └── protected real-provider E2E
```

Pin action SHAs and tool versions. Use lockfiles and cached dependencies without caching generated test outcomes. Upload contract diffs, JUnit, coverage summaries, minimized traces, and sanitized service logs. Never upload `.env`, Redis dumps containing key projections, payment payloads, or request bodies.

## Required root scripts

| Command | Contract |
| --- | --- |
| `pnpm verify:ts` | format check, lint, typecheck, Vitest. |
| `pnpm test:pbt` | bounded fast-check suites with replay output. |
| `pnpm contracts:check` | Buf format/lint/breaking/generate/drift and golden fixtures. |
| `cargo nextest run --workspace` | Rust unit/integration tests. |
| `cargo test -p gateway-pbt` | bounded proptest state machines. |
| `pnpm test:conformance` | public JSON/SSE fixtures against Rust gateway. |
| `pnpm test:e2e:fake` | official clients through gateway/fakes. |
| `pnpm test:e2e:providers` | protected minimal paid smoke only. |
| `pnpm verify` | all required non-paid pull-request checks. |

Every task handoff records commands, CI run URL when available, seeds/artifacts for failures, and which paid tests were intentionally not invoked.
