# Product delivery plan

Packages are ordered to earn revenue before owned inference breadth. Each package has one contract owner, deterministic examples, property tests for invariants and an agent-runnable handoff. No package may add derived durable state or speculative optionality without a concrete consumer.

## WP-00 — Repository, contracts and `grad`

- Create pnpm/Rust/Python workspaces, Vite/Hono skeleton, Rust gateway workspace, research package and transparent Rust CLI.
- Add Buf/Prost generation for hot cross-language contracts, OpenAPI/JSON goldens, artifact schemas and generated-drift CI.
- Add Vitest/fast-check, nextest/proptest, pytest/Hypothesis, Testcontainers/fakes and replay artifacts.
- Acceptance: `grad start`, bounded verify and fake E2E run unattended in CI; generated diff is empty.

## WP-01 — Organization, workspace and identity

- Better Auth identity/session/recovery; organization/default-workspace creation; org/workspace membership; invitations; role checks; audit.
- Vite/shadcn shell with organization/workspace URL state and accessibility baseline.
- Acceptance: transaction/PBT proves exactly one Default workspace, no cross-tenant membership/key access and retry-safe signup/invite acceptance.

## WP-02 — Ledger, top-ups and limits

- Fixed USD chart, double-entry transactions/entries, organization balance projection, top-up intents, Stripe checkout/webhooks, monthly workspace/key limits.
- No workspace wallets or arbitrary period model.
- Acceptance: model-based PBT proves balanced/idempotent top-up/refund/chargeback/correction and balance rebuild equality under duplicates/reordering/crashes.

## WP-03 — Valkey projection and admission

- Versioned key/policy/catalog/price/balance snapshots; atomic auth/reserve/concurrency/low-balance cap/settle/refund; protected billing stream; rebuild/reconciliation.
- Acceptance: Rust state-machine PBT plus real Valkey proves no overspend within reservation policy, no leaked concurrency, fail-closed uncertainty and convergence after duplicate/out-of-order operations.

## WP-04 — First paid direct-model slice

- OpenAI-compatible public gateway, one provider/model adapter, streaming, canonical errors/usage, usage posting and quickstart.
- Acceptance: official client + fake/real cheapest model tests cover funded success, insufficient balance, cancel, timeout, provider errors and exact settlement; no silent parameter or model change.

## WP-05 — Curated protocols/providers

- Add providers only from demand: OpenAI, Anthropic, Google candidates; `/v1/models`; capability checks; provider endpoint health and explicit eligible failover.
- Publish generic integration recipes for OpenAI SDK, LiteLLM, Cloudflare AI Gateway, Portkey and Helicone based on current documented interfaces.
- Acceptance: protocol conformance/golden/PBT and official clients; adapter cannot accept a capability it cannot preserve.

## WP-06 — Traces and PostgreSQL intelligence

- Public-key trace encryption, bounded trace stream, S3 custody, PostgreSQL registry/grants/tombstones, default retention/no-retention, trace-access and bounded indexed list/chart/workload queries.
- Add recommendations with replay/shadow/canary evidence and explicit approval; no auto-switch.
- Acceptance: no-retention emits no payload; credentials never persist; tenant isolation/delete/export/retention PBT; trace failure cannot starve billing; measured queries meet seed SLO or receive a narrow PostgreSQL rollup.

## WP-07 — Owned inference substrate

- Inference router, cell-agent/runtime local protocol, signed bundle/runtime verification, exact-release health, tenant-salted always-on KV cache, SQL capacity sources/targets/allocations/cells, one-use bootstrap/CSR certificate enrollment and fake provider/cell/CA.
- Acceptance: serving/fleet state-machine PBT, cache isolation, exact-release routing, bootstrap replay denial, certificate rotation/expiry, pre/post-output interruption behavior, lease fencing, uncertain cleanup freeze and zero provider lifecycle/CA issuance calls in serving path.

## WP-08 — First external GPU provider

- One native Rust provider driver with tag/idempotency/observe/drain/release/list-owned; paid bounded qualification on one hardware/runtime class.
- Acceptance: fake conformance plus real startup/stream/cache/preemption/cleanup evidence and zero orphans.

## RF-00 — Research foundations

- Python/TS/Rust research API refs, compositional artifact/bundle/qualification schemas, local tiny-model fixtures and S3/ECR CAS/signing.
- Acceptance: canonical digest/signature and cross-language fixture equality.

## RF-01 — Research domain and API

- Python sole-writer API for program, hypothesis, campaign, experiment spec/run, evidence, bundle and qualification state; Hono BFF/operator UI.
- Acceptance: Hypothesis state models prove authority/version/budget/provenance transitions and immutable sealed evidence.

## RF-02 — Temporal execution

- Deterministic workflows/activities for plan/run/evaluate/seal/cleanup; fake/local, Kubernetes Kueue/JobSet and native-provider adapters.
- Acceptance: replay/crash/cancel/retry tests prove idempotent side effects, bounded budget and cleanup; Temporal cannot approve evidence/releases.

## RF-03 — Model and operator lab

- PyTorch/Transformers/safetensors model work, quantization/batching/cache experiments, Triton kernels where measured, deterministic quality/performance evaluators and negative-result sealing.
- Acceptance: Hypothesis tensor/operator properties, reference parity, scope-matched benchmarks and reproducible environment/artifact manifests.

## RF-04 — Runtime and qualification

- Language-neutral signed OCI/local protocol; cell-agent supervisor; quality, protocol, hardware, cache, load, failure, security, cost and cleanup qualification.
- Acceptance: candidate is production-ineligible until independent qualification digest covers exact bundle/runtime/hardware classes.

## RF-05 — Continuous factory and promotion

- Always-on bounded program selection from explicit hypotheses, portfolio derived views, agent leases through Temporal activities, challenger comparison, release proposal and operator approval.
- Acceptance: one end-to-end program records a negative result and qualified challenger without publishing; a second explicit approval publishes a canary alias and rollback.

## WP-09 — Grad aliases

- Publish sparse `grad/<effort>/<speed>` catalog beginning with `grad/medium/standard`; immutable releases, endpoints and deterministic canary aliases.
- Acceptance: exact identity/price/capability snapshot, no unpublished-combination fallback, rollback to prior release and trace/ledger attribution by digest.

## WP-10 — OpenRouter distribution

- Isolated channel credential/catalog/balance policy through the public gateway, exact Grad release, usage statement ingestion and shared-ledger receivable reconciliation.
- Acceptance: OpenRouter contract smoke, no customer-credit access, channel cache/trace isolation, statement-vs-usage equality and kill switch.

## WP-11 — Additional router harnesses

- Maintain tested configuration examples/packages for generic OpenAI-compatible routers. Build a native listing only when a signed customer/channel contract requires it.
- Acceptance: each harness has version-pinned docs, streaming/error/usage smoke and ownership/maintenance plan.

## WP-12 — Production hardening and launch

- Load/fault/security/DR tests, dashboards/runbooks/support flows, margin/cost evidence, accessibility/quickstart polish, production migrations and rollback.
- Acceptance: ledger/Valkey/tenant/release invariants, multi-AZ serving, Aurora/Valkey restore/failover, trace delete, provider cleanup, protected official-client CI and five-minute onboarding pass.

## Dependency graph

```text
WP-00 -> WP-01 -> WP-02 -> WP-03 -> WP-04 -> WP-05 -> WP-06
                                   |
                                   +-> WP-07 -> WP-08
RF-00 -> RF-01 -> RF-02 -> RF-03 -> RF-04 -> RF-05 -> WP-09
WP-09 + channel prerequisites -------------------------> WP-10 -> WP-11
all --------------------------------------------------------------> WP-12
```

The first deployable milestone is WP-00–04. Research can proceed in parallel after RF-00, but no research result enters customer traffic before WP-07/RF-04 qualification and Node release approval.

## Delegation rules

- One agent owns shared Protobuf/artifact/public protocol contracts at a time.
- Split provider drivers, UI pages and evaluators only after their interface freezes.
- Every package updates docs, migrations, fixtures, PBT replay commands and handoff.
- Failed provider/research/qualification outcomes are durable results, not reasons to weaken gates.
- Agents push scoped completed work directly to main after required checks; unrelated research work remains untouched.
