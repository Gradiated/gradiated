# Research log

## 2026-07-26T10:22:41Z — one-tile global-KV candidate

Question: can old global K/V alone close the locked 20% target while every
token still traverses all 60 full-width layers and every 1,024-token local
window stays exact?

Action: hash-bound the exact config, M384 c32 trace, pinned Gemma/backend/kernel
source, and prior subtype map; joined all 900 `_fwd_kernel` calls by source
shape, shared memory, and repeated layer order; implemented incremental
post-RoPE K/V summaries, protected/recent exact tiers, multiplicity-aware
causal attention, ordinary prefill, TARGET_VERIFY, decode, and a fused
one-tile Triton consumer. Ran dependency-free geometry/information-path tests
and the complete physical screen. The coordinator lacks Torch/CUDA, so the
consumer was source-audited and syntax-checked but not compiled or timed.

Evidence: every one of 15 cycles is `LLLLLG` repeated ten times: 750 local
calls sum to `997,521.149 us`; 150 global calls sum to `490,684.609 us`.
The selected 512-token summary / 8 recent / 8 protected design needs at most
57 compact entries in any claimed 32-row phase and 37 in the locked
12-token verifier, so it stays within one 64-key tile. Charging the fused tile
at 1.5x trace-linear cost, 256,901,120 bytes of worst-case summary and compact
traffic at 3x the impossible H200 HBM floor, and `110 us/cycle` of explicit
fixed overhead yields `0.4999581203857146 s/request`, a
`0.00016116118928138912 s/request` target margin. Artifact:
`MULTIRESOLUTION_GLOBAL_KV_PHYSICAL_SCREEN.json`
(`1d7d59a96a50f95b8cbadbb763ee072b5a4c462e1bb03f039dccda3905c84a30`).

Interpretation: `source_complete_physical_candidate`, intentionally
semantics-changing and quality-unqualified. The candidate is brittle:
256-token summaries, a 16-token recent tier, or 16 protected positions require
two tiles and miss; fallback must remain below `0.128732%`. No prompt-state,
local-attention, token/layer/width, or late-GEMM savings were credited.

Next move: only under a later GPU admission, compile the fused consumer on the
pinned H200 runtime, verify the real producer/consumer and request ownership,
measure profiler-off component and exact c32 endpoint timing, and reject on a
second tile or fallback above the bound before quality recovery.
