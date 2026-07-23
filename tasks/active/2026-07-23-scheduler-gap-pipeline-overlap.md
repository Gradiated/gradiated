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
- last updated: 2026-07-23T03:31:37+00:00
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
- resume command: none; scientific terminal reached.
- rollback or cleanup: bench released ready; no provider resource created or destroyed.

## Plan

1. Persist and hash the observed source; diff and rebind the chain.
2. Freeze one observed-source intervention and run the admitted fresh pair.
3. Require candidate-path proof before the trace; terminalize and release.

## Result

- status: complete
- verification: candidate-only H200 endpoint passed 32/32 exact accounting and runtime path proof; minimum trace workload completed with the same proof.
- changed paths: project directory and this task packet.
- limitations or blocked paths: Nsight report was absent after the completed trace capture; the trace cannot be replayed.
- commit: this handoff commit
- next action: do not replay; this scheduler overlap is a measured negative.
- released: 2026-07-23T03:08:59+00:00
