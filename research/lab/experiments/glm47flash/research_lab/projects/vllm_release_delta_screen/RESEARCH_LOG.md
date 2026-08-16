# Research log

## 2026-07-15 — v0.25.1 exact-source and metadata screen

**Question.** Does one current pinned vLLM release provide an exact GLM-4.7-Flash AWQ/MoE or scheduler mechanism with a credible >=5% same-L40S cost path against the retained v0.15.0 runtime?

**Action.** Pinned the latest stable release available at the turn, v0.25.1 (`752a3a504485790a2e8491cacbb35c137339ad34`, published 2026-07-14), and compared targeted source paths with v0.15.0 (`f176443446f659dbab5315e056e605d8984fd976`). Inspected the cached current AWQ config/index only; no weights were loaded, no GPU or provider was used.

**Evidence.** The candidate registry still directly maps `Glm4MoeLiteForCausalLM` to `glm4_moe_lite`; its compressed-tensors scheme selects WNA16 for the exact `pack-quantized`, 4-bit, group-32, symmetric metadata. Candidate scheduler and OpenAI completion paths expose `max_model_len`, 65,536-token batching, high `max_num_seqs`, chunked/long-prefill controls, and prompt logprobs. The exact GLM-Lite source delta is only 10 added/9 removed lines. The larger GLM MoE delta is chiefly ROCm AITER fused shared-expert/generalized FusedMoE work, not an L40S mechanism. Generic scheduler and quantization refactors have no exact-model numeric result. Full machine-readable evidence is [VLLM_RELEASE_DELTA_SCREEN_2026-07-15.json](artifacts/VLLM_RELEASE_DELTA_SCREEN_2026-07-15.json).

**Interpretation.** Compatibility is statically positive, but no-fallback kernel selection and resident load are not provable without a GPU launch. More importantly, no source change or scope-matched upstream result supplies a credible >=5% L40S serving-wall path; frontend/interface compatibility is not an economic result. Close this runtime upgrade without paid A/B and preserve the current runtime denominator.

**Next move.** Spend remains reserved for the independent current AWQ control/batching line only if its diagnostics become interpretable; do not retry this runtime screen or claim v0.25.1 benefit from generic release churn.
