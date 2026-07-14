# Lean autonomous research factory

This package is the small execution kernel for perpetual, telemetry-driven model research. The director is the Codex session you start under your Codex subscription; the harness does not call an OpenAI API and needs no API key. One active Codex session may coordinate each model. If it stops or its context is replaced, a fresh session reconstructs ownership, spend, evidence, and the next decision from durable state.

The prototype deliberately contains no UI, service mesh, PostgreSQL, Temporal, Kubernetes scheduler, general graph ontology, intervention DSL, or learned optimizer. It standardizes only the boundaries where mistakes waste compute or corrupt scientific conclusions.

## Loop

```text
baseline + observations
  -> diverse scout portfolio
  -> cheapest faithful falsifiers
  -> strict paid-run admission when needed
  -> low-overhead correlated telemetry + hashed evidence bundle
  -> setup-affine retained session
  -> typed outcome and prediction error
  -> residual bottleneck and next loop
```

The four scientific records are a baseline, observations/scout cards, paid run specifications, and typed results. They are carried by one hash-chained event stream; `STATE.json` and the coordinator brief are generated views. Raw traces and outputs live in a content-addressed artifact store and are linked by manifest hash. See `OBSERVABILITY.md` for the collection and claim gates.

## Coordinator operation

A new or replacement Codex session needs only the repository, persistent lab root, and program ID. Its first command is:

```bash
PYTHONPATH=research/factory/src python3 -m grad_research resume \
  --root "$RESEARCH_LAB_ROOT" --program "$PROGRAM_ID" --owner "$CODEX_SESSION_ID"
```

`resume` acquires the single-writer fence, adopts a live retained setup, audits evidence references, blocks new provider mutations when cleanup or provider reconciliation is due, and writes `RESUME.json`, `WORK_QUEUE.json`, `STATE.json`, and `COORDINATOR.md`. The Codex session then follows the highest-priority recovery action or dispatches the runnable packets. Cheap offline packets are parallelizable; provider/setup-affine packets are serialized.

The operating loop is:

1. Run `resume`; trust its event head and generated views rather than chat history.
2. Resolve every P0 recovery action before new provider mutation. Run cheap trace analysis, source review, simulators, correctness oracles, and candidate preparation in parallel for selected scouts.
3. Store each observation or offline result with `store-artifact`, then append its typed JSON with `record --kind observation`, `scouts`, or `result`. Run `select-cycle` after proposing a cycle's scout pool.
4. Register each offline execution with `record --kind local_run`. Before paid compute, authorize the campaign budget once and use `admit-paid-run` on the exact spec. The durable admission event is the provider-creation intent; create at most one tagged resource with its idempotency key, then immediately call `register-allocation`.
5. After each paid run, use `pack-run`; only then record the result using the returned manifest and telemetry summary. Request adapter-backed cleanup and settle from stored provider-metered cost evidence. Never infer cleanup from process exit.
6. Run `resume` again. The residual bottleneck, failed mechanisms, instrumentation debt, and diverse next portfolio drive the next cycle.

There is deliberately no hidden LLM daemon. Research continues while the Codex session is active; when it is not, the watchdog/provider adapter must still enforce resource deadlines. Starting another Codex session with the same program and a new owner resumes the loop after the old lease expires.

Baseline, observation, scout, portfolio, run-admission, and result retries are idempotent for the coordinator. Reusing an identifier with changed content fails instead of silently rewriting history. The deterministic `demo` event stream is the compact executable example of every record shape.

## Local verification

```bash
PYTHONPATH=research/factory/src python3 -m unittest discover -s research/factory/tests -v
PYTHONPATH=research/factory/src python3 -m grad_research demo --root .agents/runtime/research-factory-demo
PYTHONPATH=research/factory/src python3 -m grad_research replay-legacy \
  --root .agents/runtime/research-factory-glm-replay \
  --program glm-4.7-flash \
  --ledger research/sol/experiments/glm47flash/campaign_100/CAMPAIGN_LEDGER.jsonl \
  --status research/sol/experiments/glm47flash/campaign_100/CAMPAIGN_STATUS.json \
  --decision research/sol/experiments/glm47flash/campaign_100/DECISION_CONTINUE_NARROWLY_SPLIT8_STOP_2026-07-14.json
```

No demonstration or test command above performs provider mutation or spends money. The lifecycle commands record authority and resource state; an actual provider adapter remains responsible for idempotent create, inventory reconciliation, and verified deletion.

Generate the standard telemetry contract with `telemetry-template`, then use `pack-run` after an experiment writes its declared outputs. This is one packaging step rather than a separate logging workflow; missing artifacts fail before a paid result can update research beliefs.

To resume the stopped GLM-4.7 campaign with the final decision and a fresh dense-residual portfolio:

```bash
PYTHONPATH=research/factory/src python3 -m grad_research bootstrap-glm47 \
  --root .agents/runtime/research-lab \
  --campaign-dir research/sol/experiments/glm47flash/campaign_100
```

Read `.agents/runtime/research-lab/programs/glm-4.7-flash/COORDINATOR.md`, execute cheap local scouts in parallel, and use paid admission only after the selected falsifier and all bound preflight checks pass. For the resumed real campaign, replace the disposable `.agents/runtime/` root with a persistent campaign evidence directory or mounted durable volume.
