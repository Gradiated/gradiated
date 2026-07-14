# Research workstreams

Research is organized by workstream, not by agent. Each workstream owns its instructions, evidence contract, reports, and next-decision queue. Agents must leave outputs in the workstream so another agent can reproduce or challenge them without the original conversation.

## Workstream map

| Workstream | Question / role | Read first | Required checks |
| --- | --- | --- | --- |
| [`factory/`](factory/) | Shared perpetual research director, telemetry/evidence contracts, portfolio selection, and paid-run safety | [`AGENTS.md`](factory/AGENTS.md), [`README.md`](factory/README.md), [`OBSERVABILITY.md`](factory/OBSERVABILITY.md) | `PYTHONPATH=research/factory/src python3 -m unittest discover -s research/factory/tests -v` |
| [`sol/`](sol/) | Model-specific inference co-design under fail-closed evidence gates | [`AGENTS.md`](sol/AGENTS.md), [`README.md`](sol/README.md), [`CONTEXT_HANDOFF.md`](sol/CONTEXT_HANDOFF.md) | `cargo fmt --check`; `cargo clippy --workspace --all-targets -- -D warnings`; `cargo test --workspace` |
| [`fable/`](fable/) | Sartor/Fable full-stack co-design and calibrated scenario research | [`CLAUDE.md`](fable/CLAUDE.md), [`README.md`](fable/README.md), current `docs/REPORT.md` | Follow `CLAUDE.md`; run the narrowest relevant Rust/Python checks |

## Adding a workstream

Create this minimum shape before starting work:

```text
research/<name>/
  README.md              # question, current verdict, reset commands, links
  AGENTS.md or CLAUDE.md # local invariants and quality gates
  docs/                  # reports and decision briefs
  evidence/              # raw or normalized evidence, with provenance
  experiments/           # scripts, configs, manifests, and run packets
```

Use dated decision briefs for conclusions and machine-readable JSON/JSONL for measurements, gates, and ledgers. Keep raw evidence separate from synthesis. Record blocked and negative results as first-class outputs.

## Evidence labels

Every research conclusion must identify whether each important input is `measured`, `analytical`, `vendor-reported`, `derived`, `inferred`, or `synthetic`. State the workload, model/software/hardware identity, control, quality gate, and claim scope before comparing or composing results.
