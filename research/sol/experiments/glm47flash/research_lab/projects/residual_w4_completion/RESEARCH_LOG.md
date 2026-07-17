# Research log

No researcher result yet. Test completion of the checkpoint's native W4 scheme across the ignored stock-serving BF16 residual; return an exact loader/dispatch and endpoint/c32 falsifier, not a full conversion or training plan.

## 2026-07-15 — Native W4 residual screen closes without paid nomination

Question: can the existing compressed-tensors W4A16 group-32 path absorb the ignored head, dense layer-0 linears, and stock-serving shared experts strongly enough to justify one L40S session?

Action: added and ran [`residual_w4_completion.py`](residual_w4_completion.py), which reads every local safetensors header, restricts stock serving to layers 0–46, derives the checkpoint's native `weight_packed`/BF16 `weight_scale`/`weight_shape` tensors, binds the current compressed-tensors config, and emits [`residual_w4_completion_bound.json`](residual_w4_completion_bound.json). The source-bound synthetic fixture covers exact c16 shapes and the retained vLLM Marlin/Marlin-MoE dispatch names. No checkpoint conversion, provider mutation, GPU, or quality run.

Evidence (measured headers): the residual is 147 BF16 linears / 1,594.5 MiB: head 605.0 MiB, shared experts 828.0 MiB across 46 layers, and dense layer-0 residual 161.5 MiB including attention. Native group-32 packing projects to 448.46 MiB and saves 1,146.04 MiB. Head-only and shared-only scopes are exact group/tile legal. The all-residual scope has one exact shape hazard: `model.layers.0.self_attn.kv_a_proj_with_mqa.weight` is `[576,2048]`, not a 128-wide output tile; it fails the conservative Marlin tile gate. The actual checkpoint also has no packed tensors for these ignored weights, so this is a derivation target, not loader evidence from a converted model.

Evidence (derived economics): applying the retained 14.09% head and 7.10% shared/standard-Marlin interval ceilings to the impossible assumption that all corresponding W4 byte savings transfer to endpoint wall time gives 631.46 tok/s, above the 594.466 target. This is intentionally non-conservative: no trace establishes residual byte limitation, and the c16 control is already 535.286 tok/s at 98.36% mean GPU utilization. A linear projection of the retained c32 46,875.7 MiB peak minus 1,146.04 MiB gives 45,729.7 MiB, so c32 is nominally memory-admissible only; no c32 throughput or kernel evidence exists.

Interpretation: the representation has enough ideal byte headroom, but the all-scope exact dispatch gate fails on layer-0 KV-A geometry and the endpoint gate is unsupported by measured transfer. Memory-only c32 admission does not meet the portfolio nomination rule. The native residual-W4 lane is closed at zero spend; do not convert the checkpoint or open a paid matched session. Reopen only with a source-supported non-128 tile path for `[576,2048]` plus a measured residual critical-path or c32 throughput bound.
