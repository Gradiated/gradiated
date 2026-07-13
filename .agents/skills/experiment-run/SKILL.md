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
5. Enforce the timeout and teardown contract. Delete remote compute and verify deletion when the experiment provisions it.
6. Validate correctness before performance, then validate performance before economics or product claims.
7. Record measured, analytical, vendor-reported, derived, inferred, and synthetic results separately.
8. Update the task packet, report, ledger, and next-action decision before committing.

Read [experiment-contract.md](references/experiment-contract.md) for the required fields and failure handling.
