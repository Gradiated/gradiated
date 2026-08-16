# Research log

No researcher result yet. Quantify and implement one whole-block depth proxy; do not run a provider or broaden into training or final quality evaluation.

## 2026-07-15 researcher result

Question: can a small complete-block removal set clear the 10% L40S cost gate or create a useful c32 memory discontinuity without provider spend?

Action: parsed every AWQ safetensor header, joined exact payload bytes by loaded layer, reused the retained L40S decode trace, and added [`run_depth_bound.py`](depth_bound.json) plus the shape-preserving [`depth_proxy.py`](depth_proxy.py). The proxy is fail-closed in stock mode and requires an explicit `semantic_proxy=True` for bypasses; its self-test passes.

Evidence (derived exact headers + measured trace): the checkpoint contains layers 0..47 (one dense plus 47 sparse) although config reports `num_hidden_layers=47`; bounds use the loaded tensor identity. A five-layer evenly spaced sparse pattern `[6,15,24,33,42]` removes 1.728 GiB of AWQ payload and 0.703 GiB of c16 MLA state at 16 sequences × 8,192 tokens. The retained trace has 160,911 decode kernels and 2,500.06 ms summed kernel work; MLA is 42.9%, dense GEMM 29.3%, and MoE routing 3.2% of summed work. The five-block linear speed/cost calculation is only an optimistic upper bound: 597.5 tok/s and $0.511/M output versus 535.286 tok/s and $0.571/M baseline, or 10.42% lower cost. Summed kernel durations overlap and do not establish endpoint savings.

Capacity: with retained 42,827 MiB c16 peak and 46,068 MiB card capacity, the derived c32 MLA-only threshold needs at least 13 sparse blocks removed; five saves only 1.406 GiB at c32. A 32-GiB tier would require substantially more than a small set after weights and runtime overhead. No quality or recovery evidence exists.

Decision: close depth reduction for now. The five-block candidate barely clears an optimistic arithmetic gate, does not cross c32, and has no modest-recovery evidence; nominate no paid follow-up. Return the slot to early-exit or trained draft-head work. Artifact: [`depth_bound.json`](depth_bound.json).
