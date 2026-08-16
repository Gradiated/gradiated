# Research log

## 2026-07-26T08:38:48Z — offline exact-geometry SM100 screen

Hypothesis: current SM100 consumers can execute the pinned Gemma 4 31B dynamic-FP8 transformer and its local-d256/global-d512 FP8-KV attention cheaply enough to clear `0.315609255362861553 s/request` on one B200.

Action: content-bound 33 files from current vLLM, FlashInfer, SGLang, TensorRT-LLM, CUTLASS, and Transformers revisions; implemented `materialize_sources.py` and the executable `b200_fp8_runtime_screen.py`; extracted all six transformer-linear families at M3679/M32/M384; and charged non-overlapping tensor, HBM, elementwise, launch, KV, tied-head, capacity, L2, and topology costs. No provider, GPU, or H100 action occurred.

Amendment: the first local discriminator exited before a result because its parser asserted an obsolete FP8 helper name. Current source used the equivalent dynamic per-token path under a comment contract. Only that assertion was repaired and the still-unconsumed offline discriminator was rerun.

Measured/derived evidence:

- **Source-backed:** vLLM maps SM100 dynamic E4M3 linears to its CUTLASS SM100 dispatcher; it exposes d256/d512 through FlashInfer TRTLLM-generation attention for both SM100 phases when Q/KV head ratios divide. Bound FlashInfer tests explicitly cover d512 prefill and decode with FP8 query/KV and BF16 output. Triton FP8-KV attention remains the fallback; FlashInfer's narrower standalone generic CUTLASS FMHA dispatcher is not selected.
- **Analytical:** exact runtime FP8 transformer weights are `29,396,828,160` bytes. Correct FP8 decode KV reads are `214,566,297,600` bytes/request, half the already-bound BF16 quantity. Model plus c32 max-context KV occupies `98,134,130,688` bytes before workspace on 180 GB B200 HBM; the full transformer cannot reside in 126 MB L2.
- **Inferred gate, not measurement:** after halving unlabeled vendor peaks to dense priors, requiring 65% of dense FP8, 50% of dense BF16, 75% of 8 TB/s HBM, and charging 1.75 us per source-counted launch yields `0.2995608884905333 s/request`. This clears the planning hurdle by `0.016048366872328246 s/request` (5.08%). The 70%-HBM sensitivity still clears at `0.30762505389091427`; 65% fails at `0.3169298601221231`.

Decision: `source_complete_b200_candidate`. This is a source/physical candidate, not B200 throughput or deployability. `B200_FP8_RUNTIME_SCREEN.json` contains the bounded later falsifier: one source-identified B200 component pass, same-B200 BF16 baseline, exact d256/d512 attention, numerical oracle, counters, 25-minute wall bound, and `$2.50` maximum future spend. It remains unauthorized until the director supplies both a shared compatible bench and positive spend reservation.
