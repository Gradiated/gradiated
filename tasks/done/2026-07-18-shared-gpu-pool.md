# Task: 2026-07-18-shared-gpu-pool

## Outcome

A lab-level GPU inventory decouples retained provider allocations from individual research projects. The director creates and tears down benches; researchers atomically claim compatible benches, update what is resident, run experiments, and release them without ending the allocation.

## Owner and coordination

- GitHub issue: https://github.com/joshsny/gradiated/issues/16
- GitHub project: unavailable to the configured token; issue is canonical
- owner: codex
- Codex thread: current user-directed Codex session
- created: 2026-07-18T11:08:21+00:00
- started: 2026-07-18T11:08:21+00:00
- last updated: 2026-07-18T11:08:21+00:00
- scope: research/factory/src/grad_research/gpu_pool.py,research/factory/src/grad_research/lab_harness.py,research/factory/tests/test_gpu_pool.py,research/factory/tests/test_lab_harness.py,research/factory/README.md,.agents/skills/research-director/SKILL.md,.agents/skills/researcher/SKILL.md,.agents/skills/research-supervisor/SKILL.md,research/sol/AGENTS.md,research/sol/experiments/gemma4_31b/research_lab/SUPERVISOR_LOG.md,tasks/active/2026-07-18-shared-gpu-pool.md
- excluded paths: provider credentials, paid provider mutation, active project artifacts outside the supervisor handoff
- dependencies: Python standard library and existing lab harness/runtime directory

## Contract

- hypothesis or user value: A director-owned warm bench removes repeated checkpoint/image/model setup while a tiny atomic lease prevents researchers from colliding on the same GPU.
- acceptance checks: inventory registration records hardware/resource/resident state and cleanup authority; concurrent claims admit one project; release preserves updated resident state without teardown; stale leases are visible but never auto-stolen; only director commands can drain/retire a bench; director/researcher/supervisor prompts receive the live inventory and role boundary.
- quality gate: focused GPU-pool and harness unit tests, full factory tests, DevEx check, and diff check.
- SLO or budget: no paid compute or provider mutation; no daemon/database/dependency; one JSON inventory, one lock, one JSONL event stream.
- timeout: local implementation and tests only.
- artifact locations: `research/factory/`, role skills, Sol operating instructions, and the Gemma supervisor handoff.
- resume command: `PYTHONPATH=research/factory/src:research/factory/tests python3 -m unittest research/factory/tests/test_gpu_pool.py research/factory/tests/test_lab_harness.py -v`
- rollback or cleanup: revert only this task's pool module, prompt integrations, tests, and docs; runtime inventories are external lab state and contain no credentials.

## Plan

1. Add the atomic lab-level bench inventory and CLI.
2. Expose inventory and claim/release commands to the three lab roles.
3. Verify state transitions, concurrency, prompt behavior, and existing harness tests.

## Result

- status: done
- verification: 106 full factory tests passed; 30 focused pool/harness tests passed after final integration; three role skills pass `quick_validate.py`; `python3 tools/devex/check.py`, `py_compile`, and scoped `git diff --check` pass; live director registered and a researcher claimed the current H200 after automatic harness reload.
- changed paths: `research/factory/src/grad_research/gpu_pool.py`, `research/factory/src/grad_research/lab_harness.py`, `research/factory/tests/test_gpu_pool.py`, `research/factory/tests/test_lab_harness.py`, `research/factory/README.md`, `.agents/skills/research-director/SKILL.md`, `.agents/skills/researcher/SKILL.md`, `.agents/skills/research-supervisor/SKILL.md`, `research/sol/AGENTS.md`, `research/sol/experiments/gemma4_31b/research_lab/SUPERVISOR_LOG.md`, and this packet.
- limitations or blocked paths: The currently adopted H200 began under the legacy project-owned controller and retains its original watchdog deadline; new allocations should be created as director-owned benches from the outset. Provider create/delete remains intentionally provider-specific and outside the inventory tool.
- commit:
- next action: Let the current claimed H200 finish its quality experiment. The director should preserve or drain it at the typed boundary, and create future benches with a long enough campaign-level deadline to amortize model setup across projects.
- released: 2026-07-18T11:24:36+00:00
