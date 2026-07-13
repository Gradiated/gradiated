# Delivery and delegation plan

## Delivery strategy

Ship one paid vertical path before breadth:

```text
sign in -> create organization + Default workspace -> verified organization top-up
-> create API key in implicit Default workspace -> Redis projection
-> existing direct provider/model or grad/medium/standard -> immutable route release
-> atomic reserve -> exact curated provider or owned Grad lane -> settle/credit
-> Redis Stream -> PostgreSQL ledger -> dashboard/reconciliation
-> settled usage -> ClickHouse trace analytics; encrypted payload -> S3 detail
-> workload profile -> customer-controlled Grad migration
```

Provider-distribution work reuses the serving path after this slice is reliable. Work packages below are designed for separate subagents with explicit path ownership. Each package gets a GitHub issue, active packet, dependency links, and acceptance evidence before its owned commit is pushed directly to `main`.

AWS/Kubernetes implementation is a coordinated workstream in [`../../infra/docs/DELIVERY_PLAN.md`](../../infra/docs/DELIVERY_PLAN.md). Product packages own application behavior, containers, contracts, and tests. Infrastructure packages own Terraform, managed services, Helm/GitOps, deployment workflows, capacity qualification, and cloud operations. Neither workstream duplicates those resources.

## Global definition of done

- No secrets in repository/logs/artifacts. Customer payload traces exist only in the encrypted Product Intelligence data path with tested policy/retention/access/delete behavior.
- Organization ID is explicit across every tenant/financial boundary; workspace/key IDs are explicit on inference, policy, limit, and usage paths.
- Integer checked money and idempotency are enforced by schema plus tests.
- Domain example tests and relevant TS/Rust property suites pass with replay artifacts.
- Public schema and internal Protobuf changes pass generation/drift/breaking/golden checks.
- Direct IDs never cross provider/model/version; Grad IDs never leave owned inference or change effort/speed; unsupported capabilities/data policy never degrade silently.
- Changed behavior is documented in source-of-truth docs/runbooks.
- `python3 tools/devex/check.py` and the package's narrow CI checks pass.
- Handoff names exact files, commands, CI run, evidence class, limitations, and next safe action.

## Work packages

### WP-00 — Monorepo, contracts, test substrate

- Scope: `product/package.json`, pnpm workspace/config, Cargo workspace, `proto/**`, `schemas/**`, `packages/contracts/**`, `packages/testkit/**`, Rust testkit/contracts crates, product test/build scripts. Root Compose/mprocs, `grad`, Terraform, charts, and deployment workflows belong to infrastructure I-00/I-05/I-06/I-09.
- Deliver: pinned toolchains; Vite/Hono/Rust shells; PostgreSQL/ClickHouse/Valkey/S3 test substrate; OpenAI/Anthropic/Google/owned fakes; Protobuf generation; public protocol fixtures; provider/model alias, Grad effort/speed, data mode, trace analytics/object and migration contracts; Vitest/fast-check/nextest/proptest; cross-language replay. Coordinate local containers/workflows with I-00/I-09.
- Acceptance: all required commands in `TESTING_AND_CI.md` exist; generated drift is detected; a deliberately failing TS and Rust property is shown to shrink/replay in CI fixture tests; no paid secrets required.
- Dependencies: none.
- Blocks: all packages.

### WP-01 — PostgreSQL organization/workspace and ledger domain

- Scope: `packages/db`, `packages/authz`, core part of `packages/billing`, migrations and domain/PBT tests.
- Deliver: tenant/key/budget domain; curated provider/model/alias, Grad effort/speed, endpoint/qualification/release/rollout schema; data/retention policy; trace registry/wrapped-key/tombstone and analytics-outbox/checkpoint schema; workload/migration/experiment schema; immutable prices; top-up/payment/ledger/balance; usage/correction/outbox/audit repositories and role policy.
- Acceptance: migration up/down policy; exactly one non-deletable Default workspace per organization; workspace membership/key organization consistency; constraints prevent imbalance/duplicate effect; fast-check covers ledger/authorization; no tenant query without organization and required workspace scope.
- Dependencies: WP-00.

### WP-02 — Hono API, auth, and Vite console

- Scope: `apps/control-api`, `apps/web`, `packages/ui`, auth/session UI and non-financial domain wiring.
- Deliver: Hono/Better Auth/tRPC and Vite/Tailwind/shadcn shell; typed tenant-scoped trace query repository; five screens; silent Default workspace; existing-provider and Grad quickstarts; Grad effort × speed selector; curated Direct Providers tab; ClickHouse-backed workload/trace/migration UI with separately authorized S3 detail; progressive Data retention/team/workspace/budget settings.
- Acceptance: transport/authz properties; Playwright proves an unambiguous existing model can migrate with base URL/key only and a new workload can select `grad/medium/standard`; Product Intelligence disclosure/no-retain controls; trace/recommendation/experiment flows; happy/error/a11y/narrow-screen; production build.
- Dependencies: WP-00 and WP-01 schemas/interfaces.
- Parallelism: UI can begin against typed fake tRPC services after WP-00; financial screens wait for WP-03.

### WP-03 — Top-ups, outbox, projection, reconciliation worker

- Scope: financial domain remainder, Stripe Hono route, `apps/control-worker`, Redis projection library, credits UI procedures/pages.
- Deliver: existing financial flow plus versioned provider/model/alias/Grad/data-policy projection, failed-request credits, internal replay/operator budget and live-canary experiment budget reconciliation.
- Acceptance: Stripe fixture/model traces prove redirect non-effect and duplicate/reordered exactly-once behavior; failed-request correction traces prove exactly one eligible credit; worker crash/redelivery tests; organization credit plus nested workspace/key window reconciliation properties; repair leaves equality or organization closed.
- Dependencies: WP-00, WP-01. API/UI coordination with WP-02.

### WP-04 — Rust Redis admission and settlement

- Scope: `gateway-admission`, generated contracts integration, Redis scripts/functions, gateway lifecycle hooks, Rust PBT.
- Deliver: existing atomic admission plus canonical provider/model or Grad effort/speed/data-policy checks, fixed-release reserve, experiment cap for live canaries, and billing-stream priority over trace ingestion.
- Acceptance: proptest-state-machine covers all billing commands/invariants; real Redis cross-workspace concurrency tests prove no shared-credit overspend and all nested caps; stream append and mutations are atomic; gateway process has no internal client dependency except Redis.
- Dependencies: WP-00 contract/test substrate; policy contract from WP-01/WP-03.
- Blocks: provider dispatch.

### WP-05 — Rust protocols, capability planner, fake providers

- Scope: gateway server/core, OpenAI/Anthropic/Google ingress crates, provider trait, fake providers, schemas/conformance fixtures.
- Deliver: OpenAI Chat/Responses/Embeddings, Anthropic Messages and versioned Google GenerateContent/stream skins; canonical provider/model and Grad effort/speed parsing; unique bare aliases; provider/no-retain headers; trace hook; identity errors and upstream interface.
- Acceptance: protocol parser/PBT and fixture matrix; official SDK fake E2E for all five endpoints; unsupported/lossy fields, hidden transforms and context overflow fail before dispatch; no dispatch hook executes without WP-04 admission token; malformed/midstream faults settle exactly once.
- Dependencies: WP-00, WP-04 interfaces. Can develop handler parsing in parallel against a fake admission trait.

### WP-06 — Curated providers and Grad effort/speed releases

- Scope: provider/model/alias and Grad product/release domain; Rust route planner; owned/OpenAI/Anthropic/Google adapters; operator-only OpenRouter/generic; qualification/pricing.
- Deliver: curated direct registry and unique aliases; 4×4 Grad grammar with catalog-gated cells; same-provider and owned-only route boundaries; scoped qualification; immutable fixed-price releases; canary/session/rollback; health/capacity; capability/data-policy profiles; translation/stream/retry/usage/buy-cost exposure.
- Acceptance: PBT proves alias uniqueness, direct identity, Grad owned/effort/speed fidelity, deterministic decisions, no speed downgrade, fixed price/rollback; adapter conformance; effort/speed monotonicity release gates; retries stay bounded.
- Dependencies: WP-04, WP-05.
- Delegation: split 06A catalog/qualification/release control plane and 06B Rust route/adapters only after one interface owner freezes Protobuf, Redis projection and qualification manifest schemas.

### WP-06C — Owned inference edge, cells, runtime and fleet controller

- Scope: `apps/fleet-controller`, `services/inference-edge`, `services/cell-agent`, owned runtime adapters, fleet/cell Protobuf, signed manifests/targets, fake provider/cell simulator and PBT. Provider account/network/Terraform/Helm and paid qualification are coordinated infrastructure work in `MULTI_PROVIDER_GPU_FLEET.md`.
- Deliver: AWS inference edge; direct-mTLS/outbound-relay cell transports; exact-release cell router; vLLM first runtime; always-on workspace/channel/release/retention-class salted KV/prefix cache; capacity intents/leases; provider adapter interface; spot drain/orphan/cost controls; target publication inputs.
- Acceptance: gateway/edge/cell golden contracts; fleet and event state-machine PBT; controller/PG/provider API can be unavailable while existing cells serve; no provider API/Kubernetes discovery on the gateway path; no-retention produces cache hits but no trace payload; cross-scope cache reuse is impossible; abrupt preemption before/after first token has the frozen retry/settlement outcome; one native and one managed-Kubernetes provider class pass bounded qualification before production.
- Dependencies: WP-00, WP-04, WP-05, and WP-06 release schema. Fake edge/cell/runtime work can proceed with WP-06 against frozen manifests.
- Delegation: split 06C-1 contracts/simulator, 06C-2 Rust edge, 06C-3 cell router/runtime/cache, and 06C-4 fleet controller/provider adapters only after one owner freezes event, lease and target epochs.

### WP-07 — Trace intelligence, ClickHouse analytics and migration engine

- Scope: `gateway-trace`, trace worker/processor/projector, ClickHouse schemas/query repository, private object contract, workload/recommendation/experiment domain and UI/API integration. ClickHouse Cloud/PrivateLink plus S3/KMS/Pod Identity/KEDA resources remain infrastructure-owned.
- Deliver: Product Intelligence/no-retain enforcement; credential stripping; public-key trace encryption; bounded Redis stream; per-trace wrapped-key/S3 lifecycle/delete/export; PostgreSQL analytics outbox; idempotent batched ClickHouse request/attempt/evaluation facts and rollups; tenant/time-bounded Hono queries; workload grouping; opportunity/candidate/verified/ready evidence; unbilled replay; approved shadow/live-canary with budgets/stops; no-auto-switch state machine.
- Acceptance: TS/Rust PBT proves no-retain/credential/ciphertext/retention invariants and no automatic migration; ClickHouse schema has no content; duplicate/reordered projection converges; arbitrary tenant queries return no cross-workspace row; tombstone/key destruction denies detail before asynchronous S3/ClickHouse cleanup; ClickHouse outage/backpressure leaves serving/billing/S3 correct; encrypted object roundtrip/delete; replay cannot debit customer; canary cannot exceed caps and stops without changing original traffic.
- Dependencies: WP-00 through WP-06 interfaces; owned replay/canary additionally depends on WP-06C. Coordinate ClickHouse/S3/KMS/projector and external inference capacity with infrastructure packages before production.

### WP-07B — End-to-end vertical slice and console completion

- Scope: integration wiring across API/worker/gateway, dashboard completion, docs/quickstarts.
- Deliver: funded direct-model and `grad/medium/standard` requests to reconciled ClickHouse dashboard/trace and separately authorized S3 detail; workload profile and recommendation to replay/shadow/canary; exact identity/release/cost/retention; extra workspace data/model policy; key/billing/operator flows.
- Acceptance: Playwright/fake-client E2E verifies ledger/Redis/ClickHouse/S3 convergence; direct base-URL migration; Grad grid; Product Intelligence and no-retain; deletion/retention; recommendation never auto-switches; regression/a11y/quickstart CI.
- Dependencies: WP-02 through WP-07.

### WP-08 — Operations, security, and protected real-provider CI

- Scope: application telemetry/freeze interfaces, product incident/financial runbooks, GitHub `provider-e2e` test behavior, secret/budget preflight. Terraform, Helm manifests, AWS observability, and deployment workflows belong to infrastructure I-05/I-06/I-08/I-10.
- Deliver: managed Redis requirements; network/secret/data policies; private trace S3/KMS access/lifecycle; ClickHouse PrivateLink/encryption/RBAC/schema/backups and cost monitoring; billing-vs-trace capacity alerts; outbox/projection/rebuild/restore-with-tombstones/delete drills; financial/trace/recommendation/ModelOps dashboards; OpenAI/Anthropic/Google/owned smoke; sanitized artifacts.
- Acceptance: drills for Redis/worker/provider/route/trace-object/KMS/retention failure; paid budget guard; identity/data-mode probes; no-retain eligibility; plaintext/credential leak scanner; missing secrets fail only protected context; no payload in ordinary logs/artifacts.
- Dependencies: WP-06C, WP-07B.

### WP-09 — OpenRouter provider and gateway distribution

- Scope: `services/gateway` provider-facing profile, integration configs/fixtures, `product/evidence/integrations/**`, decision brief.
- Deliver: maintain the source-backed feature decision brief; isolated provider model-list profile for owned/differentiated supply; Chat Completions/tools matrix; 24-hour staging soak under an explicit budget; early-429/keepalive/midstream behavior; uptime/TTFT/throughput/tool-quality/economics/capacity/receivable reconciliation evidence; Cloudflare/LiteLLM/Portkey/Kong/Vercel-compatible customer configs.
- Acceptance: source-dated requirement matrix; provider channel cannot touch direct-customer credit or credentials; measured protocol/uptime/TTFT/throughput/reconciliation evidence; positive differentiated economics; go/no-go recommendation with uncertainty; no application, terms acceptance, credential submission or publish action without human approval.
- Dependencies: WP-05 through WP-08; documentation/config exploration can begin earlier.

### WP-10 — Seed launch and design partners

- Scope: staging/production release packet, onboarding docs, support/runbooks, metric review.
- Deliver: direct-provider and Grad canaries, funded onboarding, five-minute migration/Grad quickstarts, trace/privacy support, activation/retention/margin/migration dashboard, weekly decision record.
- Acceptance: launch gates in `PRODUCT_SPEC.md`; restore/reconciliation drill; at least one real funded request reconciles end to end; customer feedback and unit economics are recorded without private data.
- Dependencies: WP-08; WP-09 is optional for direct launch.

## Contract-first parallel plan

```text
WP-00
 ├─> WP-01 ──────> WP-03 ─┐
 ├─> WP-02 ────────────────┼─> WP-07 ─> WP-07B ─> WP-08 ─> WP-10
 └─> WP-04 ─> WP-05 ─> WP-06 ─> WP-06C ┘                    │
                                      └────> WP-09 ──────────┘
```

One integration owner approves changes to `proto/**`, public schemas, Redis key/script contracts, and ledger semantics. Other agents propose contract changes in their issue before generating code, preventing simultaneous incompatible edits.

Suggested first delegation wave after WP-00:

- Agent A: WP-01 database/authz/ledger domain.
- Agent B: WP-02 Vite/Hono UI/API against contract fakes.
- Agent C: WP-04 Rust admission/Redis state machine.
- Agent D: WP-05 public protocols/fake providers against fake admission.
- Agent E: source-only portion of WP-09 integration requirement matrix.

WP-03 starts once WP-01 ledger interfaces stabilize. WP-06 starts after protocol/admission interfaces compile. WP-06C starts with fakes after release/cell contracts freeze and coordinates its provider substrates with infrastructure F-00 through F-07. WP-07 starts only after data-mode/trace contracts and infrastructure ownership are frozen. The integration owner runs shared properties continuously.

## Implementation checkpoints

1. **Contract checkpoint:** organization/workspace/key schemas generate, PBT replay works, dependencies frozen enough for parallel work.
2. **Money checkpoint:** organization top-up/ledger/projector and organization-credit/workspace-limit Redis admission independently satisfy model invariants.
3. **Vertical checkpoint:** fake official clients fund, call, settle, reconcile, and display usage.
4. **Experience checkpoint:** existing model migrates with base URL/key where unambiguous; new workload reaches `grad/medium/standard`; both show exact identity/cost.
5. **Model-lane checkpoint:** curated direct identity and Grad effort/speed qualification/price/SLO/rollback satisfy PBT and measured gates.
6. **Owned fleet checkpoint:** one native and one Kubernetes provider class satisfy exact-release edge/cell, always-on cache isolation, abrupt preemption, cleanup, concentration and successful-token margin gates.
7. **Trace checkpoint:** Product Intelligence and no-retain, encryption, retention/delete, billing isolation and no-auto-switch recommendation state pass; no-retention cache remains enabled and ephemeral.
8. **External checkpoint:** protected real-provider/owned smoke and failure drills pass inside cost limits.
9. **Distribution checkpoint:** OpenRouter/other-gateway evidence supports go/no-go.
10. **Revenue checkpoint:** direct workload retention, Grad migration and contribution margin decide next breadth.

## Scope discipline

No package may weaken fail-closed admission to unblock a demo. If a reserve/reconciliation/identity/data-policy guarantee cannot be proved, reject or close admission. Never cross a direct provider/model, leave a Grad effort/speed cell, persist a no-retain trace payload, disable no-retention KV cache, reuse cache across trust domains, let trace load starve billing, overstate recommendation evidence, or auto-switch traffic. Record failures and continue with the next bounded experiment lineage.

Infrastructure gates are equally binding: production does not use a Valkey tier that has not proved zero acknowledged reservation/event loss, CI does not receive static AWS keys, and autoscaling does not replace admission/backpressure. Product WP-00 and infrastructure I-00 establish the shared command/contract boundary before broad delegation.
