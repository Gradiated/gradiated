# Research observability contract

Telemetry is the researcher's sensory system. A campaign may simplify instrumentation when a signal has low decision value, but it must never silently lose visibility into a part of the critical path or present profiler output as an unperturbed performance result.

## What every scored server arm records

Use one monotonic clock with a wall-clock anchor and carry `run_id`, request, and scheduler-iteration correlation keys across the stack. The default scoreable template covers:

- provenance: exact model, checkpoint, tokenizer, code, runtime, configuration, and hardware identities;
- request: arrival, prompt/output tokens, queue time, TTFT, TPOT, end-to-end latency, status, and failures;
- scheduler: iteration phase and duration, batch composition, scheduled tokens, request state, and KV state;
- accelerator: utilization, memory, clocks, power, temperature, and resource failures;
- host: CPU, memory, transfer, I/O, and network health on the same clock;
- model: phase/module tags, shapes, dtypes, layouts, cache state, and architecture-specific routing or draft signals when applicable;
- quality: sample identity, policy identity, score, correctness, and SLO eligibility;
- economics: allocation lifetime, accelerator seconds, rates, shared setup cost, arm cost, and total cost.

The template is a minimum, not a fixed ontology. Add model-specific signals when they distinguish live hypotheses. Record an unsupported signal as `unavailable` with a reason and the cheapest next probe. Core request, provenance, quality, and cost data cannot be declared unavailable for a paid scored run.

## Observer ladder

`always_on` means the collector remains enabled, not that every field is emitted at maximum frequency. The default contract records request and scheduler lifecycle events, dictionary-encodes static model/operator shapes once, and samples host/accelerator health at one hertz. `sampled_trace` and `deep_profile` are separate diagnostic arms. Any intrusive observer requires an observer-off/on/off bracket. By default, shorten or sample the trace when throughput or median latency moves by more than 3%, or tail latency by more than 5%.

A deep profiler is diagnostic-only. It may identify shapes, dependencies, launch gaps, resource limits, or the next experiment, but its perturbed run cannot score a candidate. A phase-share or residual-bottleneck claim requires correlated dependency-union coverage of at least 95%. Summed kernel duration remains diagnostic.

## Evidence bundles

The artifact store writes immutable SHA-256 objects once and creates one manifest per run. Large raw traces are not copied into the event log; the result event points to the manifest hash. A run bundle contains:

- the exact run specification and identities;
- raw correlated events and system samples required by its telemetry contract;
- measurement, quality, telemetry-coverage, and cost summaries;
- stdout/stderr or a structured failure log;
- the object hash, byte count, role, producer, evidence class, media type, telemetry category, and capture tier for every artifact.

The packer fails if a declared file is missing or empty. It derives identity, bracketed effect, gate, telemetry coverage, and cost assertions from stored raw records rather than trusting the result summary. A paid scientific result is rejected when its bundle is absent, semantically contradictory, bound to another run or telemetry contract, missing planned signals, below its attribution gate, or invalidated by observer perturbation. Operational and harness failures retain their logs and cost evidence but do not update scientific beliefs.

Scoreable runs keep intrusive profilers off and therefore do not claim profiler-based critical-path coverage. Diagnostic runs use dependency-union attribution and an observer-off/on/off bracket. This separates unperturbed end-to-end scoring from bottleneck diagnosis.

Use a persistent, backed-up `--root` for real campaigns, for example a campaign evidence directory or mounted durable volume. `.agents/runtime/` is appropriate only for tests and disposable demonstrations. Content addressing deduplicates identical inputs and allows a later deep audit to rehash every object.

## Commands

Create a scoreable or deep-diagnostic contract:

```bash
PYTHONPATH=research/factory/src python3 -m grad_research telemetry-template --mode scoreable --output telemetry-contract.json
PYTHONPATH=research/factory/src python3 -m grad_research telemetry-template --mode diagnostic_only --output diagnostic-telemetry-contract.json
```

After a run writes every path declared in its run specification, package and verify it:

```bash
PYTHONPATH=research/factory/src python3 -m grad_research pack-run \
  --root "$RESEARCH_LAB_ROOT" --program "$PROGRAM_ID" \
  --spec run-spec.json --run-dir run-output

PYTHONPATH=research/factory/src python3 -m grad_research verify-artifacts \
  --root "$RESEARCH_LAB_ROOT" --program "$PROGRAM_ID" \
  --manifest "$MANIFEST_SHA256" --deep
```

If execution fails before a scoreable measurement exists, write `failure.json` with `schema_version`, `run_id`, `failure_class`, `stage`, and `message`; make `telemetry.json` account for each planned signal as captured or missing; retain exact identities, logs, and provider-metered cost. Then package it without inventing measurement or quality evidence:

```bash
PYTHONPATH=research/factory/src python3 -m grad_research pack-run \
  --root "$RESEARCH_LAB_ROOT" --program "$PROGRAM_ID" \
  --spec run-spec.json --run-dir run-output --failure-class "$FAILURE_CLASS"
```

## Self-improvement rule

After each cycle, inspect `observability.telemetry_gaps` in `STATE.json` and the observability section of `COORDINATOR.md`. Promote an instrumentation change into the scout portfolio when the missing signal blocks attribution between competing explanations or repeatedly causes invalid spend. Rank it by the decision value it unlocks, not by telemetry completeness for its own sake. Once a signal stops changing decisions, reduce its sampling or retention cost while preserving exact raw samples around decision boundaries.
