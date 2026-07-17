# Task: 2026-07-15-glm52-direct-pivot

## Outcome

A durable decision will state when to graduate GLM-4.7-Flash to GLM-5.2, quantify the current exact-variant Artificial Analysis gap, and bind the lab to methodology-matched external benchmarking without adding orchestration complexity.

## Owner and coordination

- GitHub issue: https://github.com/joshsny/gradiated/issues/20
- GitHub project:
- owner: codex
- Codex thread:
- created: 2026-07-15T12:54:25+00:00
- started: 2026-07-15T12:54:25+00:00
- last updated: 2026-07-15T12:54:25+00:00
- scope: research/sol/docs/GLM52_DIRECT_PIVOT_DECISION_2026-07-15.md, research/sol/experiments/glm47flash/research_lab/CAMPAIGN.md
- excluded paths:
- dependencies:

## Contract

- hypothesis or user value: A bounded GLM-4.7-Flash graduation phase lowers the chance of wasting expensive GLM-5.2 nodes while avoiding an open-ended prototype campaign.
- acceptance checks: exact reasoning/model variant is identified; AA pricing and speed denominators are normalized; current measured gap and uncertainty are explicit; GLM-5.2 graduation gates are durable.
- quality gate: claims distinguish measured, derived, external, and unmatched evidence; no quality-equivalent provider win is claimed before the active quality gate closes.
- SLO or budget: $0; no provider mutation or live-campaign ownership changes.
- timeout: one decision turn.
- artifact locations: research/sol/docs/GLM52_DIRECT_PIVOT_DECISION_2026-07-15.md and the campaign comparator section.
- resume command: read the decision brief and current lab STATUS.md.
- rollback or cleanup: documentation-only; no external resources created.

## Plan

1. Reconcile exact Artificial Analysis model/reasoning pages and methodology.
2. Compare the current measured GLM-4.7-Flash frontier on valid denominators.
3. Record the bounded graduation decision and minimal GLM-5.2 stack requirements.

## Result

- status: complete
- verification: `python3 tools/devex/check.py`; `git diff --check`
- changed paths: `research/sol/docs/GLM52_DIRECT_PIVOT_DECISION_2026-07-15.md`, `research/sol/experiments/glm47flash/research_lab/CAMPAIGN.md`
- limitations or blocked paths: Artificial Analysis's rolling performance prompts are private, so a methodology-matched reproduction can be built but not an exact prompt replay. The measured frontier remains quality-ineligible until the active calibration closes.
- commit: not created; the shared worktree contains unrelated live-factory work.
- next action: finish the active quality capture, run the AA serverless/SLT profiles on a retained allocation, then graduate scientific work to GLM-5.2.
