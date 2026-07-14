# Product delivery plan

> This file defines product milestone outcomes, not claimable packet IDs. [The complete work package catalog](../../docs/implementation/WORK_PACKAGES.md) and [path registry](../../docs/implementation/PATH_OWNERSHIP.md) are the canonical dependency, ownership and subagent acceptance plan. The `P*`/`R*` labels below are roadmap groupings only.

Packages are ordered to earn revenue before owned inference breadth. Each package has one contract owner, deterministic examples, property tests for invariants and an agent-runnable handoff. No package may add derived durable state or speculative optionality without a concrete consumer.

## P0 — Repository, contracts and `grad`

- Create pnpm/Rust/Python workspaces, Vite/Hono REST skeleton, Rust gateway workspace, research package and transparent Rust CLI.
- Add the described-Zod route registry, OpenAPI 3.1/TypeScript-client/agent-doc generation, MCP allowlist generator, Buf/Prost hot contracts, artifact schemas and generated-drift CI.
- Add Vitest/fast-check, nextest/proptest, pytest/Hypothesis, Testcontainers/fakes and replay artifacts.
- Acceptance: `grad start`, bounded verify and fake E2E run unattended in CI; generated diff is empty.

## P1 — Organization, workspace and identity

- Better Auth identity/session/recovery/OAuth; organization/default-workspace creation; org/workspace membership; invitations; role checks; audit; self-service organization deletion workflow.
- Vite/shadcn shell with organization/workspace URL state and accessibility baseline.
- Acceptance: transaction/PBT proves exactly one Default workspace, no cross-tenant membership/key access, retry-safe signup/invite acceptance and deletion request/cancel/drain/refund/purge under crashes.

## P2 — Ledger, top-ups and limits

- Fixed USD chart, double-entry transactions/entries, organization balance projection, top-up intents, Stripe checkout/webhooks, monthly workspace/key limits.
- No workspace wallets or arbitrary period model.
- Acceptance: model-based PBT proves balanced/idempotent top-up/refund/chargeback/correction and balance rebuild equality under duplicates/reordering/crashes.

## P3 — Valkey projection and admission

- Versioned key/policy/catalog/price/balance snapshots; atomic auth/reserve/concurrency/low-balance cap/settle/refund; protected billing stream; rebuild/reconciliation.
- Acceptance: Rust state-machine PBT plus real Valkey proves no overspend within reservation policy, no leaked concurrency, fail-closed uncertainty and convergence after duplicate/out-of-order operations.

## P4 — First paid direct-model slice

- OpenAI Responses Create, Anthropic Messages and Models surfaces, OpenAI/Anthropic direct adapters, streaming, canonical errors/usage, usage posting and quickstarts.
- Acceptance: official OpenAI and Anthropic clients plus fake/real cheapest-model tests cover funded success, tool cycles, structured output where qualified, insufficient balance, cancel, timeout, provider errors and exact settlement; unsupported fields spend nothing and no parameter/model changes silently.

## P5 — Curated providers and gateway recipes

- Add providers only from demand: Google and additional OpenAI/Anthropic models are candidates; capability checks, provider endpoint health and explicit eligible failover.
- Defer Chat Completions, Embeddings, Google GenerateContent and hosted-product APIs until demonstrated demand.
- Publish generic integration recipes for OpenAI SDK, LiteLLM, Cloudflare AI Gateway, Portkey and Helicone based on current documented interfaces.
- Acceptance: protocol conformance/golden/PBT and official clients; adapter cannot accept a capability it cannot preserve.

## P6 — Traces and PostgreSQL intelligence

- Public-key trace encryption, bounded trace stream, S3 custody, PostgreSQL registry/grants/tombstones, default retention/no-retention, trace-access and bounded indexed list/chart/workload queries.
- Add recommendations with replay/shadow/canary evidence and explicit approval; no auto-switch.
- Acceptance: no-retention emits no payload; credentials never persist; tenant isolation/delete/export/retention PBT; trace failure cannot starve billing; measured queries meet seed SLO or receive a narrow PostgreSQL rollup.

## P7 — Owned inference substrate

- Inference router, cell-agent/runtime local protocol, signed bundle/runtime/topology verification, exact-release health, tenant-salted always-on KV cache, SQL capacity sources/targets/allocations/members/cells, coordinator/worker one-use joins, CSR certificate enrollment and fake provider/cell/CA.
- Support one- and multi-node cells behind the same gateway/router contract. Multi-node loss fences the whole cell; no elastic repair or cross-provider topology.
- Acceptance: serving/fleet state-machine PBT, two-node CPU harness, cache isolation, exact-release/topology routing, bootstrap/join replay denial, certificate rotation/expiry, partial acquire/member loss, pre/post-output interruption, lease fencing, uncertain cleanup freeze and zero provider lifecycle/CA issuance calls in serving path.

## P8 — First external GPU provider

- One native Rust provider driver with tag/idempotency/observe/drain/release/list-owned; paid bounded qualification on one hardware/runtime class.
- Acceptance: fake conformance plus real single-node and smallest meaningful two-node startup/collective/stream/cache/member-loss/preemption/cleanup evidence and zero orphans.

## R0 — Research foundations

- Python/TS/Rust research API refs, compositional artifact/bundle/qualification schemas, local tiny-model fixtures and S3/ECR CAS/signing.
- Acceptance: canonical digest/signature and cross-language fixture equality.

## R1 — Research domain and API

- Python sole-writer API for program, hypothesis, campaign, experiment spec/run, evidence, bundle and qualification state; Hono BFF/operator UI.
- Acceptance: Hypothesis state models prove authority/version/budget/provenance transitions and immutable sealed evidence.

## R2 — Temporal execution

- Deterministic workflows/activities for plan/run/evaluate/seal/cleanup; fake/local, Kubernetes Kueue/JobSet and native-provider adapters.
- Acceptance: replay/crash/cancel/retry tests prove idempotent side effects, bounded budget and cleanup; Temporal cannot approve evidence/releases.

## R3 — Model and operator lab

- PyTorch/Transformers/safetensors model work, quantization/batching/cache experiments, Triton kernels where measured, deterministic quality/performance evaluators and negative-result sealing.
- Acceptance: Hypothesis tensor/operator properties, reference parity, scope-matched benchmarks and reproducible environment/artifact manifests.

## R4 — Runtime and qualification

- Language-neutral signed OCI/local protocol and exact topology; cell-agent supervisor; quality, protocol, hardware/fabric, cache, load, member/failure, security, cost and cleanup qualification.
- Acceptance: candidate is production-ineligible until independent qualification digest covers exact bundle/runtime/single-or-multi-node topology and hardware/fabric classes.

## R5 — Continuous factory and promotion

- Always-on bounded program selection from explicit hypotheses, portfolio derived views, agent leases through Temporal activities, challenger comparison, release proposal and operator approval.
- Acceptance: one end-to-end program records a negative result and qualified challenger without publishing; a second explicit approval publishes a canary alias and rollback.

## P9 — Grad aliases

- Publish sparse `grad/<effort>/<speed>` catalog beginning with `grad/medium/standard`; immutable releases, endpoints and deterministic canary aliases.
- Acceptance: exact identity/price/capability snapshot, no unpublished-combination fallback, rollback to prior release and trace/ledger attribution by digest.

## P10 — OpenRouter distribution

- Isolated channel credential/catalog/balance policy through the public gateway, exact Grad release, usage statement ingestion and shared-ledger receivable reconciliation.
- Acceptance: OpenRouter contract smoke, no customer-credit access, channel cache/trace isolation, statement-vs-usage equality and kill switch.

## P11 — Additional router harnesses

- Maintain tested configuration examples/packages for generic OpenAI-compatible routers. Build a native listing only when a signed customer/channel contract requires it.
- Acceptance: each harness has version-pinned docs, streaming/error/usage smoke and ownership/maintenance plan.

## P12 — Production hardening and launch

- Load/fault/security/DR tests, dashboards/runbooks/support flows, margin/cost evidence, accessibility/quickstart polish, production migrations and rollback.
- Acceptance: ledger/Valkey/tenant/release invariants, multi-AZ serving, Aurora/Valkey restore/failover, trace delete, provider cleanup, protected official-client CI and five-minute onboarding pass.
- Public owned-inference launch additionally requires one qualified single-node and one qualified multi-node topology through the same cell contract.

## Dependency graph

```text
P0 -> P1 -> P2 -> P3 -> P4 -> P5 -> P6
                                   |
                                   +-> P7 -> P8
R0 -> R1 -> R2 -> R3 -> R4 -> R5 -> P9
P9 + channel prerequisites ----------------------------> P10 -> P11
all -------------------------------------------------------------> P12
```

The first deployable milestone is P0–P4. Research can proceed in parallel after R0, but no research result enters customer traffic before P7/R4 qualification and Node release approval. Actual implementation order and issue IDs always come from canonical waves W0–W9 and their named packets.

## Delegation rules

- One agent owns shared Protobuf/artifact/public protocol contracts at a time.
- Split provider drivers, UI pages and evaluators only after their interface freezes.
- Every package updates docs, migrations, fixtures, PBT replay commands and handoff.
- Failed provider/research/qualification outcomes are durable results, not reasons to weaken gates.
- Agents push scoped completed work directly to main after required checks; unrelated research work remains untouched.
