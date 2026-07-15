# Task: 2026-07-15-supervisor-campaign-objective

## Outcome

The GLM-4.7 campaign and lab instructions explicitly define progress as achieving the lowest sustainable quality-eligible $/token for background agents, cheaper than major providers, using GLM-4.7-specific telemetry and model/serving/hosting co-design including alternate and spot hardware.

## Owner and coordination

- GitHub issue: https://github.com/joshsny/gradiated/issues/18
- GitHub project:
- owner: codex-supervisor-objective
- Codex thread:
- created: 2026-07-15T08:52:34+00:00
- started: 2026-07-15T08:52:34+00:00
- last updated: 2026-07-15T08:52:34+00:00
- scope: .agents/skills/research-supervisor/SKILL.md,research/factory/src/grad_research/lab_harness.py,research/factory/tests/test_lab_harness.py,research/sol/experiments/glm47flash/research_lab/CAMPAIGN.md,tasks/active/2026-07-15-supervisor-campaign-objective.md
- excluded paths:
- dependencies:

## Contract

- hypothesis or user value: Explicitly binding the process supervisor to the campaign result will prevent generic infrastructure or process optimization from becoming a substitute for GLM-4.7 research progress.
- acceptance checks: Skill validation and focused harness tests pass; the live supervisor prompt contains the campaign-objective binding after a safe service reload.
- quality gate: Preserve model quality and a declared background-job completion/reliability envelope; latency is otherwise tradeable. Preserve the separation between scientific portfolio direction and process supervision while allowing the supervisor to flag drift.
- SLO or budget: Prompt-only behavior change, no provider spend, and no interruption of active experiments.
- timeout: 20 minutes.
- artifact locations: `research_lab/CAMPAIGN.md`, `.agents/skills/research-supervisor/SKILL.md`, and the harness supervisor prompt.
- resume command: `systemctl --user status gradiated-research-lab@glm47.service --no-pager`
- rollback or cleanup: Revert the scoped wording; no external cleanup required.

## Plan

1. Compare the campaign objective with the supervisor skill and live prompt.
2. Make the model-specific co-design result the explicit definition of progress.
3. Validate and reload without disrupting active work.

## Result

- status: complete
- verification: `python3 tools/devex/validate_skills.py`; `PYTHONPATH=research/factory/src python3 -m unittest research/factory/tests/test_lab_harness.py -v` (4 passed); `python3 tools/devex/check.py`; service safely restarted after the active instance canary reached a terminal pass and clean inventory.
- changed paths: `.agents/skills/research-supervisor/SKILL.md`, `research/factory/src/grad_research/lab_harness.py`, `research/factory/tests/test_lab_harness.py`, `research/sol/experiments/glm47flash/research_lab/CAMPAIGN.md`.
- limitations or blocked paths: The supervisor remains a process supervisor and flags portfolio drift rather than directly choosing experiments; the Sol director owns scientific allocation.
- commit:
- next action: On the next scheduled supervisor turn, confirm it assesses throughput against the GLM-4.7 quality/background-reliability/cost result rather than generic process metrics.
