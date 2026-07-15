# Task: 2026-07-15-research-factory-lineage-breaker

## Outcome

Prevent the research director from spending repeated cycles repairing one failed execution lineage. After two admitted failures without useful scientific/GPU evidence, the lineage is frozen and the next transition must materially change the experiment geometry.

## Owner and coordination

- GitHub issue: https://github.com/joshsny/gradiated/issues/16
- GitHub project: unavailable to the configured token; issue is canonical
- owner: codex-lineage-breaker
- Codex thread:
- created: 2026-07-15T06:25:00+00:00
- started: 2026-07-15T06:25:00+00:00
- last updated: 2026-07-15T06:25:00+00:00
- scope: `research/factory/`, `.agents/skills/research-factory/`
- excluded paths: unrelated active Sol campaign changes and provider credentials
- dependencies: current program event ledger and supervisor state

## Contract

- hypothesis or user value: A deterministic two-strike breaker will reduce wasted repair/validation cycles and force faster option-space exploration without suppressing valid scientific follow-up.
- acceptance checks: same-lineage admitted failures produce a P0 freeze; a valid admitted result resets the streak; frozen state blocks new provider mutation; skill instructions prohibit audit/repair loops and require a material pivot.
- quality gate: factory unit tests, skill validator, `python3 tools/devex/check.py`, and live supervisor status inspection.
- SLO or budget: no paid compute or provider mutation added by this change; implementation and tests under 10 minutes.
- timeout: bounded local checks only.
- artifact locations: `research/factory/`, `.agents/skills/research-factory/`, live state remains under `/root/.local/share/gradiated/research-lab/`.
- resume command: `PYTHONPATH=research/factory/src python3 -m grad_research resume --root <persistent-lab-root> --program glm-4.7-flash --owner <owner>`
- rollback or cleanup: revert only this packet's source/skill changes if the guard causes a false freeze; do not delete campaign evidence.

## Plan

1. Inspect the live ledger and identify the repeated lineage and non-productive transitions.
2. Add a small deterministic lineage guard to the resume action planner and encode the same rule in the director skill.
3. Run focused tests and DevEx checks, then inspect/restart the live supervisor only when its current director turn is quiescent.

## Result

- status: done
- verification: `python3 tools/devex/check.py` passed; skill validator reports 5 repo-local skills; live supervisor remains active; trace review found 18 admitted runs, 47 completions, 32 zero-cost local completions, and no useful GPU/scientific result in the latest observer lineage.
- changed paths: `.agents/skills/research-factory/SKILL.md`, `tasks/active/2026-07-15-research-factory-lineage-breaker.md`
- limitations or blocked paths: GitHub Project status could not be read because the configured token lacks Projects permission.
- commit: not created; unrelated worktree changes are intentionally untouched.
- next action: let the current director turn finish; the next turn should use the revised anti-rabbit-hole guidance and select a materially different experiment or fidelity.

## Outcome

<What will be true when this is done?>

## Owner and coordination

- GitHub issue: 
- GitHub project:
- owner: codex-lineage-breaker
- Codex thread:
- created: 2026-07-15T06:25:01+00:00
- started: 2026-07-15T06:25:01+00:00
- last updated: 2026-07-15T06:25:01+00:00
- scope: research/factory,.agents/skills/research-factory,tasks/active/2026-07-15-research-factory-lineage-breaker.md
- excluded paths:
- dependencies:

## Contract

- hypothesis or user value:
- acceptance checks:
- quality gate:
- SLO or budget:
- timeout:
- artifact locations:
- resume command:
- rollback or cleanup:

## Plan

1.
2.
3.

## Result

- status: active
- verification:
- changed paths:
- limitations or blocked paths:
- commit:
- next action:
- released: 2026-07-15T06:27:54+00:00
