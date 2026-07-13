# Delivery and delegation plan

## Delivery strategy

Ship one paid vertical path before breadth:

```text
sign in -> create organization + Default workspace -> verified organization top-up
-> create workspace key -> Redis projection
-> official client -> atomic reserve -> one provider -> settle
-> Redis Stream -> PostgreSQL ledger -> dashboard/reconciliation
```

Provider-distribution work reuses the serving path after this slice is reliable. Work packages below are designed for separate subagents with explicit path ownership. Each package gets a GitHub issue, active packet, dependency links, and CI acceptance evidence before merge.

## Global definition of done

- No secrets or customer payloads in repository, logs, snapshots, or artifacts.
- Organization ID is explicit across every tenant/financial boundary; workspace/key IDs are explicit on inference, policy, limit, and usage paths.
- Integer checked money and idempotency are enforced by schema plus tests.
- Domain example tests and relevant TS/Rust property suites pass with replay artifacts.
- Public schema and internal Protobuf changes pass generation/drift/breaking/golden checks.
- Changed behavior is documented in source-of-truth docs/runbooks.
- `python3 tools/devex/check.py` and the package's narrow CI checks pass.
- Handoff names exact files, commands, CI run, evidence class, limitations, and next safe action.

## Work packages

### WP-00 — Monorepo, contracts, test substrate

- Scope: `product/package.json`, pnpm workspace/config, Cargo workspace, `proto/**`, `schemas/**`, `packages/contracts/**`, `packages/testkit/**`, Rust testkit/contracts crates, Docker/CI/tool scripts.
- Deliver: pinned Node/pnpm/Rust/Buf toolchains; Vite/Hono/Rust shells; PostgreSQL/Redis/fake-provider containers; Protobuf-ES/Prost generation; public protocol schemas; Vitest/fast-check/nextest/proptest/Testcontainers; cross-language `PropertyTrace`; seed/replay wrapper; GitHub Actions graph.
- Acceptance: all required commands in `TESTING_AND_CI.md` exist; generated drift is detected; a deliberately failing TS and Rust property is shown to shrink/replay in CI fixture tests; no paid secrets required.
- Dependencies: none.
- Blocks: all packages.

### WP-01 — PostgreSQL organization/workspace and ledger domain

- Scope: `packages/db`, `packages/authz`, core part of `packages/billing`, migrations and domain/PBT tests.
- Deliver: users, organizations and memberships, automatic Default workspace, workspaces and memberships, organization/workspace invitations, workspace-bound keys, interval budgets, price books, organization top-up/payment records, balanced ledger/materialized organization balance, usage/outbox/audit schema, repositories and role policy.
- Acceptance: migration up/down policy; exactly one non-deletable Default workspace per organization; workspace membership/key organization consistency; constraints prevent imbalance/duplicate effect; fast-check covers ledger/authorization; no tenant query without organization and required workspace scope.
- Dependencies: WP-00.

### WP-02 — Hono API, auth, and Vite console

- Scope: `apps/control-api`, `apps/web`, `packages/ui`, auth/session UI and non-financial domain wiring.
- Deliver: Hono Node server, Better Auth session routes, tRPC context/routers, Vite React shell, Tailwind/shadcn, TanStack Router/Query, organization/default-workspace onboarding, organization/workspace switchers, both membership surfaces, keys, overview, models/routes/limits, usage/credits/settings skeletons.
- Acceptance: Hono request tests; session/CSRF/organization/workspace guards; generated role-isolation/default-workspace properties; Testing Library/Playwright happy/error/a11y flows; production Vite build.
- Dependencies: WP-00 and WP-01 schemas/interfaces.
- Parallelism: UI can begin against typed fake tRPC services after WP-00; financial screens wait for WP-03.

### WP-03 — Top-ups, outbox, projection, reconciliation worker

- Scope: financial domain remainder, Stripe Hono route, `apps/control-worker`, Redis projection library, credits UI procedures/pages.
- Deliver: organization top-up intents/Checkout, signed idempotent webhooks, organization ledger posting, refunds/chargebacks, outbox claimer, versioned organization/workspace/key Redis projector, stream consumer, continuous/full reconciliation, fenced rebuild CLI/runbook, safe receipts/history.
- Acceptance: Stripe fixture/model traces prove redirect non-effect and duplicate/reordered exactly-once behavior; worker crash/redelivery tests; organization credit plus nested workspace/key window reconciliation properties; repair leaves equality or organization closed.
- Dependencies: WP-00, WP-01. API/UI coordination with WP-02.

### WP-04 — Rust Redis admission and settlement

- Scope: `gateway-admission`, generated contracts integration, Redis scripts/functions, gateway lifecycle hooks, Rust PBT.
- Deliver: organization-tagged Redis keys, key-to-organization/workspace auth, version/epoch checks, max-cost reserve, organization low-credit plus workspace/key budgets/concurrency, lease/heartbeat/sweeper, settle/overage, Redis Stream events, fail-closed readiness.
- Acceptance: proptest-state-machine covers all billing commands/invariants; real Redis cross-workspace concurrency tests prove no shared-credit overspend and all nested caps; stream append and mutations are atomic; gateway process has no internal client dependency except Redis.
- Dependencies: WP-00 contract/test substrate; policy contract from WP-01/WP-03.
- Blocks: provider dispatch.

### WP-05 — Rust protocols, core routing, fake providers

- Scope: gateway server/core, OpenAI/Anthropic ingress crates, provider trait, fake providers, schemas/conformance fixtures.
- Deliver: `/v1/models`, Chat Completions and Messages stream/non-stream, request/attempt IDs, error translation, cancellation, deterministic routing, bounded fallback, upstream interface.
- Acceptance: protocol parser/PBT and fixture matrix; official SDK fake E2E; no dispatch hook can execute without WP-04 admission token; malformed/midstream faults settle exactly once.
- Dependencies: WP-00, WP-04 interfaces. Can develop handler parsing in parallel against a fake admission trait.

### WP-06 — Upstream provider adapters and pricing

- Scope: owned, OpenAI, Anthropic, OpenRouter, and generic-compatible adapter crates; price/capability configs.
- Deliver: explicit capability profiles, header/secret handling, translation, SSE mapping, retry/cancel/usage evidence, buy-cost capture, reservation exposure bounds.
- Acceptance: adapter fixture matrix and PBT support-subset roundtrips; no lossy supported feature; retries remain within reservation; live calls excluded unless protected job.
- Dependencies: WP-04, WP-05.

### WP-07 — End-to-end vertical slice and console completion

- Scope: integration wiring across API/worker/gateway, dashboard completion, docs/quickstarts.
- Deliver: sign-up through organization creation/default workspace/funding and official-client request to reconciled dashboard; extra workspace with distinct models/limits/key; key rotation/revoke; top-up history; request details; operator freeze/rebuild views/CLI.
- Acceptance: Playwright plus fake official-client E2E verifies PostgreSQL ledger and Redis state; PBT regression corpus; error/empty/loading/a11y flows; quickstart copy/paste in CI.
- Dependencies: WP-02 through WP-06.

### WP-08 — Operations, security, and protected real-provider CI

- Scope: deployment manifests, observability, runbooks, GitHub `provider-e2e` workflow, secret/budget preflight.
- Deliver: managed Redis requirements, network/secret policies, metrics/alerts, backups/restore drills, stream/reconciliation dashboards, OpenAI/Anthropic real smoke, sanitized artifacts.
- Acceptance: fault drills for Redis/worker/provider; paid job budget guard; one stream/non-stream request per provider through gateway; missing secrets fail only the protected context; no body/token logs.
- Dependencies: WP-06, WP-07.

### WP-09 — OpenRouter and gateway distribution spike

- Scope: `services/gateway` provider-facing profile, integration configs/fixtures, `product/evidence/integrations/**`, decision brief.
- Deliver: source-backed OpenRouter organization/workspace/key/limit/routing feature brief, provider `/v1/models` profile, provider Chat Completions matrix, 24-hour staging soak under an explicit test budget, economics/capacity model, Cloudflare/LiteLLM/Portkey/Kong/Vercel-compatible configs where currently supported.
- Acceptance: source-dated requirement matrix; measured protocol/uptime/TTFT/throughput/reconciliation evidence; go/no-go recommendation with uncertainty; no application/publish action without human approval.
- Dependencies: WP-05 through WP-08; documentation/config exploration can begin earlier.

### WP-10 — Seed launch and design partners

- Scope: staging/production release packet, onboarding docs, support/runbooks, metric review.
- Deliver: canary, funded design-partner onboarding, incident/support path, activation/retention/margin dashboard, weekly decision record.
- Acceptance: launch gates in `PRODUCT_SPEC.md`; restore/reconciliation drill; at least one real funded request reconciles end to end; customer feedback and unit economics are recorded without private data.
- Dependencies: WP-08; WP-09 is optional for direct launch.

## Contract-first parallel plan

```text
WP-00
 ├─> WP-01 ──────> WP-03 ─┐
 ├─> WP-02 ────────────────┼─> WP-07 ─> WP-08 ─> WP-10
 └─> WP-04 ─> WP-05 ─> WP-06 ┘                    │
                            └────────────> WP-09 ──┘
```

One integration owner approves changes to `proto/**`, public schemas, Redis key/script contracts, and ledger semantics. Other agents propose contract changes in their issue before generating code, preventing simultaneous incompatible edits.

Suggested first delegation wave after WP-00:

- Agent A: WP-01 database/authz/ledger domain.
- Agent B: WP-02 Vite/Hono UI/API against contract fakes.
- Agent C: WP-04 Rust admission/Redis state machine.
- Agent D: WP-05 public protocols/fake providers against fake admission.
- Agent E: source-only portion of WP-09 integration requirement matrix.

WP-03 starts once WP-01 ledger interfaces stabilize. WP-06 starts after protocol/admission interfaces compile. The integration owner runs shared traces continuously.

## Implementation checkpoints

1. **Contract checkpoint:** organization/workspace/key schemas generate, PBT replay works, dependencies frozen enough for parallel work.
2. **Money checkpoint:** organization top-up/ledger/projector and organization-credit/workspace-limit Redis admission independently satisfy model invariants.
3. **Vertical checkpoint:** fake official clients fund, call, settle, reconcile, and display usage.
4. **External checkpoint:** protected real-provider smoke and failure drills pass inside cost limits.
5. **Distribution checkpoint:** OpenRouter/other-gateway evidence supports go/no-go.
6. **Revenue checkpoint:** design-partner paid retention and contribution margin decide next product breadth.

## Scope discipline

No package may weaken fail-closed admission to unblock a demo. If a safe reserve cannot be computed, reject. If reconciliation cannot prove a balance, close the workspace. If an upstream feature cannot be translated, return an explicit unsupported error. Record failures and continue with the next bounded implementation branch.
