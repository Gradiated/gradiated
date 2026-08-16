# Research log

## 2026-07-16 — Director opening handoff

- Treat the verified archive as a background-valid economic pass despite the obsolete interactive-SLO return code.
- Attribute only what the retained phase/request/telemetry/source evidence identifies, and nominate at most one mechanism that conservatively closes the `9.503` tok/s robust gap.
- The direct maxseq36/split-8 frontier is independent and excluded; no provider, CUDA, checkpoint, shared-code, or terminal-lineage work.

## 2026-07-16 — Archive/source attribution terminal result

Question/action: consume the 40-member unchanged-stock maxseq32 archive once and attribute the c32 gain and remaining robust gap at `$0`, without provider, checkpoint, or shared-runtime mutation.

Evidence: the archive hash and manifest match. Exact c16/c32 are `550.908084/596.851973` tok/s over `59.479977/109.802770 s`, with 32/64 successful requests and all requests inside the 300-second background envelope. c32 gains `8.343%` while p50 TPOT worsens `19.954 -> 39.157 ms`, queue mean rises `2.017 -> 3.372 s`, and p95 TTFT reaches `20.018 s`. Prefix-cache counters remain zero. Active telemetry reaches 100% GPU utilization, 43,719 MiB FB use, and 2,520/9,001 MHz SM/memory clocks. The pinned source configuration is unchanged MLA block-32/stage-2, four KV splits; Triton MLA forces piecewise rather than full CUDA graphs.

Interpretation: the measured c32 gain is higher admitted concurrency and improved batch/device saturation, not a proven kernel-specific improvement. Summed request phase times overlap and the archive lacks scheduler-iteration and kernel interval unions, so the residual cannot be causally assigned to MoE, MLA, routing, host scheduling, or graph boundaries. Rank448+c40 remains a capacity hypothesis only: this archive supplies no c40 endpoint, the desired SM89 block-64 stage-2 tile remains unlegalized, and capacity arithmetic cannot conservatively guarantee `606.355` tok/s.

Decision: `ATTRIBUTION_CLOSE`. Machine-readable evidence is in [`STOCK_C32_ATTRIBUTION_CLOSE_2026-07-16.json`](artifacts/STOCK_C32_ATTRIBUTION_CLOSE_2026-07-16.json). The missing measurement is one independently owned exact rank448+c40 loader/quality/memory-reserve/endpoint falsifier; do not prepare or launch it here.
