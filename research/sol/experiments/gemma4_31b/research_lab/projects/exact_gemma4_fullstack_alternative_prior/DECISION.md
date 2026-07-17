# Decision: one conditional alternative

Current primary evidence supports one route worth a direct falsifier: SGLang's merged Gemma 4 implementation (`2813cb6d9a5b6e8fb02435647917e6f1652d7940`, PR #21952) with BF16 weights and FP8 E5M2 KV cache. A public SGLang report serves `google/gemma-4-31B-it` in `lmsysorg/sglang:dev-gemma4` on 8 H20s (TP2/DP4) and reports 71.3167 decode tok/s and 1.8255 s end-to-end for a request. SGLang's own issue records Gemma 4 31B + FP8 KV as working while the failure is specific to E4B's shared-KV layers.

This is support evidence only. It does not bind the required checkpoint revision, image digest, campaign geometry, cost, or quality, and H20 throughput does not transfer to L40S or H100. The route is retained because changing engine avoids the repeated vLLM consumer-binding failure and is plausibly capable of a >=10% all-in improvement, but only a matched same-hardware complete-request run can promote it.

The executable falsifier is in `ALTERNATIVE_PRIOR.json`: bind the exact revision, immutable SGLang/runtime image, tokenizer/template, then run matched 4,214/358 plus 10K single-stream arms against pinned vLLM. Require SGLang cost/request <= 0.90x vLLM with complete telemetry and no worse raw-output/feature boundary; otherwise terminal typed `none`. No provider, weights, compilation, or quality execution occurred here.

Evidence: merged support [PR #21952](https://github.com/sgl-project/sglang/pull/21952), exact-31B/FP8-KV report [issue #22277](https://github.com/sgl-project/sglang/issues/22277), and current runtime report [issue #22510](https://github.com/sgl-project/sglang/issues/22510).
