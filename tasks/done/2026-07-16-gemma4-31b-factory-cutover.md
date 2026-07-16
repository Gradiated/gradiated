# Task: 2026-07-16-gemma4-31b-factory-cutover

## Outcome

The GLM-4.7 Flash lab is durably concluded and inactive. A fresh Gemma 4 31B campaign runs continuously through the existing subscription-authenticated research harness, with its own objective, workload, economics, projects, traces, and WhatsApp result stream.

## Owner and coordination

- GitHub issue: https://github.com/joshsny/gradiated/issues/24
- GitHub project: unavailable/not configured for this repository
- owner: root
- Codex thread:
- created: 2026-07-16T21:55:27+00:00
- started: 2026-07-16T21:55:27+00:00
- last updated: 2026-07-17T00:07:01+02:00
- scope: research/sol/experiments/gemma4_31b/research_lab,research/sol/experiments/glm47flash/research_lab/CONCLUSION_2026-07-16.md,/root/.config/gradiated/research-lab/gemma4-31b.json,systemd service cutover
- excluded paths: existing GLM project artifacts and unrelated dirty worktree changes
- dependencies: installed Codex subscription login, existing provider credentials, research factory harness

## Contract

- hypothesis or user value: A model-clean campaign with an immediate measured baseline lane and a parallel architecture/opportunity lane will preserve factory speed while directing research toward Gemma 4 31B cost leadership.
- acceptance checks: GLM service inactive/disabled; direct provider inventory empty; Gemma config parses; focused harness tests and DevEx pass; Gemma lab and notifier active; first director turn creates runnable projects and researchers begin work.
- quality gate: exact pinned model identity and complete-request telemetry for baseline evidence; broad quality is deferred until a performance candidate, but required before production qualification.
- SLO or budget: initial autonomous paid experiment cap $25; no more than one live paid allocation; two parallel researchers; 60-second scheduling cadence.
- timeout: 60 minutes for cutover and initial scheduling verification; project-specific timeouts live in each project brief.
- artifact locations: research/sol/experiments/gemma4_31b/research_lab/, its runtime events/traces, and GitHub issue 24.
- resume command: `systemctl --user restart gradiated-research-lab@gemma4-31b.service`
- rollback or cleanup: stop/disable Gemma lab and notifier, then verify provider inventory is empty; do not resume the concluded GLM campaign unless explicitly requested.

## Plan

1. Conclude and disable the GLM campaign after terminal provider cleanup.
2. Create the fresh Gemma 4 31B campaign and host-only harness config.
3. Verify the harness, start the lab/notifier, and observe the first director/researcher scheduling cycle.

## Result

- status: done
- verification: 19 focused harness/notifier tests passed; `python3 tools/devex/check.py` passed; old GLM lab is inactive/disabled; direct provider inventory was 0 instances/0 disks; Gemma lab and notifier are active/enabled; Sol completed its first director turn in 330.614 seconds and launched both delegated researchers.
- changed paths: `research/sol/experiments/gemma4_31b/research_lab/`, `research/sol/experiments/glm47flash/research_lab/CONCLUSION_2026-07-16.md`, and host-only `/root/.config/gradiated/research-lab/gemma4-31b.json`; systemd instance links changed from GLM to Gemma.
- limitations or blocked paths: no research result yet; the first H100 researcher is validating exact Gemma/runtime/provider inputs before allocation, while the parallel researcher prepares geometry and MTP/async evidence. Existing unrelated dirty worktree changes were preserved.
- commit: included in the direct-to-main repository handoff.
- next action: let the autonomous factory execute `exact_bf16_mtp_h100_frontier` and `exact_geometry_runtime_opportunities`; review results through the generated lab status, traces, and WhatsApp notifications.
- released: 2026-07-16T22:07:16+00:00
