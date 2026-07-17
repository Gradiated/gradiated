# Task: 2026-07-15-shared-gpu-price-inventory

## Outcome

All research agents share one weekly refreshed GPU price inventory. Production estimates use realistic medium-term committed rates and ranges, while experiment spend retains actual metered rates.

## Owner and coordination

- GitHub issue: https://github.com/joshsny/gradiated/issues/21
- GitHub project:
- owner: codex
- Codex thread:
- created: 2026-07-15T13:16:04+00:00
- started: 2026-07-15T13:16:04+00:00
- last updated: 2026-07-15T13:16:04+00:00
- scope: research/factory/data/gpu_prices.json,research/factory/src/grad_research/gpu_prices.py,research/factory/src/grad_research/cli.py,research/factory/tests/test_gpu_prices.py,research/factory/README.md,research/factory/tools/README.md,.agents/skills/research-director/SKILL.md,.agents/skills/researcher/SKILL.md,research/sol/experiments/glm47flash/research_lab/CAMPAIGN.md,research/sol/experiments/glm47flash/research_lab/projects/aa_methodology_matched_awq_session/PROJECT.md,research/sol/docs/GLM52_DIRECT_PIVOT_DECISION_2026-07-15.md
- excluded paths:
- dependencies:

## Contract

- hypothesis or user value: One canonical inventory eliminates repeated market research and prevents on-demand or spot rates from becoming production headline assumptions.
- acceptance checks: machine-readable rates and sources; actual experiment versus committed production separation; seven-day freshness; stale fail signal; documented weekly owner; director/researcher reuse instructions.
- quality gate: planning rates remain inside labeled evidence ranges and are derived for 12–24 month, 8–64 GPU non-preemptible commitments.
- SLO or budget: zero provider spend; no network operation in tests.
- timeout: one implementation turn.
- artifact locations: `research/factory/data/gpu_prices.json` and `research/factory/src/grad_research/gpu_prices.py`.
- resume command: `PYTHONPATH=research/factory/src python3 -m grad_research gpu-prices --require-fresh`.
- rollback or cleanup: remove the inventory command/data and skill references; no external resources.

## Plan

1. Define and validate the shared inventory and medium-term planning policy.
2. Expose a query/freshness command and tests.
3. Route directors, researchers, and the active campaign to the shared source.

## Result

- status: complete
- verification: 3 focused GPU-price tests pass; fresh/stale CLI behavior passes; `python3 tools/devex/check.py` passes; `git diff --check` passes. Full factory suite ran 66 tests with 64 passing and two unrelated live-legacy expectation failures in `test_legacy_and_demo` and `test_sol_glm47`.
- changed paths: shared inventory/module/CLI/test/docs; director and researcher skills; GLM campaign, AA project, and pivot decision economics.
- limitations or blocked paths: rates are planning estimates until matching written quotes exist; TensorWave has no public committed quote. Weekly refresh remains a director-delegated agent task rather than brittle deterministic web scraping.
- commit: not created; the shared live-factory worktree contains unrelated concurrent changes.
- next action: refresh the inventory after seven days or sooner when a written provider quote arrives; add missing accelerators only when a campaign needs them.
