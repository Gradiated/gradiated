# Research log

## 2026-07-17 — director admission

Activated as independent `$0` evidence after measured H200 linears-plus-head left only c16/c32 alive. The primary bound gives KV reads the full H200 peak bandwidth and a full 50-MiB per-step L2 credit; it cannot poll or delay the endpoint owner.

## 2026-07-17T12:24:00Z — deterministic KV floor terminal

- Question: does compulsory exact BF16 hybrid-attention KV read traffic exceed the residual c16/c32 H200 service budget?
- Action: reran `compute_kv_attention_floor.py` with current content-addressed geometry, measured linears-plus-head terminal, economic gate, and shared accelerator inventory. The calculation sums all 358 decode positions, 50 local layers at a 1,024-token window, 10 global layers, 8,192 BF16 K+V bytes/token/layer, ideal H200 4.8 TB/s, and a full 50-MiB L2 credit per step.
- Evidence: `KV_ATTENTION_FLOOR.json` identity assertions all pass. Both points read `278,976,512,000` bytes/request. Optimistic H200 floors are c16 `0.057875712` and c32 `0.057997909` seconds/request. Measured component floors are c16 `0.442462222` and c32 `0.224769590`; strict residuals are `0.029549601` and `0.247242233` against a `0.472011823` strict ceiling. c16's combined lower bound is `0.500337934` and exceeds both ceilings; c32's is `0.282767499` and fits. Zero-L2 H200 is `0.058120107`; H100 sensitivity is `0.083276571`.
- Interpretation: c16 is falsified by compulsory KV reads under an intentionally favorable physical bound. c32 is preserved, not endpoint-proven. The fixed L2 credit is amortized less efficiently at c32, but raw per-request traffic is batch-invariant.
- Secondary screen: the 20,480-to-18,432 global-QKV source-bound projection saves `0.352%` of strict service time at c16 and `0.181%` at c32, so the 5% CUDA-promotion threshold is not met.
- Next move: none in this project; the exact vLLM c16/c32 endpoint owner should retain only c32 as a viable operating point and measure the complete request path.
