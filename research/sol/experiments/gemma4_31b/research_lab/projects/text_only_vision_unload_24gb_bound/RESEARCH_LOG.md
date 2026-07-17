# Research log

## 2026-07-17 — director delegation

Activated as a materially different `$0` model/runtime-placement line. Determine whether text-only loading can exclude byte-exact vision-exclusive tensors without text changes and unlock a credible 24-GiB W4 placement. Return one direct nominee or typed none under 45 wall minutes, 1.5 CPU-hours, 1 GiB/128 MiB probes, and `$0`; no provider, CUDA, weights, compilation, quality execution, shared `/tmp`, or W4-owner polling.

## 2026-07-17 — exact bytes, runtime audit, and terminal bound

Question: can exact text-only vision unloading unlock 24-GiB W4 placement?

Action: parsed the exact safetensors headers using two bounded 16-MiB HTTP range reads (33,554,432 bytes total), audited pinned vLLM source `gemma4_mm.py`/`gemma4.py`, and recomputed primary and 10K c1/c2/c4/c8 capacity. No full weights, CUDA, provider, compilation, or quality execution.

Measured evidence: the index has 832 language-model tensors, 355 `vision_tower` tensors, and one `embed_vision` projection. Exact vision-exclusive BF16 bytes are 1,151,487,072 (1.072406 GiB), not the full 3.752517-GB residual. The exact config architecture is `Gemma4ForConditionalGeneration`; its pinned constructor unconditionally creates the vision tower/projector. The separate `Gemma4ForCausalLM` loader skips multimodal prefixes but is not selected by this checkpoint.

Derived evidence: hypothetical exact unload leaves 19.271088-GiB W4 resident weights. With 5-GiB reserve and source-bound FP8 KV, primary c1/c2/c4/c8 are 24.634511/24.997934/25.724781/27.178473 GiB; 10K is 24.856954/25.442820/26.614552/28.958015 GiB. All fail the 22.08-GiB conservative 24-card envelope; c1 exceeds nominal 24 GiB by 0.634511 GiB before allocator uncertainty.

Interpretation: typed `none`. The byte discontinuity is insufficient, the current runtime has no unload path, and no 24-GiB production prices or matched throughput exist. Bandwidth-only 10%-better candidate rate ceilings are $0.378/$0.756/$1.271 per hour for L4/A10/4090 before a conservative 15% efficiency haircut; these are priors, not nominations.

Next move: close this line. Reopen only with a measured text-only architecture adapter that preserves text outputs and a representation/reserve reduction large enough to put c1 below the conservative envelope; explicitly forfeit vision eligibility.
