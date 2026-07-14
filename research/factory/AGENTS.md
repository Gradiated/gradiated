# Research factory instructions

This workstream owns the lean, repository-native harness for autonomous model research. It coordinates research; it does not make production releases or call live providers in tests.

## Design test

Every retained component must do at least one of the following:

- prevent invalid paid compute;
- increase valid experiments per expensive setup;
- broaden the intervention portfolio;
- improve causal attribution or claim validity;
- make unattended recovery and cleanup safer.

Delete or defer abstractions that do not satisfy that test with a concrete behavior.

## Scientific invariants

- The active Codex subscription session is the director, but chat context never owns durable state and the harness never calls an LLM API.
- Repository JSONL events and hashed artifacts are scientific truth. SQLite is the durable runtime safety ledger; reconcile it against admitted provider intents and tagged provider inventory after interruption.
- Every measured observation references a stored artifact. Every admitted paid result references a complete content-addressed evidence bundle bound to its run and telemetry contract.
- Keep low-overhead request-to-model telemetry on scored arms. Deep profilers are separate diagnostic arms with observer-off/on/off perturbation measurement.
- Missing telemetry is explicit research debt. Improve instrumentation when it blocks a bottleneck decision, not merely to maximize the number of collected counters.
- Only scientific positive, negative, or mixed outcomes update mechanism beliefs. Harness-invalid and operational outcomes update reliability statistics only.
- A valid scientific result includes a residual-bottleneck update. Lower-fidelity evidence cannot silently become a higher-scope claim.
- Paid admission fails before provider mutation unless identity, control, quality/SLO, budget, timeout, watchdog, artifact, and cleanup contracts pass.
- One fenced owner mutates a provider allocation. Retained state is explicit and remains under an independent deadline.
- Preserve Sol/GLM evidence as measured history. Legacy replay is normalization, not reinterpretation.

## Commands

```bash
PYTHONPATH=research/factory/src python3 -m unittest discover -s research/factory/tests -v
PYTHONPATH=research/factory/src python3 -m grad_research demo --root .agents/runtime/research-factory-demo
```

Keep generated databases, projections, and demo artifacts under `.agents/runtime/` or test temporary directories unless they are explicit decision evidence.

For a real multi-day campaign, use a persistent backed-up lab root and follow `OBSERVABILITY.md`; `.agents/runtime/` is disposable.

Every fresh director begins with `grad_research resume --root ... --program ... --owner ...`. Resolve its P0 actions before provider mutation, parallelize `parallel_offline` packets, serialize `serialized_setup_affine` packets, and rerun `resume` after each material transition. Do not add an OpenAI API client or background LLM daemon.
