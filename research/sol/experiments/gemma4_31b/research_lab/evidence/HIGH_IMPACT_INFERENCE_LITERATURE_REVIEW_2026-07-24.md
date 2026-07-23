# High-impact Gemma 4 inference literature review

Date: 2026-07-24  
Decision: identify technically credible routes to a 20–50% reduction in Gemma 4
31B serving cost without reducing target-model quality  
Retrieval date for online sources: 2026-07-24

## Executive decision

The literature changes the next experiment priority.

The highest-value immediate experiment is **DFlash speculative decoding using the
already-published `z-lab/gemma-4-31B-it-DFlash` draft**. This is not a proposal to
train a speculative model. A 2B BF16 Gemma 4 31B-specific draft, SGLang and vLLM
integration instructions, and c32 measurements already exist. On one B300, its
authors report 1.9–3.8x c32 throughput versus their autoregressive comparator
across MT-Bench, code, and reasoning workloads. At unchanged GPU-hour price,
those ratios correspond to 47–74% lower compute cost per generated token.
Transfer to the lab's H200, FP8 target, exact workload, and current optimized
stack is unmeasured, so the result is a strong experiment lead rather than a
forecast.

Three routes clear the 20% plausibility bar:

1. **Lossless speculative decoding with the Gemma-specific DFlash draft.**
   This can remove target-model decode passes while preserving the target
   distribution. It is the fastest and strongest falsifier.
2. **A narrow operation-overlap data plane inspired by NanoFlow.** The lab's
   profile has large sequential synchronization, attention/KV, and FP8-linear
   regions. Overlapping those heterogeneous resources across nano-batches is a
   more credible rewrite than replacing the SGLang control plane.
3. **Persistent, prefix-aware KV service for agent and tool traffic.** This is
   exact reuse, not approximation. It may reduce real OpenRouter agent-session
   cost by 20–50% or more, but it will not improve a fresh-prompt Artificial
   Analysis benchmark and must therefore be measured on a separate product
   workload.

A QServe-style W4A8KV4 stack on L40S remains a credible 20–50% economic route,
but it is not yet a no-quality-loss result for Gemma. The lab's slow Marlin and
INT4 experiments do not refute this route: the QServe paper identifies
20–90% dequantization overhead in ordinary INT4 implementations and addresses it
with representation, kernel, and serving co-design. It requires a Gemma port
and later GPQA-Diamond/TauBench validation.

## Local evidence boundary

Measured local facts:

- Qualified E5M2 contiguous local-ring endpoint:
  `0.6556567115 s/request`, 32/32 requests, exact fresh-extend/decode transition
  checks.
- Incremental E4M3 tied-head endpoint:
  `0.6518282820 s/request`, a further 0.5839% reduction, without a broad quality
  claim.
- Current economic ceiling:
  `0.6381105231 s/request`.
- The scope-matched profile attributes 52.5196% of decode wall time to
  synchronization, 28.2473% of request wall time to attention/KV, and 22.9730%
  to FP8 linears. Older aggregate synchronization attribution is 36.5787%.
- H200 activity averaged about 97.3% and 564 W. This proves the GPU is busy; it
  does not prove tensor cores, HBM, and copy/scheduling resources are
  simultaneously saturated.
- Fixed-c32 multi-token graph attempts reduced 21 host boundaries to 3 and
  produced a conservative `0.6286271699 s/request` bound, but all attempted
  graph topologies failed exact position/request/KV/token state. The final raw
  forward graph matched only 144/704 tokens.
- The synthetic workload reports 17,120 cached of 134,848 prompt tokens
  (12.6958%). This leaves a potentially large workload-level prefix-reuse
  opportunity, but synthetic shared-prefix accounting does not estimate real
  agent-session locality.

Primary local records:

- `../projects/gemma4_h200_static_c32_multitoken_decode_engine/PROJECT.md`
- `../projects/gemma4_h200_static_c32_multitoken_decode_engine/STATUS.json`
- `../projects/gemma4_h200_v0513_fp8_qkv_residual_profile/RESEARCH_LOG.md`
- `../DIRECTOR_LOG.md`

## Ranked routes

| Rank | Route | Literature result | Transferable cost hypothesis | Quality status | Cheapest decisive experiment |
|---|---|---|---|---|---|
| 1 | Gemma-specific DFlash | 1.9–3.8x c32 throughput on Gemma 4 31B across reported B300 tasks; 2B draft is public | 20–50% lower H200 cost is credible if acceptance and verification stay favorable on the exact mix | Speculative decoding is algorithmically lossless; implementation equivalence must still be checked | Four-request acceptance/verification diagnostic, then one matched c32 AR/DFlash pair and comparison with `0.6518282820` |
| 2 | NanoFlow-style operation overlap | 1.91x throughput across several model families | 20–35% is plausible if Gemma attention/KV and FP8 work can overlap without destructive interference | Exact if dependencies and kernels are unchanged | Concurrent exact-shape attention + FP8-GEMM microbench and a resource-overlap trace |
| 3 | Persistent agent KV and prefix-aware routing | InferCept 1.6–2x throughput; CachedAttention up to 70% end-to-end cost reduction; CacheWise up to 3.5x session completion | 20–50% on multi-turn/tool traffic with sufficient repeated-prefix residency | Exact KV reuse; cross-tenant/privacy rules required | Replay TauBench-style multi-turn sessions with and without persistent content-addressed KV and report hit/recompute curves |
| 4 | QServe-like W4A8KV4 on L40S | 1.4x Llama-3-8B throughput on L40S; larger gains on Qwen-72B; 3x reported dollar efficiency versus A100 | 20–50% may be achievable through cheaper hardware plus full low-bit co-design | Not established for Gemma; requires QAT/QAD and benchmark validation | Port one exact Gemma M=32 MLP and local-attention pair with QServe-style reordering/fused dequant, then test a small endpoint |
| 5 | P/D disaggregation | Workload-dependent papers report material goodput gains | Could exceed 20% at scale under asymmetric prefill/decode load | Exact | Queueing simulation from production arrival/prompt/output distributions before any implementation |
| 6 | Architectural compression/retraining | Low-rank, MLA-like, width, and low-bit training can produce large savings | Potentially 20–50% | Not a no-quality-loss route until retrained and evaluated | Defer until exact runtime routes are consumed |

## 1. DFlash is the immediate priority

[DFlash](https://arxiv.org/abs/2602.06036) uses a lightweight block-diffusion
draft to propose many tokens in parallel, followed by target-model verification.
The paper reports more than 6x lossless acceleration in selected settings.

More importantly, the public
[Gemma 4 31B DFlash model card](https://huggingface.co/z-lab/gemma-4-31B-it-DFlash)
contains directly scope-relevant evidence:

- the draft is explicitly paired with `google/gemma-4-31B-it`;
- it is a 2B-parameter BF16 model;
- both vLLM and SGLang integration paths are published;
- at concurrency 32 on one B300, reported throughput speedups are 3.8x on
  Math500, 3.2x on GSM8K, 3.6x on HumanEval, 2.6x on MBPP, and 1.9x on
  MT-Bench;
- reported c32 accepted lengths range from 4.19 on MT-Bench to 8.62 on
  Math500.

The c32 result is unusually relevant to the lab's fixed-c32 economic objective.
Even the reported worst task, MT-Bench at 1.9x, implies a 47.4% same-hardware
cost reduction (`1 - 1/1.9`). This must not be transferred directly from B300 to
H200 or from the authors' runtime to the lab's FP8 stack.

The correct first experiment is:

1. Use the exact target checkpoint and public DFlash draft.
2. Start from the authors' supported SGLang or vLLM integration rather than
   porting it into pinned v0.5.13 before obtaining a signal.
3. Run a tiny exact-workload acceptance diagnostic. Record accepted length,
   draft time, target verification time, fallback frequency, HBM use, and
   end-to-end target forwards per emitted token.
4. Run one c32 autoregressive/DFlash pair in the same runtime.
5. Compare the DFlash absolute endpoint against the lab's
   `0.6518282820 s/request` stack, not only against the slower same-runtime
   baseline.
6. Require greedy token equality, exact cache/request accounting, and
   position/KV invariants. If sampled serving is later enabled, verify
   distributional correctness separately.

Suggested decision levels:

- continue integration if the absolute result is below
  `0.5214626256 s/request` (20% below the tied-head frontier);
- treat below `0.4562797974 s/request` as a strong 30% result;
- close the exact draft/runtime pair if target verification dominates and the
  measured absolute endpoint cannot beat the current stack.

Production-grade speculative decoding needs careful batch-state handling.
[Batch Speculative Decoding Done Right](https://arxiv.org/abs/2510.22876)
shows that ragged accepted lengths can desynchronize positions, masks, and KV
state, which is directly analogous to the lab's failed multi-token graph state.
[A recent vLLM study](https://arxiv.org/abs/2601.11580) also finds that target
verification often dominates and that acceptance varies substantially by token
position, request, and dataset. Therefore the public speedup is a high-value
falsifiable lead, not permission to skip exact batch-state evidence.

[EAGLE-3](https://arxiv.org/abs/2503.01840) is a fallback, not the first action.
It reports 1.38x SGLang throughput at batch 64, equivalent to 27.5% lower
same-hardware cost, but no equally direct public Gemma 4 31B draft was found in
this review.

## 2. The defensible rewrite is an operation-overlap data plane

[NanoFlow](https://arxiv.org/abs/2408.12757) argues that serving systems leave
throughput unused because compute, memory, and network operations execute
sequentially within a GPU. It splits work into operation-level nano-batches and
schedules heterogeneous resources concurrently, reporting 1.91x throughput and
59–72% of modeled optimal throughput on several Llama and Mixtral models.

This maps to the local trace better than a generic serving rewrite:

- attention/KV and FP8 linears are both large, physically different regions;
- synchronization is large;
- launch overhead alone is too small to justify a new runtime;
- high `nvidia-smi` utilization does not rule out resource-complementary
  overlap.

The first discriminator should not be a runtime rewrite. Run the exact dominant
attention/KV operation and exact dominant FP8 GEMM concurrently on separate
streams at c32, preserving outputs, and collect SM tensor-pipe, HBM,
occupancy/register, and elapsed-time counters. If concurrent elapsed time is no
better than roughly 85% of the serial sum, interference makes a 20% endpoint
win implausible. If it is at or below roughly 75–80%, build a model-specific
operation pipeline across c32 nano-batches.

The architecture should retain SGLang for API, request state, radix cache, and
admission control. Replace only the hot model-execution data plane. This avoids
rebuilding mature control-plane behavior while allowing fixed Gemma layer
groups, stable buffers, and explicit stream/resource scheduling.

## 3. Exact KV persistence may dominate real agent economics

Three independent sources support a workload-level opportunity:

- [InferCept](https://arxiv.org/abs/2402.01869) reports that tool/API
  interruptions cause 37–40% recomputation in augmented LLMs and reports
  1.6–2x serving throughput.
- [CachedAttention](https://arxiv.org/abs/2403.19708) persists KV across
  multi-turn conversations using a memory/storage hierarchy and reports up to
  87% lower TTFT, 7.8x prefill throughput, and 70% lower end-to-end cost.
- [CacheWise](https://arxiv.org/abs/2606.16824) studies coding-agent traces and
  reports 2–2.6x fewer KV evictions and up to 3.5x faster session completion
  using prefix-aware scheduling and reuse-aware eviction.

This is particularly relevant to OpenRouter tool and agent traffic. The provider
will usually receive the full accumulated conversation again. A
content-addressed prefix fingerprint can recover the exact prior KV state even
without a provider-specific session ID, subject to tenant isolation and privacy
policy.

This route needs its own scorecard:

- Artificial Analysis / fresh-prompt cost;
- fresh OpenRouter request cost;
- multi-turn agent-session cost with exact prefix reuse.

Combining them would hide whether an improvement comes from faster model
execution or from serving less duplicated work.

## 4. Low-bit co-design remains open despite local negatives

[QServe](https://arxiv.org/abs/2405.04532) reports that ordinary INT4 serving
can lose 20–90% to weight or partial-sum dequantization overhead. Its W4A8KV4
design combines progressive quantization, compute-aware weight reordering,
register-level parallelism, fused attention, and SmoothAttention. It reports
1.4x Llama-3-8B throughput on L40S and larger gains for Qwen-72B.

This explains the local evidence:

- slow W4 Marlin at the exact Gemma M=32 shape, with high register/shared-memory
  pressure, is evidence against that kernel realization;
- slow/inaccurate local KV INT4 is evidence against that pack/dequant/attention
  realization;
- neither result proves that a jointly designed W4A8KV4 Gemma path is
  physically impossible.

However, QServe does not establish unchanged Gemma 4 GPQA-Diamond or TauBench
quality. Treat this as a separate model/hardware co-design program. It earns a
full endpoint only after exact-shape component gains and a credible quality
recovery plan.

## What not to prioritize

- **Another generic SGLang/vLLM swap.** Current-runtime comparisons were already
  slower and do not attack the measured mechanism.
- **Launch-only fusion.** Launch overhead is too small for a 20% result.
- **B200/NVFP4 solely for faster GEMMs.** The current price ratio and measured
  FP8-linear wall share make a 20% all-in economic win unlikely without a much
  broader Blackwell-specific stack.
- **More host/device multi-token graph repair.** Four materially distinct
  topologies failed exact state. DFlash changes the algorithm and has a trained
  draft; it is not another repair of that lineage.
- **Quality-unsafe width removal as a final answer.** It exposed a cost floor but
  the attempted low-rank recoveries remained incoherent.

## Recommended order

1. Run the Gemma 4 DFlash acceptance diagnostic and one matched c32 endpoint.
2. In parallel, run the exact-shape attention/FP8 overlap discriminator.
3. Build a turn-aware TauBench/agent-session KV-reuse benchmark and measure
   persistent-prefix economics separately from Artificial Analysis.
4. Start a QServe-style Gemma/L40S component port only if the first three routes
   do not reach the target or if later quality recovery is acceptable.

This order maximizes information per GPU-hour: the first route is already
implemented upstream, the second can reject or justify a rewrite with one
microbenchmark, and the third can be evaluated by replay before building a
distributed cache.

## Evidence classification and limitations

- Local endpoint/profile values: **measured**, scope-matched to the lab's H200
  campaign unless noted.
- Paper/model-card speedups: **author-reported**.
- Cost reductions derived from speedup: **derived**, assuming unchanged
  GPU-hour price and sufficient load.
- Expected transfer to H200/Gemma FP8: **inferred** and unverified.
- No paper result is treated as proof of OpenRouter GPQA-Diamond/TauBench
  parity.
- DFlash's public c32 numbers use B300, thinking mode, up to 4,096 generated
  tokens, and the authors' runtime. The lab uses H200, a fixed 358-token output,
  its own prompt/cache mix, and a tuned FP8 stack.
- CachedAttention/InferCept/CacheWise improve repeated-work economics, not the
  fresh-prompt AA benchmark.

## Source index

- Chen et al., “DFlash: Block Diffusion for Flash Speculative Decoding,” ICML
  2026 camera-ready: https://arxiv.org/abs/2602.06036
- Public Gemma 4 31B DFlash draft/model card:
  https://huggingface.co/z-lab/gemma-4-31B-it-DFlash
- DFlash implementation: https://github.com/z-lab/dflash
- Li et al., “EAGLE-3,” 2025: https://arxiv.org/abs/2503.01840
- Liu et al., “Speculative Decoding: Performance or Illusion?”, revised 2026:
  https://arxiv.org/abs/2601.11580
- Zhang et al., “Batch Speculative Decoding Done Right,” revised 2026:
  https://arxiv.org/abs/2510.22876
- Zhu et al., “NanoFlow,” revised 2025:
  https://arxiv.org/abs/2408.12757
- Lin et al., “QServe,” revised 2025:
  https://arxiv.org/abs/2405.04532
- QServe/OmniServe implementation:
  https://github.com/mit-han-lab/omniserve
- Abhyankar et al., “InferCept,” 2024:
  https://arxiv.org/abs/2402.01869
- Gao et al., “CachedAttention,” USENIX ATC 2024:
  https://arxiv.org/abs/2403.19708
- Tiwari et al., “CacheWise,” 2026:
  https://arxiv.org/abs/2606.16824

