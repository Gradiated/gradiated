# Sartor — instructions for Claude

Read `README.md` first for orientation, then `docs/REPORT.md` for the current
verdict and evidence ledger. This is a research environment testing whether
per-model full-stack co-design (custom serving software + finetune-healed
model surgery + eventually custom silicon) can host open-source LLMs cheaper
than incumbent providers (Fireworks/Baseten-class).

## Working conventions established in this project

- **Every quantitative claim gets a trust label**: measured (on this M4 Pro),
  anchored (to a public benchmark), or simulated (pure model). Never present a
  simulated number as measured. See `docs/calibration.md` for the trust
  discipline (realization factor 0.73, duty factor ~0.53) — apply it before
  quoting any absolute $/Mtok figure externally.
- **Ratios over absolutes**: cross-config ratios (the moat-study multipliers)
  are far better calibrated than absolute $/Mtok numbers. Prefer reporting
  "3.9× vs provider-best" over "$0.23/Mtok".
- **Uncertainty gets carried, not collapsed**: point estimates from
  `experiments/moat_study.py` are optimistic; the honest number is the Monte
  Carlo output from `moat_mc.py` (median + P10/P90), which models individual
  optimizations failing. Don't quote a point estimate as the headline without
  the MC range alongside it.
- **Real experiments correct the simulator, not the other way round**: when
  `twin/` (real weight surgery + healing on real models) or `barge`
  (real engine benchmarks) disagree with the simulator, the simulator's
  priors get updated and the MC gets rerun. This happened multiple times
  (MoE compute miscounted, EP comms modeled serial, a chip-fitter artifact,
  and — most importantly — the twin's matched-control healing runs corrected
  an overly optimistic reading of "head-pruning improves quality").
- **No comments unless genuinely non-obvious** (global user preference, also
  the style already in this codebase — see crates/engine/src for the pattern).
- **Neutral, non-salesy tone in `docs/sartor-report.html`**: it's a decision
  input document (fund or don't-fund), not a pitch. Keep it that way — no
  audience framing, no "for the curious" asides, state things as they are.
- **Every session's research should append to `bridge/lablog.jsonl`**
  (`{"ts","kind":"result"|"finding"|"note","text":...}` one JSON line per
  entry) and refresh `bridge/status.json`'s `updated`/`text` fields, so the
  live dashboard at slackhog.ngrok.dev stays current. Commit after each
  meaningful result, not in one giant batch at the end.

## Architecture quick-reference

- `crates/spec` defines `StackConfig` = `ModelSpec × HardwareSpec × KernelSpec
  × ServingSpec × WorkloadSpec × ParallelSpec × CostSpec`. A simulation run is
  a pure function over this tuple (`crates/perf::simulate`).
- `crates/perf::trace::trace_decode` gives a byte-exact per-op breakdown of
  one decode step — this is the tool for "why is X expensive" questions and
  for choosing which model-surgery lever to try next.
- `crates/engine` (binary name `barge`) is a real, independently-useful LLM
  serving engine (slot-based KV cache, continuous batching, OpenAI-compatible
  server) — it is both a product prototype and the simulator's ground truth.
  `tests/parity.rs` must stay green (logits match candle-transformers to
  ~1e-5); never merge an engine change that breaks it.
- `experiments/moat_study.py` is the reusable harness for "what does
  co-designing model X on hardware Y save" — read it before writing a new
  one-off study script; extend it rather than duplicating its TOML-generation
  logic.

## When resuming after a context clear

1. Read `README.md` and the top of `docs/REPORT.md`.
2. Check `bridge/lablog.jsonl` tail (`tail -20 bridge/lablog.jsonl`) for the
   most recent research activity — it's a chronological log independent of
   git history.
3. Check `git log --oneline -20` in `~/dev/gradiated` for recent commits.
4. If the bridge dashboard should be live, verify
   `curl -s -o /dev/null -w '%{http_code}' https://slackhog.ngrok.dev/`
   returns 200; restart `bridge/server.py` + `ngrok http 8710
   --domain=slackhog.ngrok.dev` if not (both plain `nohup ... &` processes,
   no supervisor).
