# Task: 2026-07-15-simple-research-lab

## Outcome

A small subscription-authenticated research lab continuously runs one Sol research director, several parallel project researchers, and a periodic research-process supervisor. Agent judgment lives in three concise skills; code only schedules turns, records traces, renders status, and keeps project threads durable.

## Owner and coordination

- GitHub issue: https://github.com/joshsny/gradiated/issues/18
- GitHub project: unavailable to the configured token; issue is canonical
- owner: codex-simple-lab
- Codex thread:
- created: 2026-07-15T06:41:51+00:00
- started: 2026-07-15T06:41:51+00:00
- last updated: 2026-07-15T06:41:51+00:00
- scope: research/factory,.agents/skills/research-director,.agents/skills/researcher,.agents/skills/research-supervisor,research/sol/experiments/glm47flash/research_lab,tasks/active/2026-07-15-simple-research-lab.md
- excluded paths: active provider/controller artifacts until their watchdog completes; unrelated product and Fable work
- dependencies: saved Codex subscription login, Codex CLI, existing provider/experiment tools and credentials outside the repository

## Contract

- hypothesis or user value: A high-freedom skill-based lab with project-local logs will produce more actual research and less coordinator ceremony than the current event-heavy director/work-packet loop.
- acceptance checks: three valid skills; director creates/delegates project files; active projects run in parallel with persistent threads; each project has a research log; process supervisor periodically reviews throughput; JSONL traces and compact status survive restart; no API key is passed to Codex; systemd service runs the GLM-4.7 lab.
- quality gate: focused deterministic tests with fake agents, repo skill validation, DevEx checks, no live cutover until the old provider controller is quiescent.
- SLO or budget: at most one Sol director plus configured parallel researchers per cycle; no new provider budget authority; harness contains no scientific policy state machine.
- timeout: director 15 minutes, researcher 45 minutes, process supervisor 15 minutes; existing experiment tools own their own GPU deadlines and cleanup.
- artifact locations: `.agents/skills/{research-director,researcher,research-supervisor}/`, `research/factory/src/grad_research/lab_harness.py`, `research/sol/experiments/glm47flash/research_lab/`.
- resume command: `systemctl --user restart gradiated-research-lab@glm47.service`
- rollback or cleanup: stop the new service and re-enable the old supervisor only after confirming no active provider controller; campaign logs and experiment artifacts are retained.

## Plan

1. Create concise high-freedom skills and the lab file contract.
2. Build the minimal scheduler, trace/status output, tests, and service unit.
3. Wait for the live V23 controller to finish safely, cut over, and verify real Codex turns/logs.

## Result

- status: done
- verification: 4 focused harness tests pass; 7 repository skills validate; `python3 tools/devex/check.py` passes; new systemd service is enabled/active; first Sol director completed in 283.898 seconds and delegated three projects; three Terra researchers are running concurrently; old supervisor is disabled/inactive; V23 provider resource and disk are absent, result recorded, and reservation settled at $0.128855.
- changed paths: `.agents/skills/{research-director,researcher,research-supervisor}/`, `AGENTS.md`, `docs/CONTEXT_INDEX.md`, `research/README.md`, `research/factory/{AGENTS.md,README.md,SUPERVISOR.md,pyproject.toml,src/grad_research/lab_harness.py,tests/test_lab_harness.py,systemd/gradiated-research-lab@.service,tools/README.md}`, deleted legacy supervisor source/test/unit, `research/sol/experiments/glm47flash/research_lab/`.
- limitations or blocked paths: GitHub Project status could not be read because the configured token lacks Projects permission. The broader legacy factory suite has 58/60 passing tests; two old tests hard-code a pre-observer campaign snapshot and fail against the now-advanced live campaign. They do not cover the new lab harness.
- commit:
- next action: let the three active researchers finish their turns; the next persistent Sol director turn will read their logs and update the portfolio. Inspect with `PYTHONPATH=research/factory/src python3 -m grad_research.lab_harness --config /root/.config/gradiated/research-lab/glm47.json --status`.
- released: 2026-07-15T07:05:55+00:00
