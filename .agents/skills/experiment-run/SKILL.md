---
name: experiment-run
description: Plan, execute, verify, measure the efficiency of, and record bounded technical or product experiments with explicit hypotheses, budgets, timeouts, and cleanup. Use when an agent needs to benchmark, run a model or browser experiment, compare alternatives, gather evidence for a decision, or diagnose research throughput.
---

# Experiment run

Make experiments useful to the next agent, including when they fail.

## Routine product and infrastructure checks

For deployment tests, CI diagnosis, service checks, and small operational benchmarks:

- State the scope, success criteria, timeout, and cost limit in a short progress message.
- Keep raw output and temporary scripts under ignored `.agents/runtime/`, or the remote host's temporary directory.
- Do not create evidence folders, dated reports, task packets, ledgers, opportunity registers, or handoff files.
- Report the result and limitations in the response or PR. Update an existing README or plan only when a useful operating instruction or decision changes.
- Keep reusable tests with the component they test. Do not retain one-off probes as product code.
- Preserve credentials and active test state during cleanup. Stop test processes and verify cleanup within the authorized scope.

The research workflow below applies only to research campaigns that need recorded measurements. It does not apply to routine product or infrastructure work.

## Research workflow

1. Create or claim a task packet before running work. For a research-lab harness project, its existing `projects/<id>/` brief, status, and log are the task packet: do not create, claim, assign, or update GitHub issues or `tasks/` files.
2. State the causal hypothesis, stock control, exact inputs and revisions, workload geometry, quality gate, SLO, maximum spend, timeout, and artifact contract.
3. Build a typed observation-to-opportunity register before choosing an intervention. Record the evidence scope, phase, resource signature, uncertainty, competing explanations, modifiable fraction, upper bound, falsifier, next measurement, and expected information per dollar. Encourage intuition and first-principles leaps, but anchor them to observed data or an explicit unknown and choose a cheap discriminating measurement.
4. Measure the baseline deeply enough to locate the critical path. Capture phase and concurrency, per-request distributions, queueing, batch composition, failures, CPU/GPU timelines, accelerator utilization, memory capacity and traffic, cache behavior, occupancy/resource limits, power, and network/collective behavior when relevant. Separate setup/load telemetry from steady state.
5. Prefer an existing harness. Add a deterministic script or configuration when a command will be repeated.
6. Use the cheapest fidelity that can falsify the mechanism: analytical bound, deterministic simulation, CPU/reference oracle, reduced model, exact-shape component harness, target-hardware microbenchmark, then matched serving holdout. A lower-fidelity pass promotes a measurement; it never approves transfer to a higher scope.
7. Make the smoke test the smallest real invocation in the exact target environment. During discovery, retain the session, inspect the traceback, patch ordinary integration defects in place, and continue; do not use source-string checks as behavioral proof.
   Precondition and absence probes must be read-only: use metadata or `Path.exists()` and never open a result, terminal, request, or owner-state path in write, append, or create mode merely to test whether it exists.
8. Enforce an absolute watchdog and spend deadline, not teardown after every exception. Apply a timeout derived from that same absolute deadline to every pipeline, repair callback, remote command, and child process; exporting or documenting the deadline without bounding the subprocess does not enforce it. Retain costly accelerator state across in-place repairs and adjacent arms while it remains the fastest safe route to evidence; delete and verify absence when the session genuinely ends.
9. Validate correctness before performance, then validate performance before economics or product claims. Alternate or randomize matched control/candidate repetitions and report uncertainty when the decision margin is not obviously larger than run variance.
10. Record measured, analytical, vendor-reported, derived, inferred, and synthetic results separately. Score every prospective prediction after measurement and update the bottleneck model.
11. Update the task packet, report, ledger, opportunity register, residual bottleneck, and next-action decision before committing.

## Throughput discipline

Keep the user-selected coordinator model for campaign-level judgment. Use its expensive reasoning for hypothesis selection, causal interpretation, admission, stop/promotion decisions, and surprising failures. Route bounded mechanical work—log extraction, fixture generation, polling, packaging, deterministic tests, and routine code edits—to faster workers or lower reasoning effort when available.

- Batch a mechanical phase into one script or tool call. If a sequence needs more than three similar shell calls or will recur, make it one bounded deterministic command with structured output.
- Do not assign several high-reasoning agents overlapping reviews. Give workers disjoint outputs, use at most one high-reasoning skeptic for a decision, and continue non-overlapping work while they run.
- Launch provider work as one bounded asynchronous experiment command. Do not spend model turns repeatedly polling when the wait mechanism can yield.
- Validate images, dependency keys, capability-output parsers, harness patches, and exact fixtures before allocation. Emit phase timestamps for provision, SSH, image/bootstrap, checkpoint transfer, model load, warmup, scored arms, packaging, and cleanup.
- Emit `useful_gpu_seconds` separately from provider-active seconds. Useful GPU time begins at model transfer or the first experiment-specific GPU operation, not VM creation.
- Reuse a validated image and retained resident state. A paid allocation should not discover a dependency or parser incompatibility that a local fixture or image-build check could have rejected.

Measure the last 24 hours before a daily campaign review:

```bash
python3 .agents/skills/experiment-run/scripts/research_efficiency.py \
  --thread-id "$CODEX_RESEARCH_THREAD_ID" \
  --campaign-dir "$CAMPAIGN_DIR" \
  --hours 24 \
  --output-dir "$RESEARCH_LAB_ROOT/efficiency"
```

Use `LATEST.json` for comparisons and `LATEST.md` for the operator summary. Optimize valid scientific outcomes per active coordinator hour and per dollar. Treat model/orchestration share, synchronous tool wait, provider setup, useful GPU share, invalid spend, and context compactions as diagnostic metrics—not goals that can justify weaker evidence.

For model, kernel, serving, memory, network, or hardware search campaigns, read [measurement-driven-research-loop.md](references/measurement-driven-research-loop.md) before designing the search.
Use `scripts/opportunity_register.py` to validate and rank reusable typed opportunity queues when the campaign has more than a few candidates.
Use `scripts/summarize_nvidia_smi.py` to separate standard one-second accelerator telemetry by recorded experiment phases, report coverage/gaps, and integrate phase energy instead of reporting allocation-wide setup averages.
Use `scripts/analyze_bracketed_ab.py` for deterministic A/B/A/.../B/A same-session effects and paired bootstrap intervals. Fewer than three independent candidate repetitions remain descriptive and the tool deliberately suppresses an interval.
Use `scripts/research_efficiency.py` for daily Codex/provider throughput accounting. It reads event timing metadata, not reasoning text.

## Retained accelerator sessions

Treat allocation, image/runtime setup, checkpoint transfer, model load, and scientific arms as separate costs. Queue likely arms before allocation and reuse the most expensive valid state.

Use a mutable development session for first execution and a frozen batch session for canonical reproduction. In development mode the same researcher remains attached, may update harness bytes and rerun commands on the owned instance, and records each attempted program and result. Operational failures such as imports, paths, permissions, runtime context, signatures, telemetry, and benchmark bugs normally stay in the session and project. They become terminal only when repair is unsafe, requires different hardware or image, exceeds the budget or deadline, or is no longer the best research choice.

- Keep one explicit session owner and an independent absolute-deadline cleanup watchdog.
- Push content-addressed harness changes in place. Preregister each causal change before executing it.
- Verify large immutable resident inputs once per session, then write a content-addressed integrity marker that binds the manifest hash, file identities, and verification timestamp. Later arms may validate that marker and cheap file metadata instead of re-reading every byte; invalidate it after any write, remount, repair, or unexplained state change.
- Reuse a live server for observer-only changes; reload the server for runtime flags; recreate the VM only for hardware, driver, image, or unsafe-state changes.
- Inspect typed results for embedded harness errors. A result envelope is not a scientific result merely because it exists.
- Keep one provider-state coordinator. Parallelize read-only trace analysis, prior-art review, simulator construction, candidate generation, local tests, and result validation. Parallelize live experiments only across independent budgeted allocations whose controls, randomization, and cleanup ownership cannot interfere.
- When a trace selects a custom kernel, reproduce its exact shapes in a correctness-checked standalone microbenchmark and reject hardware-illegal launch configurations before paying for another full model/server arm. Do not convert summed or overlapping kernel duration into end-to-end share. Require a scope-matched critical-path attribution or empirical end-to-end A/B before promotion.
- After any error or completed arm, decide whether the next materially changed test can begin within ten minutes. Retain and start it when yes; teardown when no, or on a safety, spend, deadline, or completed-lineage stop.
- Retrieve and hash every arm independently. Attribute total allocation exposure across the session and perform one final delete plus provider absence verification.

Read [experiment-contract.md](references/experiment-contract.md) for the required fields and failure handling.
