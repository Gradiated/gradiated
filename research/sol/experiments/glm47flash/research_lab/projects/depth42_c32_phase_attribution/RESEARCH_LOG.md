# Research log

## 2026-07-16 — Director opening handoff

- New evidence: a clean depth42 c16/c32 pair passes the campaign economic envelope and includes complete telemetry, while quality remains failed/deferred.
- Objective: explain the measured c32 gain and nominate at most one non-depth mechanism with a conservative `606.355` path; otherwise close observability at `$0`.
- Guardrail: no provider, profiler rerun, code mutation, c40+, or additional layer-count proposal.

## 2026-07-16 — Terminal phase attribution

- Reconstructed the two scientific intervals from `phases.jsonl`, request rows, and 1-second `telemetry.csv`; the compact machine-readable result is [`DEPTH42_PHASE_ATTRIBUTION_2026-07-16.json`](artifacts/DEPTH42_PHASE_ATTRIBUTION_2026-07-16.json).
- Measured c16/c32: `616.602087/686.910494` tok/s; GPU utilization `99.98/100.0%`, power `325.11/325.00 W`, and peak memory `43,869/43,871 MiB`. Prefix-cache deltas are zero.
- c32 raises aggregate throughput `11.398%` while TTFT rises `54.1%`, TPOT rises `90.6%`, and mean queue rises `1.2175 s`; this identifies continuous decode batch packing as the only source/runtime-bound mechanism supported by the retained data. Prefill, cache, memory capacity, and power/frequency headroom do not explain the gain.
- Terminal decision: `NOMINATE_MECHANISM`. Conservative path is to preserve the proven runtime batch geometry and tune decode admission/packing with a `606.355 tok/s` (98.34% of c16) lower bound. A matched c16 arm below that bound, above `44,532 MiB`, or below `95%` GPU utilization falsifies it. No successor is opened.
