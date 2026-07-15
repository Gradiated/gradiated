# Task: 2026-07-15-research-progress-focus

## Outcome

The live research lab's role skills and prompts explicitly optimize for decision-relevant evidence per wall-clock hour, discourage documentation and repeated validation as ends in themselves, and tell agents to pivot when a route becomes a rabbit hole. Parallel researcher slots use both Terra and Luna so temporary capacity on one model does not discard the other slot.

## Owner and coordination

- GitHub issue: https://github.com/joshsny/gradiated/issues/18
- GitHub project:
- owner: codex-progress-focus
- Codex thread:
- created: 2026-07-15T08:28:13+00:00
- started: 2026-07-15T08:28:13+00:00
- last updated: 2026-07-15T08:28:13+00:00
- scope: .agents/skills/research-director/SKILL.md,.agents/skills/researcher/SKILL.md,.agents/skills/research-supervisor/SKILL.md,research/factory/src/grad_research/lab_harness.py,research/factory/tests/test_lab_harness.py,tasks/active/2026-07-15-research-progress-focus.md
- excluded paths:
- dependencies:

## Contract

- hypothesis or user value: Clear progress-first role objectives will reduce busywork and shorten the time between meaningful experiments without adding deterministic process machinery.
- acceptance checks: Skill validation, focused lab-harness tests, and repository DevEx checks pass; Terra/Luna researcher routing is covered; the live service remains healthy.
- quality gate: Instructions preserve evidence, observability, bounded paid-resource safety, and researcher autonomy while making documentation subordinate to experiments and decisions.
- SLO or budget: No provider spend and no interruption of active researchers; complete this focused change in one turn.
- timeout: 30 minutes.
- artifact locations: `.agents/skills/research-{director,researcher,research-supervisor}/SKILL.md`, `research/factory/src/grad_research/lab_harness.py`.
- resume command: `systemctl --user status gradiated-research-lab@glm47.service --no-pager`
- rollback or cleanup: Revert only the scoped prompt/skill edits; no runtime cleanup expected.

## Plan

1. Inspect live traces, project status, and experiment cadence.
2. Simplify and strengthen role instructions around research progress and pivots.
3. Route parallel researchers across Terra and Luna instead of wasting a slot on repeated model-capacity failures.
4. Verify the focused harness behavior and live service health.

## Result

- status: complete
- verification: `python3 tools/devex/validate_skills.py`; `PYTHONPATH=research/factory/src python3 -m unittest research/factory/tests/test_lab_harness.py -v` (4 passed); `python3 tools/devex/check.py`; live Luna smoke returned `LUNA_OK`; restarted service launched concurrent Terra and Luna researchers with the revised prompts.
- changed paths: `.agents/skills/research-director/SKILL.md`, `.agents/skills/researcher/SKILL.md`, `.agents/skills/research-supervisor/SKILL.md`, `research/factory/src/grad_research/lab_harness.py`, `research/factory/tests/test_lab_harness.py`, `/root/.config/gradiated/research-lab/glm47.json` (host-local runtime config).
- limitations or blocked paths: The current GLM-4.7 campaign still has no new successful performance result after V31; the durable controller proof now passed and a cheap real deletion canary is active. Host-local config is intentionally outside version control.
- commit:
- next action: Observe whether the canary completes and the next paid experiment reaches GPU execution; compare experiment cadence on the next daily review.
