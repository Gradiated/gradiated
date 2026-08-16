# Research log

## 2026-07-18 — director start

Opened a bounded execution completion after the conjunctive XQA/model proxy closed on its first real XQA CUDA call. This project does not retry that backend: it freezes the measured `0.08169989766753512` seconds/request projection and prompt-attention saving and asks whether supported Triton decode plus KV writes preserve a complete 5% head-256 architecture saving.

## 2026-07-18 — measured Triton completion

Snapshot the bound prior runner and prior `RESULT.json` locally before claiming `h200-attention-endpoint-e00vbbb709tzxscaan`; their SHA-256 values matched `4648fe...` and `5926b984...`. One H200 invocation of the pinned image measured only the remaining page-1, eight-split native-GQA Triton decode and BF16-to-E5M2 KV writes at c32/context 4,571. Candidate decode was 0.243136 ms versus 0.444256 ms current; candidate output was deterministic, finite/nonzero, avoided dense KV repetition, and passed the dequantized-cache native-GQA oracle (cosine `0.9999986291`, NRMSE `0.0020213884`). Completion changes the frozen partial saving from 81.700 ms/request to **104.250 ms/request** (11.338% of canonical 919.457 ms/request), exceeding the 45.973 ms gate. Typed evidence: `RESULT.json` and `artifacts/global-head256-triton-completion-20260718t2142z/RESULT.json` (SHA-256 `9ebc88...`). This is a non-quality-preserving nomination only; no checkpoint surgery, endpoint replay, or XQA retry was performed.
