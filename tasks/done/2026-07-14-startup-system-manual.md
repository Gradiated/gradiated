# Task: 2026-07-14-startup-system-manual

## Outcome

The repository contains a canonical, build-grade manual for the entire startup. Every product and infrastructure subsystem has explicit ownership, contracts, persistence, failure semantics, security boundaries, tests, dependencies, rollout and acceptance gates. A dependency-safe parallel plan lets junior agents implement the system without making architectural decisions.

## Owner and coordination

- GitHub issue: 17
- GitHub project:
- owner: codex
- Codex thread:
- created: 2026-07-14T15:00:01+00:00
- started: 2026-07-14T15:00:01+00:00
- last updated: 2026-07-14T15:00:01+00:00
- scope: docs/**, product/AGENTS.md, product/docs/**, infra/docs/**, product/HANDOFF.md, product/README.md, infra/HANDOFF.md, infra/README.md; excludes research/factory/** and active research tasks
- excluded paths: research/factory/**, research/sol/**, research/fable/**, tasks/active/2026-07-14-research-factory-harness.md, and all unrelated worktree changes
- dependencies: accepted ADRs 0001-0009 and the active research-factory implementation contract; this documentation may reference but must not rewrite active implementation artifacts

## Contract

- hypothesis or user value: a precise, single-source system manual and packet graph will let multiple lower-capability agents build the startup in parallel with less integration rework and no hidden architectural choices
- acceptance checks: all coverage rows have an owner, input/output contract, state owner, failure behavior, security rule, tests and dependency packet; all Mermaid blocks parse structurally; links resolve; stale terminology and known contradictions are absent
- quality gate: root DevEx check, Markdown link/path audit, Mermaid fence audit, terminology/contract searches, diff check and an independent completeness review of the owned diff
- SLO or budget: documentation-only; no paid services; no edits to active research implementation; prefer one canonical definition with links over duplicated prose
- timeout: one working session with periodic progress updates
- artifact locations: docs/SYSTEM_MANUAL.md, docs/diagrams/**, docs/implementation/**, docs/IMPLEMENTATION_COVERAGE.md, product/docs/** and infra/docs/** indexes/handoffs
- resume command: python3 tools/devex/start.py && sed -n '1,260p' tasks/active/2026-07-14-startup-system-manual.md
- rollback or cleanup: revert only issue 17 documentation commits; release the local claim; no runtime or cloud state is changed

## Plan

1. Inventory every existing architecture, contract, ADR and active workstream; record gaps and contradictions.
2. Define the canonical end-to-end system, package boundaries, data/contracts and failure semantics.
3. Write the system manual, Mermaid diagram set and dependency-safe implementation packet catalog.
4. Reconcile existing indexes, coverage, delivery and handoff documents to the canonical manual.
5. Run quality gates, review the complete owned diff, commit/push directly to main and close issue 17.

## Result

- status: complete
- verification: `python3 tools/devex/check.py`; `git diff --check`; 81-file local Markdown link and heading-anchor audit; 24-block Mermaid structural audit; 71 work-package/dependency/path-row parity audit; current-blueprint terminology/state/authority contradiction searches
- changed paths: canonical manuals and ADR/index reconciliation under `docs/**`; current product architecture/handoff/instructions under `product/AGENTS.md`, `product/README.md`, `product/HANDOFF.md`, `product/docs/**`; current AWS/platform handoff and blueprints under `infra/README.md`, `infra/HANDOFF.md`, `infra/docs/**`; this completed task packet
- limitations or blocked paths: no product/cloud runtime was built or mutated; provider economics, exact SLOs, jurisdiction/tax treatment, OpenRouter acceptance and GPU/model qualification intentionally remain measured or human launch gates with safe fallbacks; unrelated active research-factory and Sol changes were preserved
- commit: this documentation commit; canonical history is `main`
- next action: create one issue per unblocked W0 packet, claim exact roots from `docs/implementation/PATH_OWNERSHIP.md`, and assign one integrator for generated/shared files
