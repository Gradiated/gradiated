# Task: 2026-07-24-event-driven-research-scheduler

## Outcome

The continuous research harness reacts to each material researcher completion:
one serialized director turn consumes the result immediately, free researcher
slots refill without waiting for unrelated work, and the periodic supervisor
cannot block either path.

Follow-up: periodic fallback oversight remains enabled while research is active,
but its cadence is measured from the end of the latest director turn so the
harness cannot launch an accidental back-to-back review.

## Owner and coordination

- GitHub issue: https://github.com/joshsny/gradiated/issues/18
- GitHub project:
- owner: codex
- Codex thread:
- created: 2026-07-24T17:37:53+00:00
- started: 2026-07-24T17:37:53+00:00
- last updated: 2026-07-24T18:50:00+00:00
- scope: research/factory/src/grad_research/lab_harness.py,research/factory/tests/test_lab_harness.py,research/factory/README.md
- excluded paths: model research projects, GPU/provider lifecycle, scientific skills
- dependencies: preserve the uncommitted spend, durable-owner, and warm-bench scheduler changes already present in the owned files

## Contract

- hypothesis or user value: removing the batch barrier materially lowers result-to-decision latency and keeps all five research slots useful.
- acceptance checks: a fast result starts a director and successor before a slow sibling finishes; unchanged active work does not wake Sol every fallback interval; a blocked supervisor does not block the director; every completed director resets the periodic fallback deadline; existing harness tests pass.
- quality gate: preserve spend reservations, durable-owner continuation/adoption, GPU fencing, route selection, source reload, and `--once` behavior.
- SLO or budget: no new dependency or service; use the existing process and at most five researcher Codex processes.
- timeout: finish implementation and verification in this Codex turn.
- artifact locations: source, tests, README, and this task packet.
- resume command: `PYTHONPATH=research/factory/src:research/factory/tests python3 -m unittest research/factory/tests/test_lab_harness.py -v`
- rollback or cleanup: revert only the event-loop additions; the synchronous `cycle()` path remains available for `--once`.

## Plan

1. Extract reusable researcher selection/submission without changing policy.
2. Add the persistent first-completion event loop and independent supervisor.
3. Verify focused scheduling behavior, the complete harness suite, and DevEx.

## Result

- status: complete
- verification: 144 factory tests pass; 49 harness tests pass; the focused fallback-cadence regression passes; Python compilation and DevEx pass. Earlier focused event concurrency tests passed ten repeated stress runs, diff checks, and two independent review passes.
- changed paths: research/factory/src/grad_research/lab_harness.py; research/factory/tests/test_lab_harness.py; research/factory/README.md
- limitations or blocked paths: safe source reload deliberately drains already-running Codex turns before restart rather than killing an experiment. The live service requested that reload at 2026-07-24T20:34:16Z and is preserving an active deep H200 researcher until its turn boundary.
- commit:
- next action: the active systemd service automatically loads the final source after the current `gemma4_h200_ngram_torch_reserved_staircase` researcher reaches its turn boundary; no manual restart or experiment interruption is required.
