# Research log

## 2026-07-17 — director delegation

Activated as independent `$0` evidence while the live lowercase L40S head owner runs. Derive the exact SGLang BF16+FP8-KV H100 c1–c32 capacity surface, reconcile the 1.825 req/s floor with the `$0.000614–$0.000621` hurdle and fresh H100 rates, and return one paid saturation ladder or typed none. Budgets are 35 wall minutes, 1 CPU-hour, 512/128 MiB storage, and `$0`; no polling or mutation of the live owner and no provider/weights/image/compile/CUDA/endpoint/quality work.

## 2026-07-17 — runtime-bound capacity and cost result

Question: which exact SGLang points are physically admissible before an H100 measurement? Action: inspected only the retained immutable config/source and shared inventories, then derived the FP8-KV surface and request-cost floors in `CAPACITY_COST_BOUND.json`. Evidence: the pinned `gemma4_causal.py` selects 16 KV heads and 256 dimensions for both layer types; it does not read the config's four-global-head/512-dimension fields. The immutable command's multimodal default yields an effective `mem_fraction_static=0.7605395703125` after the source's 13.125 GiB activation/graph/metadata reserve and VLM adjustment. At peak request residency, primary KV is 0.750995 GiB/request and 10K KV is 1.199329 GiB/request including a bounded scale sensitivity.

Interpretation: correcting the capacity calculation to the project-specified 80 GB decimal H100 yields typed none. The source-defined multimodal static cap is 55.851 GiB, 2.399 GiB below the exact 58.251 GiB checkpoint before c1 KV. Raw HBM capacity is not an executable admission because the immutable command cannot allocate its weight-plus-KV pool. The market-only floor remains 1.118–1.402 rps; 1.825 rps is a stricter independent packet gate, not a derivable market result. No provider or live-owner interaction occurred. Next move: do not create this H100 owner; a materially changed, separately content-bound configuration is required before any later provider admission.
