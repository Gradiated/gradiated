# Task: 2026-07-14-python-first-research-factory

## Outcome

The product architecture treats Fable and Sol as spike evidence rather than implementation dependencies and defines a Python-first, always-on research lab with explicit Rust and TypeScript boundaries. Every funded model has a durable baseline, champion, Pareto frontier, negative-result memory and ranked experiment queue. Agents can continuously investigate the whole inference stack while GPU work remains bounded; the factory can qualify Python-backed or native runtimes without forcing premature Rust rewrites; and production still launches one exact signed `ModelStackBundle` through the Rust cell boundary.

## Owner and coordination

- GitHub issue: https://github.com/joshsny/gradiated/issues/12
- GitHub project:
- owner: codex
- Codex thread:
- created: 2026-07-13T22:24:59+00:00
- started: 2026-07-13T22:24:59+00:00
- last updated: 2026-07-13T22:24:59+00:00
- scope: product/docs/MODEL_RESEARCH_TO_PRODUCTION_2026-07-13.md,product/docs/ARCHITECTURE.md,product/docs/API_AND_DATA_CONTRACTS.md,product/docs/DELIVERY_PLAN.md,product/docs/TESTING_AND_CI.md,product/README.md,product/HANDOFF.md,docs/decisions/0007-research-production-model-lifecycle.md,tasks/active/2026-07-14-python-first-research-factory.md
- excluded paths: `research/fable/**`, `research/sol/**`, runtime/application implementation, cloud/provider mutation, paid GPU work, credentials, model weights, customer traffic and unrelated worktree changes
- dependencies: ADR-0007; existing `ModelStackBundle`, `RouteRelease`, gateway/edge/cell and provider-adapter contracts; Fable/Sol reports as non-authoritative spike evidence; current official PyTorch/Triton/Temporal/vLLM extension documentation

## Contract

- hypothesis or user value: Python/PyTorch/Triton minimizes iteration latency for model and kernel research, while a language-neutral bundle/operator contract and Rust launch/serving boundary preserve production reliability. Treating spikes as evidence to mine rather than frameworks to integrate removes accidental architecture lock-in.
- acceptance checks: freeze language ownership; define Python research SDK/service/Temporal worker and repository layout; define model/checkpoint/operator/runtime contracts; define Python-to-Rust runtime modes and graduation ladder; replace Fable/Sol adapter dependencies with selective port/archive rules; update testing/PBT/CI and RF work packages; preserve exact-bundle qualification and gateway invariants.
- quality gate: primary official sources for current PyTorch custom-op/compiler, Triton, Temporal Python and vLLM extension behavior; evidence labels and falsification; `python3 tools/devex/check.py`; `git diff --check`; naming/dependency consistency search; no edits or staging under dirty research workstreams.
- SLO or budget: documentation-only, zero spend and no external infrastructure/model mutation; complete in one working session.
- timeout: stop external research once language/runtime boundaries and testable package contracts are supported by primary documentation.
- artifact locations: scoped architecture/ADR/delivery/testing/handoff documents and this packet.
- resume command: `git diff -- product/docs/MODEL_RESEARCH_TO_PRODUCTION_2026-07-13.md product/docs/ARCHITECTURE.md product/docs/API_AND_DATA_CONTRACTS.md product/docs/DELIVERY_PLAN.md product/docs/TESTING_AND_CI.md product/README.md product/HANDOFF.md docs/decisions/0007-research-production-model-lifecycle.md tasks/active/2026-07-14-python-first-research-factory.md`
- rollback or cleanup: revert the scoped documentation commit; no runtime resources or research artifacts are created.

## Plan

1. Audit the existing spike-derived plan and select language/runtime boundaries from current primary documentation.
2. Redesign the factory packages, experiment loop, operator/runtime promotion ladder, testing and agent delegation without modifying Fable/Sol.
3. Verify, commit and push only owned documentation, close issue #12 and report any unrelated CI failure separately.

## Result

- status: done
- verification: `python3 tools/devex/check.py`; `git diff --check`; relative Markdown link validation across all nine scoped files; stale spike/package dependency search.
- changed paths: `product/docs/MODEL_RESEARCH_TO_PRODUCTION_2026-07-13.md`, `product/docs/ARCHITECTURE.md`, `product/docs/API_AND_DATA_CONTRACTS.md`, `product/docs/DELIVERY_PLAN.md`, `product/docs/TESTING_AND_CI.md`, `product/README.md`, `product/HANDOFF.md`, `docs/decisions/0007-research-production-model-lifecycle.md`, and this packet moved to `tasks/done/` on release.
- limitations or blocked paths: architecture/documentation only; no factory code, paid GPU validation or cloud/runtime mutation was in scope. Runtime-mode overhead, operator portability and unattended portfolio value remain explicit measured spikes before production authority expands. Dirty concurrent `research/sol/**` work and handoffs were not touched or staged.
- commit: this documentation commit.
- next action: delegate RF-00 contracts/local substrate, then RF-01 through RF-05 in the dependency order documented in the delivery plan.
- released: 2026-07-13T22:35:45+00:00
