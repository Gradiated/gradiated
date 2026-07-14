# Task: 2026-07-14-research-factory-harness

## Outcome

A repository-native research harness can run one perpetual coordinator per model without making a chat session the source of truth. It converts scoped observations into a diverse scout portfolio, selects the cheapest faithful falsifier, fails closed before paid compute, safely owns and reuses retained allocations, classifies outcomes without contaminating scientific beliefs, projects one resumable state view, and updates the residual bottleneck after every valid result. The completed GLM-4.7 campaign is replayable as legacy evidence, and a deterministic synthetic campaign proves at least two autonomous discovery loops.

## Owner and coordination

- GitHub issue: https://github.com/joshsny/gradiated/issues/16
- GitHub project: not configured; issue is canonical
- owner: Codex
- Codex thread:
- created: 2026-07-14T14:16:56+00:00
- started: 2026-07-14T14:16:56+00:00
- last updated: 2026-07-14T18:00:00+00:00
- scope: research/factory,research/sol integration,.agents/skills/experiment-run
- excluded paths: live provider mutation, paid GPU work, credentials, model weights, customer traffic, production release/qualification, UI, Kubernetes, PostgreSQL, Temporal
- dependencies: Python standard library; existing Sol/GLM evidence as read-only replay input; experiment-run statistics/telemetry behavior selectively ported with provenance

## Contract

- hypothesis or user value: A small safety kernel plus a low-ceremony, telemetry-driven discovery loop will produce more valid scientific decisions per setup and broader opportunity coverage than the campaign-specific scripts, without imposing the production factory's process cost.
- acceptance checks: one synthetic campaign completes at least two observation-to-scout-to-run-to-residual loops; shortlist policy covers bottleneck-adjacent, cross-stack, model/representation, and adversarial families; invalid and operational outcomes do not update mechanism beliefs; scientific positive/negative/mixed outcomes do; paid admission rejects missing identities, controls, gates, budgets, deadlines, watchdogs, and cleanup contracts before mutation; SQLite leases/reservations/allocation adoption/cleanup survive restart; setup-affine arms reuse one retained session; GLM ledger replay preserves event count/spend/outcome classes and produces one generated state; CLI resume context is complete.
- quality gate: deterministic unit/property-style tests for domain invariants, SQLite restart/concurrency behavior, projection idempotence, portfolio diversity, fidelity promotion, legacy replay, and two-loop autonomy; no secrets in artifacts; `python3 tools/devex/check.py`; `git diff --check`.
- SLO or budget: zero paid compute and zero external provider mutation; synthetic acceptance campaign under 30 seconds; test suite under 60 seconds on the local host; prototype runtime has one Python process and no non-stdlib runtime dependency.
- timeout: individual tests and simulations must be bounded; implementation continues only while each slice improves paid-run safety, experiment throughput, option-space coverage, or scientific validity.
- artifact locations: `research/factory/` source/tests/docs/examples; generated test runtime only under temporary directories or `.agents/runtime/`; GLM source evidence remains under `research/sol/experiments/glm47flash/campaign_100/`.
- resume command: `PYTHONPATH=research/factory/src python3 -m unittest discover -s research/factory/tests -v`
- rollback or cleanup: remove the new `research/factory/` workstream and restore only explicitly archived Sol paths; tests use fake providers and temporary SQLite/artifact roots, and must leave no process, allocation, or database outside their temporary directory.

## Plan

1. Inventory reusable evidence and define the smallest canonical records and state transitions.
2. Implement append-only evidence, scout selection, paid admission, SQLite coordination, projection, legacy replay, and CLI/context generation.
3. Prove the loop with adversarial failure, restart, retained-session, GLM replay, and autonomous-campaign tests; simplify anything that does not improve the acceptance metrics.

## Result

- status: complete
- verification: 49 unit/integration tests pass, including two discovery loops, semantic evidence rejection, compact early-failure evidence, restart adoption, budget concurrency, fail-closed cleanup, GLM legacy replay, and resume safety; `python3 tools/devex/check.py`; `git diff --check`.
- changed paths: `research/factory/`, `research/README.md`, `research/sol/README.md`, `research/sol/CONTEXT_HANDOFF.md`, `docs/CONTEXT_INDEX.md`.
- limitations or blocked paths: no live provider adapter or paid run was exercised by design; provider create/delete implementations must honor the admitted idempotency key, exact tags, inventory reconciliation, and two-view absence check. Research runs only while a user-started Codex subscription session is active; there is no API-key LLM daemon.
- commit:
- next action: start a Codex session for GLM-4.7, run `grad_research bootstrap-glm47` once and `grad_research resume` on every start/transition, then execute the emitted dense-residual scouts and telemetry-debt probes.
