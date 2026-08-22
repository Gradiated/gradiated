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

## 2026-07-28T21:05Z — invalid FP8-layout invocation; no scientific sample

Question: execute the director-bound exact B200 BF16-versus-dynamic-E4M3 linear and BF16-KV-versus-FP8-KV component generation.

Action: claimed `b200-nvfp4-computeinstance-i00rqcq5yzr6xc991j` at 21:03:30Z, hash-bound the three admitted packet files, and launched the controller-host durable owner at 21:05:19Z. The remote B200 was identified as SM100 and loaded `flashinfer 0.6.6`; no checkpoint or endpoint was loaded.

Evidence: the first E4M3 linear smoke entered `torch._scaled_mm` but cuBLASLt rejected the row-major B operand: `Only multiplication of row-major and column-major matrices is supported by cuBLASLt`. The retrieved terminal is `B200_FP8_RUNTIME_FALSIFIER_TERMINAL.json`; it contains no completed warmup or 40-sample timing distribution, numerical comparison, attention arm, counter set, or aggregate. This is a layout integration defect, not support or performance evidence. The packet amendment changes only B to the required column-major `[N,K]` view (`w8.t()`).

Disposition: the owner wrongly released the otherwise safe bench after this non-interpretable terminal, contrary to the same-claim repair contract. It is now available but must be explicitly re-readied by the director before any retry; this researcher did not reclaim or replay it. Conservative director-assigned exposure through the watchdog is `$2.422094841625`, below the `$2.50` reservation. No candidate conclusion is valid.

## 2026-07-28T21:20Z — exact pinned consumer incompatibility

The re-authorized B200 repair bound the actual vLLM `fp8_utils.cutlass_scaled_mm` consumer, which completed first-call markers for all six linear families at M32, M3679, and uncharged M384. The exact FlashInfer 0.6.6 TRTLLM-generation context consumer then rejected the required local q32/kv16/d256/context1024/page16 arm with `Missing TRTLLM-GEN kernel (context)`. This is the director-required consumer and geometry, not an SDPA proxy, so it closes the current pinned-runtime candidate as `typed_none`. The healthy B200 was released available; terminal: `B200_FP8_RUNTIME_CONSUMER_REPAIR_TERMINAL.json`.

## 2026-07-28T21:30Z — fund and bind native Triton FP8-KV fallback

The `$6` total reservation is durable. One authenticated provider/guest revalidation found the exact RUNNING B200 and READY disk, strict SSH identity, SM100 device, cached pinned image, zero running containers, and no model server. The director replaced the `21:33Z` watchdog with `gemma4-b200-triton-fp8kv-20260728t2125z-watchdog.service` through `22:20Z`, reconciled inventory, and only then stopped the predecessor. Conservative total project exposure is `$5.516262`, below the ceiling.

Bind `DIRECTOR_B200_FP8_TRITON_EXECUTION_20260728T2129Z.json`. It preserves exact vLLM CUTLASS dynamic-E4M3 linears and changes only the attention consumer to source-bound `TritonAttentionImpl.forward`, `triton_reshape_and_cache_flash`, and `unified_attention` with native E4M3 KV. Claim by `21:35Z`, launch the durable owner by `21:43Z`, persist linear/local/global stages atomically, and release a decision-bearing result by `22:08Z`. The consumed FlashInfer incompatibility, SDPA, materialized dequantization proxies, model loading, and endpoint work are forbidden.

## 2026-07-28T22:08Z — re-ready the zero-row block API repair

The block-scale owner launched durably, but its first invocation bypassed vLLM's registered wrapper and called an absent `torch.ops._C.cutlass_scaled_mm`. A repair attempt then reached `vllm._custom_ops.cutlass_scaled_mm` but passed the scale/output fields positionally in the wrong order, leaving `out_dtype=None` at the wrapper assertion. Both terminals contain zero rows and no returned candidate output, completed warmup, timing sample, or numerical comparison. They are implementation diagnostics, not a block-E4M3 result.

Bind `DIRECTOR_B200_FP8_BLOCK_API_REPAIR_20260728T2208Z.json` and explicitly re-ready the released safe B200. Preserve the exact 1x128 activation and 128x128 weight representation, bind the installed `QuantFP8` scale layout and `CutlassFp8BlockScaledMMKernel.apply_block_scaled_mm` API, and use keyword arguments at the registered wrapper boundary. Claim by `22:13Z`, launch a repair-capable owner by `22:14:30Z`, and release a decision-bearing result by `22:18Z`. The `$6` ceiling and `22:20Z` watchdog are unchanged.

## 2026-07-28T22:07Z — block-scale integration defect; zero scientific rows

Claimed the director-bound B200 at 22:03:48Z and launched a hash-bound block-scale owner at 22:05:10Z. Its first attempt used the wrong `torch.ops._C` namespace; inspection of the pinned image identified `vllm._custom_ops.cutlass_scaled_mm`. The in-claim repair then reached that installed wrapper, but passed its arguments positionally and hit the wrapper's BF16 identity assertion before any warmup or timing sample. `B200_FP8_BLOCK_PAIR_TERMINAL.json` records zero rows and both raw owner artifacts are retained. These are launcher/API defects, not evidence about 1x128/128x128 E4M3.

The repair owner incorrectly released the safe B200 at 22:06:45Z. Per the lifecycle contract, this researcher did not reclaim it; director re-readiness and a fresh owner envelope are required before correcting the keyword call and running the one still-unconsumed generation.

## 2026-07-28T22:14Z — exact block-scaled CUTLASS negative

The API-repair claim began at 22:11:43Z. The installed `vllm._custom_ops.cutlass_scaled_mm` signature was bound by keyword, then a same-claim column-major repair gave B and its scale matrices stride-0 equal to one. This completed the only allowed 18-row BF16-versus-1x128/128x128 E4M3 pair with 8 warmups and 40 samples per arm. All rows used the registered vLLM boundary; no attention, tensor-scale, endpoint, model, or proxy work occurred.

Measured: every numerical gate failed (cosine `0.980321-0.982364`, NRMSE `0.192218-0.203493` versus requirements `>=0.999` and `<=0.03`), while summed p50 rose from `4.040352` ms BF16 to `13.980544` ms block-E4M3. This closes only the exact 1x128 activation/128x128 weight E4M3 representation. `B200_FP8_BLOCK_PAIR_TERMINAL.json` SHA-256 is `aa1c3857a00e253fa35df8f4efdee37b2b491314e69a2630b9c15fd3519cd2af`; the owner released the healthy bench ready at 22:14:02Z.

## 2026-07-28T22:22Z — installed QuantFP8 block producer negative

The official producer claim invoked installed `QuantFP8(static=False, GroupShape(1,128), use_ue8m0=False, column_major_scales=True)` for every activation before the registered vLLM CUTLASS consumer. The complete 18-row pair is interpretable. Cosine passed (`0.999309-0.999320`), but all NRMSE values (`0.036876-0.037155`) exceed the `0.03` gate and summed p50 regressed from `3.978400` ms BF16 to `13.971168` ms FP8. This closes the installed official block-E4M3 producer/consumer; terminal `B200_FP8_BLOCK_OFFICIAL_PAIR_TERMINAL.json` SHA-256 `7de8dc1b0c6c496e598088e21c6c9670af046bcb5467e27d9b38455070d20868`.
