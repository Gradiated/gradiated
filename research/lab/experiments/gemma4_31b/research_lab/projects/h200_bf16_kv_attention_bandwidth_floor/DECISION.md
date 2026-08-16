# Decision

## 2026-07-17 — deterministic hybrid-attention KV floor

Question: do compulsory exact BF16 KV-cache reads consume the residual H200 service budget left by the measured transformer linears plus the actual `ParallelLMHead`?

Action: reran `compute_kv_attention_floor.py` against the bound geometry, reconciled H200/H100 inventory values, the measured component terminal, and the economic gate. The calculation covers all 358 decode positions from the 4,214-token prompt, 50 local layers with a 1,024-token window, and 10 global layers. The primary bound uses reads only, ideal 4.8 TB/s H200 bandwidth, and subtracts a full 50-MiB L2 credit on every batch step.

| point | exact read bytes/request | optimistic H200 KV floor | strict residual after linears+head | result |
|---|---:|---:|---:|---|
| c16 | 278,976,512,000 | 0.057875712 s | 0.029549601 s | falsified |
| c32 | 278,976,512,000 | 0.057997909 s | 0.247242233 s | preserved, not proven |

The c16 combined lower bound is 0.500337934 s/request, above both strict and lenient ceilings (`0.472011823` and `0.477513644`). c32's combined lower bound is `0.282767499` s/request, so it survives this compulsory-read test. Zero-L2 H200 gives `0.058120107` s/request at both batches; the H100 3.35-TB/s sensitivity is `0.083276571` s/request. KV writes, attention arithmetic, achieved-bandwidth loss, competing weights, prefill, scheduling, and service overhead are excluded and can only increase the real cost.

The stock-runtime `attention_k_eq_v=true` screen is closed: replacing executed global QKV width 20,480 with a distinct 18,432-row specialization projects only `0.001662552` s/request at c16 (`0.352%` of strict market service time) and `0.000853114` s/request at c32 (`0.181%`), below the 5% promotion threshold. This is a source-bound projection, not a kernel result.

Decision: close c16; preserve c32 as the sole high-batch endpoint candidate for the active exact vLLM owner. No provider mutation or successor is authorized by this project.

Evidence boundary: this artifact is a deterministic physical lower bound. It does not establish attention-kernel efficiency, latency, throughput, quality, or endpoint economics.
