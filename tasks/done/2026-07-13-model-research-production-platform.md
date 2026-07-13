# Task: 2026-07-13-model-research-production-platform

## Outcome

The repository has an implementation-ready architecture for a continuously agent-operated model research factory that iterates across model weights/architecture, kernels/runtime, serving policy, topology and hardware mapping; produces one immutable deployable stack bundle; subjects it to a multi-fidelity, control-backed qualification pipeline; and promotes qualified releases behind stable family and effort/speed model IDs without changing in-flight identity or weakening production gates.

## Owner and coordination

- GitHub issue: https://github.com/joshsny/gradiated/issues/10
- GitHub project:
- owner: codex
- Codex thread:
- created: 2026-07-13T21:08:14+00:00
- started: 2026-07-13T21:08:14+00:00
- last updated: 2026-07-13T22:05:00+00:00
- scope: product/docs/MODEL_RESEARCH_TO_PRODUCTION_2026-07-13.md,docs/decisions/0007-research-production-model-lifecycle.md,product/docs/ARCHITECTURE.md,product/docs/API_AND_DATA_CONTRACTS.md,product/docs/DELIVERY_PLAN.md,product/docs/OWNED_INFERENCE_ARCHITECTURE.md,product/docs/MODEL_LANES_AND_MIGRATION.md,product/docs/TESTING_AND_CI.md,product/README.md,product/HANDOFF.md,tasks/active/2026-07-13-model-research-production-platform.md
- excluded paths: `research/sol/**`, `research/fable/**`, runtime/application implementation, credentials, model weights, paid GPU runs, live model promotion, capacity-provider/cloud mutation, customer traffic, unrelated worktree changes
- dependencies: Sol evidence/claim-composition/fidelity contracts; Fable functional-twin/model-surgery/engine/simulator lessons; ADR-0003/0005/0006; existing ModelOps, RouteRelease, inference cell and migration contracts

## Contract

- hypothesis or user value: A content-addressed full-stack serving bundle plus separate research-evidence and production-release state machines lets autonomous agents iterate quickly while production consumes only reproducible, scope-matched, signed candidates. Stable aliases can move safely only through immutable release heads, measured qualification, canary and rollback.
- acceptance checks: define research/control/product planes and agent ownership; define complete stack bundle and lineage/version schemas; reconcile Fable hypothesis generation with Sol fail-closed evidence admission; specify experiment isolation, datasets/evals, custom-runtime tests, supply-chain/security and full-cell qualification; define promotion/rollback/deprecation state machines; freeze stable family, generic effort/speed and immutable pin naming; define alias movement and customer disclosure; define CI/continuous-agent loops, work queues, artifact stores and reproducible commands; update canonical product architecture/contracts/testing/delivery/handoff.
- quality gate: internal architecture/evidence audit; current official primary sources for selected workflow/artifact/orchestration technologies where recommendations are time-sensitive; evidence labels and falsification rules; no transfer of Fable modeled claims into production evidence; local link resolution; `python3 tools/devex/check.py`; `git diff --check`; naming/authority/invariant searches.
- SLO or budget: planning only; zero external spend or mutations; no experiment/model promotion; no edits under active dirty research workstreams; research agents may propose automatically but production alias movement requires the documented policy and human authority until separately delegated.
- timeout: one working session; stop external research after the architecture can choose repository/artifact/workflow primitives without vendor lock-in.
- artifact locations: `product/docs/MODEL_RESEARCH_TO_PRODUCTION_2026-07-13.md`, `docs/decisions/0007-research-production-model-lifecycle.md`, canonical product docs in scope, and this packet.
- resume command: `git show --stat --oneline HEAD && sed -n '1,640p' product/docs/MODEL_RESEARCH_TO_PRODUCTION_2026-07-13.md && sed -n '1,260p' tasks/done/2026-07-13-model-research-production-platform.md`
- rollback or cleanup: revert the scoped documentation commit; no remote compute, model registry entries, aliases or deployment resources are created.

## Plan

1. Audit Sol, Fable and existing product ModelOps/release/naming contracts; identify reusable parts and contradictions.
2. Research current workflow/artifact/evaluation/orchestration primitives and choose a minimally coupled platform architecture.
3. Write the full research-to-production plan and ADR, update canonical contracts/testing/delivery/handoff, verify, commit and push only owned paths.

## Result

- status: done
- verification: `python3 tools/devex/check.py` passed; `git diff --check` passed; documentation link command passed; architecture naming/authority/invariant searches reviewed; no paid experiment, cloud mutation or model promotion performed.
- changed paths: `product/docs/MODEL_RESEARCH_TO_PRODUCTION_2026-07-13.md`, `docs/decisions/0007-research-production-model-lifecycle.md`, `product/docs/ARCHITECTURE.md`, `product/docs/API_AND_DATA_CONTRACTS.md`, `product/docs/DELIVERY_PLAN.md`, `product/docs/OWNED_INFERENCE_ARCHITECTURE.md`, `product/docs/MODEL_LANES_AND_MIGRATION.md`, `product/docs/TESTING_AND_CI.md`, `product/README.md`, `product/HANDOFF.md`, and this completed packet.
- limitations or blocked paths: architecture is implementation-ready but bundle cold-load/portability, Temporal operations, first custom-architecture parity tolerances, hidden-eval governance, pin economics, first-family envelope, canary statistics and provider placement envelopes remain explicitly preregistered measured spikes; active concurrent `research/sol/**` and unrelated untracked work were preserved and excluded.
- commit: completion commit on `main` (see Git history and issue #10).
- next action: delegate RF-00 with WP-00 to freeze Protobuf, canonical manifest, fake services, Temporal/local substrate and cross-language/PBT replay before parallel RF agents begin.
- released: 2026-07-13T21:23:04+00:00
