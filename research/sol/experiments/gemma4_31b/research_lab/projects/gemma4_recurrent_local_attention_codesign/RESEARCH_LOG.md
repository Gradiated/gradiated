# Research log

## 2026-07-26T10:43Z — exact recurrent local-attention physical screen

- **Question:** Can all 50 exact Gemma 4 sliding layers replace the
  1,024-key scan with a rolling information-carrying state and reduce the
  measured local family by at least 47.62088323402555% without credit from any
  other candidate?
- **Action:** Bound the pinned config, runtime sources, and c32 trace; joined
  750 local calls (`997521.149 us`) and 150 global calls (`490684.609 us`);
  implemented rank-64 positive-feature production, FP32 numerator/denominator,
  a 1,024-slot projected-K/full-V eviction ring, graph-padding and ownership
  guards, stock fallback, and the one-pass real output consumer. Ran the
  deterministic recurrence/direct-window fixture and exact physical model.
- **Evidence:** `RECURRENT_LOCAL_ATTENTION_PHYSICAL_SCREEN.json`
  (`sha256:708761c17bc605702d16058331493c01eab65417d7dc45fdea4a6ea4411fcf87`)
  classifies `source_complete_physical_candidate`. The complete path costs
  `29020.1664668396 us/cycle` versus `66501.40993333333 us/cycle`, reduces
  the local family by `56.36157715162448%`, and derives
  `0.47717037100432264 s/request`, `0.02294891057067333 s/request` below the
  locked target. The CPU consumer matches direct exact-window evaluation to
  `4.440892098500626e-16`; every current token enters once and each expired
  token contributes zero.
- **Interpretation:** Rank 64 is the largest tested warp-aligned rank that
  clears the target. Rank 96 derives `0.5269826992323626 s/request`; a second
  rank-64 consumer pass derives `0.5119589561709748 s/request`. Those routes
  are closed. The positive result is analytical/source-backed, not a compiled,
  measured, or quality-qualified result.
- **Next move:** Director disposition. With a future authorized shared H200,
  train/distill the added per-layer feature projections, compile the exact
  one-pass consumer, and continue directly to profiler-off component and
  locked c32 endpoint measurement. Fail closed above 15.508249341718414%
  fallback, on a second consumer pass, or above rank 64; do not stack global-KV
  or prompt-state savings.
