# Task: 2026-07-23-scheduler-gap-pipeline-overlap

## Outcome

Rebind the measured 358-gap scheduler mechanism to the observed retained source, freeze one equivalent intervention, and either measure the one admitted fresh pair plus trace or close on a typed no-retry boundary.

## Owner and coordination

- GitHub issue: https://github.com/joshsny/gradiated/issues/25
- GitHub project:
- owner: root
- Codex thread:
- created: 2026-07-23T02:40:37+00:00
- started: 2026-07-23T02:40:37+00:00
- last updated: 2026-07-23T03:09:00+00:00
- scope: research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_h200_scheduler_gap_pipeline_overlap
- excluded paths:
- dependencies:

## Contract

- hypothesis or user value: moving `SamplingBatchInfo.copy_for_forward` penalty preparation to `schedule_stream` can hide the 358 measured gaps behind current forward work.
- acceptance checks: required b648 source capture; source-chain rebind; exactly one fresh c32 pair; candidate path proof; one minimum trace only after valid candidate execution.
- quality gate: 32/32 sane requests and exact token/cache accounting per arm.
- SLO or budget: cumulative project reservation $12; one retained H200; no candidate replay.
- timeout: two claimed GPU-hours / three wall-clock hours from iteration-2 claim.
- artifact locations: `research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_h200_scheduler_gap_pipeline_overlap/artifacts/scheduler-gap-observed-v2-20260723t0305z`
- resume command: none; project is terminal.
- rollback or cleanup: bench released ready; no provider resource created or destroyed.

## Plan

1. Persist and hash the observed source; diff and rebind the chain.
2. Freeze one observed-source intervention and run the admitted fresh pair.
3. Require candidate-path proof before the trace; terminalize and release.

## Result

- status: complete
- verification: DevEx check, JSON parsing, Python compilation, shell syntax, exact source and artifact hashes.
- changed paths: project directory and this task packet.
- limitations or blocked paths: worker-local scheduler installation was absent after non-idempotent multiprocess `sitecustomize`; the candidate-labeled workload ran, so no retry or trace is allowed.
- commit: this handoff commit
- next action: do not replay or relabel; a worker-local idempotent redesign requires a new admitted project.
- released: 2026-07-23T03:08:59+00:00
