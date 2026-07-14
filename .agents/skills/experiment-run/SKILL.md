---
name: experiment-run
description: Plan, execute, verify, and record bounded technical or product experiments with explicit hypotheses, budgets, timeouts, cleanup, and durable artifacts. Use when an agent needs to benchmark, run a model or browser experiment, compare alternatives, or gather evidence for a decision.
---

# Experiment run

Make experiments useful to the next agent, including when they fail.

## Workflow

1. Create or claim a task packet before running work.
2. State the causal hypothesis, stock control, exact inputs and revisions, workload geometry, quality gate, SLO, maximum spend, timeout, and artifact contract.
3. Prefer an existing harness. Add a deterministic script or configuration when a command will be repeated.
4. Run a smoke test before expensive allocation. Capture stdout, stderr, environment identity, command, seed, and timestamps without secrets.
5. Enforce the timeout and final teardown contract. For costly accelerator setup, retain the allocation across preregistered arms and in-place repairs when the next useful test can start within ten minutes; delete and verify absence when the session ends.
6. Validate correctness before performance, then validate performance before economics or product claims.
7. Record measured, analytical, vendor-reported, derived, inferred, and synthetic results separately.
8. Update the task packet, report, ledger, and next-action decision before committing.

## Retained accelerator sessions

Treat allocation, image/runtime setup, checkpoint transfer, model load, and scientific arms as separate costs. Queue likely arms before allocation and reuse the most expensive valid state.

- Keep one explicit session owner and an independent absolute-deadline cleanup watchdog.
- Push content-addressed harness changes in place. Preregister each causal change before executing it.
- Verify large immutable resident inputs once per session, then write a content-addressed integrity marker that binds the manifest hash, file identities, and verification timestamp. Later arms may validate that marker and cheap file metadata instead of re-reading every byte; invalidate it after any write, remount, repair, or unexplained state change.
- Reuse a live server for observer-only changes; reload the server for runtime flags; recreate the VM only for hardware, driver, image, or unsafe-state changes.
- Inspect typed results for embedded harness errors. A result envelope is not a scientific result merely because it exists.
- When a trace selects a custom kernel, reproduce its exact shapes in a correctness-checked standalone microbenchmark and reject hardware-illegal launch configurations before paying for another full model/server arm. Require a prospective component-to-end-to-end effect threshold before promotion.
- After any error or completed arm, decide whether the next materially changed test can begin within ten minutes. Retain and start it when yes; teardown when no, or on a safety, spend, deadline, or completed-lineage stop.
- Retrieve and hash every arm independently. Attribute total allocation exposure across the session and perform one final delete plus provider absence verification.

Read [experiment-contract.md](references/experiment-contract.md) for the required fields and failure handling.
