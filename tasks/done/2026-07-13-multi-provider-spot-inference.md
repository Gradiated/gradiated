# Task: 2026-07-13-multi-provider-spot-inference

## Outcome

The repository contains a source-backed, implementation-ready architecture for serving owned Grad models on pooled external GPU capacity, including spot lifecycle, cell orchestration, gateway contracts, always-on KV cache, failure handling, security, testing, and phased delivery.

## Owner and coordination

- GitHub issue: https://github.com/joshsny/gradiated/issues/7
- GitHub project:
- owner: codex
- Codex thread:
- created: 2026-07-13T19:23:41+00:00
- started: 2026-07-13T19:23:41+00:00
- last updated: 2026-07-13T19:23:41+00:00
- scope: product/docs, product/README.md, product/HANDOFF.md, product/AGENTS.md, infra/docs, infra/README.md, docs/ARCHITECTURE.md, docs/decisions/0005-multi-provider-spot-inference.md, tasks/active/2026-07-13-multi-provider-spot-inference.md
- excluded paths: research/**, application/runtime code, credentials, provider account mutation, paid capacity, Terraform/Helm implementation, unrelated worktree changes
- dependencies: product and infrastructure architecture merged in PR #5; direct-to-main workflow in `c633cfa`

## Contract

- hypothesis or user value: a cell-local orchestration model with a thin AWS capacity broker can pool heterogeneous spot supply without putting provider APIs, Kubernetes discovery, or financial state on the request path.
- acceptance checks: freeze AWS/external-plane boundaries; define gateway-to-cell Protobuf and route-release behavior; define provider adapters, scheduling, spot draining, cache isolation, failure semantics, cost guardrails, security, PBT/E2E coverage, and phased implementation tasks; adapt existing product/infra docs.
- quality gate: current primary-source evidence with uncertainty labels; no unsupported vendor guarantee; `python3 tools/devex/check.py`; `git diff --check`; local Markdown link validation; terminology/invariant search.
- SLO or budget: planning/research only, zero provider spend and zero cloud mutation; target design supports exact-release routing, no cross-tenant cache reuse, and no control-plane dependency on the live request path.
- timeout: one working session; stop browsing after enough primary evidence exists to choose the abstraction and label provider-specific unknowns for implementation spikes.
- artifact locations: `product/docs/OWNED_INFERENCE_ARCHITECTURE.md`, `infra/docs/MULTI_PROVIDER_GPU_FLEET.md`, `docs/decisions/0005-multi-provider-spot-inference.md`, adaptations in the declared scope, and this packet.
- resume command: `git diff -- product infra/docs docs/ARCHITECTURE.md docs/decisions/0005-multi-provider-spot-inference.md tasks/active/2026-07-13-multi-provider-spot-inference.md`
- rollback or cleanup: revert the scoped documentation commit; no external resources are created.

## Plan

1. Inspect the merged architecture and gather current primary evidence on multi-cluster orchestration, GPU runtimes/cache behavior, and representative provider APIs/interruption models.
2. Decide the fleet abstraction and freeze contracts, state ownership, lifecycle, security, failure, cache, and scheduling semantics in architecture/ADR documents.
3. Adapt product and infrastructure plans, add implementation work packages and verification, run checks, and publish the owned docs directly to `main`.

## Result

- status: done
- verification: current primary-source decision brief completed; `python3 tools/devex/check.py` passed; `git diff --check` passed; local Markdown links valid across 49 product/infra/architecture files; invariant searches found no direct gateway/provider-lifecycle dependency or cache-disable contradiction.
- changed paths: new `product/docs/OWNED_INFERENCE_ARCHITECTURE.md`, `product/docs/MULTI_PROVIDER_GPU_EVIDENCE_2026-07-13.md`, `infra/docs/MULTI_PROVIDER_GPU_FLEET.md`, and `docs/decisions/0005-multi-provider-spot-inference.md`; adaptations across declared product/infra/root architecture and delivery/handoff documents; this packet.
- limitations or blocked paths: no provider capacity, account, pricing, contract/DPA, network, edge latency, cache teardown, interruption frequency, or successful-token economics was measured; every provider/release remains qualification-gated. No application or infrastructure code exists yet.
- commit: pending direct-to-main architecture commit; exact SHA will be recorded after commit.
- next action: delegate product WP-00 plus fleet F-00 contracts/simulator and infrastructure I-00 foundations; run paid provider spikes only after provider/security/budget authority.
- released: 2026-07-13T19:41:04+00:00
