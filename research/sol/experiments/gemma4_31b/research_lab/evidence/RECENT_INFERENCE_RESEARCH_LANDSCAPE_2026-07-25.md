# Recent inference research landscape and Gemma 4 implications

Date: 2026-07-25

## Question

What inference work published in the last six months reports substantial
speedups, where has the field been looking, and which mechanisms are most
likely to transfer to the measured Gemma 4 31B H200 workload?

## Executive decision

The wide search changes the immediate Gemma portfolio in two useful ways:

1. **Adaptive speculative verification should become part of the primary
   route, not a later scheduler optimization.** D-Cut and DSpark independently
   show that long parallel drafts waste target compute at high concurrency and
   that verification depth must be selected jointly across the batch using
   acceptance confidence and a hardware-specific cost model. This maps almost
   exactly to Gemma's c32, depth-12 target-verification workload.
2. **The 262k-vocabulary output head is an overlooked independent target.**
   FlashHead reports up to 1.75x model-level speedup on Llama-3.2, Gemma-3, and
   Qwen-3 by replacing dense vocabulary classification with structured
   retrieval. Gemma 4's trace contains 180 depth-sliced tied-head launches in
   15 verifier cycles, so a Gemma-specific exact top-k/retrieval discriminator
   is warranted before assuming attention is the only large kernel opportunity.

The most credible route to another 20% on the current qualified endpoint is a
**stack**, ordered as follows:

1. repair lossless parallel drafting and add D-Cut/DSpark-style adaptive
   verification at c32;
2. specialize or replace the large-vocabulary output head and fuse its
   sampling/verification tail;
3. apply packed Hopper attention plus deep SwiGLU/GEMM fusion to the target
   verifier;
4. evaluate hardware-specific W4A4 or sparse execution on the chip where the
   arithmetic balance supports it, rather than presuming H200 is best.

No single recent generic attention paper establishes a transferable 20%
whole-request improvement for this workload. Attention is only
`17.03-19.42%` of the whole request even under the impossible assumption that
the measured target-verification attention family is eliminated entirely.

## Search scope and reproducibility

Window: 2026-01-25 through 2026-07-25.

The initial inventory used the arXiv API query:

```text
submittedDate:[202601250000 TO 202607252359] AND
(all:"LLM inference" OR all:"language model inference")
```

The query returned 666 records. Title-plus-abstract keyword screening produced
the following overlapping signals:

| Broad signal | Records |
| --- | ---: |
| serving, scheduling, batching, or caching | 369 |
| quantization, pruning, or sparsity | 172 |
| hardware, chip, accelerator, or near-memory work | 161 |
| attention, KV cache, or context sparsity | 131 |
| kernels, fusion, CUDA, or collectives | 109 |
| speculation, drafting, multi-token, or parallel decoding | 101 |

These are deliberately high-recall keyword counts, not a taxonomy or evidence
that every record is relevant. They show that recent inference work is spread
across the whole stack rather than concentrated in attention kernels.

The second pass retained work that met at least one of these criteria:

- author-reported end-to-end improvement around 15% or greater;
- a much larger component speedup on a component visible in the Gemma trace;
- a new model/system mechanism that can remove full target passes;
- a hardware-specific result that changes the chip-selection decision;
- a negative result that changes how a promising route should be evaluated.

All paper results below are **author-reported** unless explicitly labeled
local, derived, or inferred. Most are arXiv preprints and are not independently
replicated here.

## Where the field has been looking

### 1. Parallel generation and speculative decoding

This is the most active source of large end-to-end claims. The research has
moved beyond “attach a small autoregressive drafter” in four directions:

- generate a whole block or tree in one forward pass;
- restore causal dependence between parallel draft positions;
- adapt draft/verification geometry to confidence, load, and hardware;
- overlap likely future drafting with target verification.

Representative recent results:

| Work | Mechanism | Reported result | Transfer to Gemma |
| --- | --- | --- | --- |
| DFlash | one-pass block-diffusion draft | large lossless speedups; Gemma checkpoint exists | high after the current integration/KV-commit bug is fixed |
| JetSpec | causal, branch-conditioned tree from one forward | up to 9.64x on MATH and 4.58x chat on H100 | high-upside Gemma-specific drafter fallback |
| DominoTree | conditional tree over parallel drafts with GPU-native builder | up to 6.6x AR; 9-10% over Domino overall | useful after a correct parallel drafter exists |
| D-Cut | prune verification depths jointly across concurrent requests | speculative speedup rises from 1.26x to 1.65x; up to 3x AR on MoE | **directly relevant to c32 verification waste** |
| DSpark | semi-autoregressive draft plus confidence/load-aware verification | 60-85% faster per-user generation than MTP-1 at matched throughput in DeepSeek-V4 serving | strongest production evidence for adaptive c32 geometry |
| EntMTP | entropy-conditioned choice among speculation trees | 1.15x over Hydra; peak 1.36x over Medusa | low-cost controller idea, weaker upside |
| Saguaro | pre-draft likely verification outcomes during verification | up to 2x over optimized speculative decoding | relevant only if draft remains on the critical path after Spec-v2 |
| Progressive Tree Drafting | training-free, model-agnostic in-model tree drafting | up to 2x decoding | useful low-training fallback, needs exact Gemma cost test |

The negative PEFT-BD result is equally important: accepted prefixes do not
create speedup if the drafter runs a verifier-scale backbone. Draft quality,
draft cost, target verification cost, and batch capacity must be measured
together. This supports repairing the existing five-layer DFlash route but
argues against any “lightweight-parameter” drafter that still executes most of
Gemma.

**Gemma implication:** native NGRAM already accepts nearly all 12 proposals, so
better NGRAM proposal quality is not the problem. The opportunity is to stop
paying a fixed 12-token verification shape for every request. Record
per-request survival probability at each depth and benchmark a joint c32
verification budget for depths 4/8/12/16. The controller objective should be:

```text
completed accepted tokens /
(measured draft GPU time + measured batched verification GPU time)
```

This is a semantic-preserving systems change when the verifier and commit path
are implemented correctly.

### 2. Attention, KV layout, and context sparsity

Recent attention research is splitting into three regimes:

- chip-specific dense attention pipelines;
- packed/load-balanced batched attention and KV layouts;
- extreme sparse attention for long contexts.

FlashAttention-4 is the clearest hardware co-design result: Blackwell doubled
tensor-core throughput without proportionally scaling softmax/exponential and
shared-memory resources, so the authors changed both algorithm and pipeline,
including software-emulated exponentials and 2-CTA MMA. It reaches up to 1.3x
cuDNN and 2.7x Triton on B200. It is a B200 lesson, not an H200 kernel to copy.

PackInfer is more directly aligned with c32. It packs heterogeneous query/KV
regions into balanced execution groups, co-locates shared-prefix requests, and
uses group-contiguous KV layouts. It reports 13.0-20.1% lower inference latency
and 20% higher throughput than FlashAttention.

SpecSA co-designs sparse attention with speculative verification and reports
up to 6.86x kernel speedup and 3.49x end-to-end throughput over autoregressive
NSA decoding on H100. Its key lesson is that query-specific sparsity can
destroy the cross-query reuse needed by speculative verification; sparsity
must be selected and fused for the verifier geometry, not bolted on afterward.

Inference-time context sparsity reports up to 10x sparse-decode-kernel speedup
over FlashInfer at 50x sparsity on H100. This is interesting for long contexts,
but the current workload is about 4.2k input tokens and Gemma already has 50
sliding-window layers and only 10 global layers. It is not the first route for
this benchmark.

**Gemma implication:** build the current M384 verifier kernel around packed
c32 work, exact q-length 12, the 50 local/10 global split, and direct paged-FP8
KV consumption. A 2x speedup to all measured target attention projects to only
about `8.5-9.7%` whole-request improvement, so this is a stack component rather
than the sole 20% project.

### 3. Output head, sampling, and verification tail

This category is smaller but unusually relevant to Gemma.

FlashHead reframes the dense vocabulary projection as structured retrieval
using balanced clusters, multiprobe search, selective quantization, and a
sampling scheme that can reach beyond only the top tokens. It reports up to
1.75x model-level speedup while maintaining output accuracy on Llama-3.2,
Gemma-3, and Qwen-3.

SonicSampler vertically fuses logit processing, penalties, top-k/top-p/min-p,
sampling, and speculative verification into CUDA-graph-compatible Triton
kernels. It reports up to 10x for hierarchical top-k and up to 16x over
sampling-pipeline baselines. Those are component results, not 16x whole-model
speedups.

**Gemma implication:** the campaign has a 262k vocabulary and a depth-sliced
tied head. First measure the head plus sampling/acceptance share over the exact
c32 verifier trace. Then run two independent component discriminators:

1. exact hierarchical top-k and verification fusion, preserving the current
   logits/token contract;
2. FlashHead-style clustered retrieval, initially measuring top-k recall and
   GPU time before any endpoint quality claim.

The first can be bit/token exact. The second is likely distribution-preserving
only approximately and therefore needs later GPQA-Diamond/TauBench
qualification, but it is not an obviously quality-destroying architecture
change and is directly validated on the prior Gemma family.

### 4. Deep operator fusion and persistent execution

Recent work is moving past one-epilogue fusion toward tile-level and
cross-operator scheduling:

- Tile-Level Activation Overlap fuses SwiGLU into Hopper GEMM at tile
  granularity, overlaps Swish with operand loading/stores, reaches 79.5% peak
  BF16 utilization, and reports up to 2.47x over PyTorch on H100 Qwen MLPs.
- DeepFusionKernel targets the HBM traffic and cache reuse of SwiGLU blocks and
  reports up to 13.2% end-to-end over SGLang on H100.
- Ada-MK hoists a fixed serving DAG's scheduling decisions to compile time and
  reports up to 23.6% over TensorRT-LLM and 50.2% over vLLM at batch one on
  L20.

These results validate hand-designed tile/dataflow work where `torch.compile`
cannot reproduce the fusion, but their deployment regimes differ. Ada-MK's
main win is launch overhead at batch one; the Gemma c32 trace says queued GPU
work dominates. DeepFusionKernel and tile-level SwiGLU are more relevant
because they reduce HBM materialization and improve cache reuse inside large
MLPs.

**Gemma implication:** profile the exact FP8 gate/up–activation–down boundary,
not isolated GEMMs. Pursue tile-level activation overlap and fused residual
epilogues only if the materialized SwiGLU/intermediate traffic is visible.
Treat the persistent executor as a later stack project spanning norm,
quantization, projection, activation, residual, head, and acceptance—not as
another attention tile-size sweep.

### 5. Quantization and sparsity as hardware co-design

The strongest recent low-bit result is not “4-bit is always faster”; it is
that the correct low-bit format depends on the balance between tensor cores,
CUDA cores, dequantization, and memory.

APEX4 identifies the tensor-core/CUDA-core throughput ratio as a primary
predictor of W4A4 viability. It reports up to 1.66x end-to-end on L40S, 2.09x
on A40, but only 1.20-1.40x on A100 after mixed-granularity repair. This
explains why a generic Marlin W4A16 failure on H200 does not settle the W4A4
question, while also warning that H200 may be the wrong chip for
dequantization-heavy INT4.

Moderately Unstructured Sparse Weights uses sparse tensor cores plus CUDA
cores and reports up to 1.41x end-to-end over FlashLLM. SpenseGPT instead
combines a 2:4 sparse region with a dense residual and reports 1.2x
end-to-end on B200 FP8 while preserving accuracy.

SharQ combines dynamic activation sparsity with FP4 and reports 1.2-1.4x
throughput over FP8 on RTX 5090. Multi-Scale Dequant avoids lifting low-bit
weights to BF16 by decomposing activations, but currently provides analytical
and numerical evidence rather than scope-matched NVIDIA endpoint results.

**Gemma implication:** reopen low bit only as a chip-format-kernel package:

- L40S/A40: APEX4-style W4A4 is a credible cost experiment because the
  hardware balance is favorable and hourly prices can be much lower;
- B200: FP4 plus structured sparsity is credible, with FlashAttention-4 for
  attention;
- H200: keep FP8 as control and require an exact-shape component roofline
  before another endpoint. Do not assume W4 wins merely from reduced HBM
  bytes.

These routes alter numerical behavior and require eventual product-quality
qualification. They are valid early performance experiments if labeled
accordingly.

### 6. Model-architecture search and dynamic compute

Recent work is making architecture changes cheaper to discover:

- DASH searches FA/SWA placement with frozen operator weights in about 20
  minutes and 12.3M tokens on one RTX Pro 6000, rather than a 200B-token
  post-NAS process.
- ConSA learns full-versus-sliding attention at layer or KV-head granularity
  and finds contiguous middle-layer full attention rather than evenly
  interleaved patterns.
- Learning to Allocate jointly gates layers, heads, and reasoning tokens,
  reporting 34% realized layer sparsity within 0.6% of the dense model on
  GSM8K.

**Gemma implication:** Gemma's fixed 50-local/10-global pattern is a concrete
co-design variable. A DASH-like frozen-weight search can test whether global
attention belongs in a smaller, contiguous subset or at selected KV heads.
This is a model modification requiring post-training/quality work, but the
search itself is now cheap enough to run in parallel with systems work.
Avoid naive layer dropping: search operator placement based on measured H200
cost and teacher-aligned outputs.

### 7. Serving, scheduling, and multi-GPU communication

Albireo reports up to 1.9x throughput, 48% lower latency, and 28% higher GPU
utilization by overlapping scheduling/I/O with compute and making sampling
sequence-parallel. Near-speed-of-light collectives reduce small/medium
collective latency to within 7% of the hardware lower bound. A large body of
recent work also covers P/D disaggregation, prefix-aware scheduling, KV
offload, and heterogeneous serving.

These are important for a production OpenRouter fleet and for models that
require tensor parallelism. They are not the primary explanation for the
current fixed, single-H200 Gemma benchmark. Apply them when moving to
multi-GPU models or mixed online traffic, and measure goodput rather than
transferring headline latency.

### 8. New hardware and diffusion-language-model research

The wide scan also contains custom accelerators, near-memory dequantization,
large-cache inference, wafer-scale systems, and a large cluster of
diffusion-language-model decoding papers. These show where the field may go,
but they do not accelerate an unchanged autoregressive Gemma checkpoint on
available GPUs. They become relevant when the lab changes hardware or trains a
substantially different model; they should not consume the immediate Gemma GPU
budget.

## Ranked Gemma research portfolio

| Rank | Project | Why now | Expected class | First falsifier |
| ---: | --- | --- | --- | --- |
| 1 | lossless DFlash repair plus D-Cut-style c32 verification budget | directly attacks the measured 25.36-28.93% target-verifier share and fixed depth-12 waste | potentially 20%+ whole request | one-cycle token/logit/KV oracle, then matched c32 depths 4/8/12/16 |
| 2 | large-vocabulary head and SonicSampler tail | overlooked Gemma-specific 262k-vocab work; Gemma-family literature result | uncertain, plausibly material and stackable | exact component attribution, top-k recall, and head/sampling GPU time |
| 3 | packed M384 Hopper verifier attention | measured low occupancy and c32 imbalance; PackInfer mechanism matches workload | roughly 5-10% whole if strong | exact q12 local/global component pair |
| 4 | tile-level FP8 SwiGLU/GEMM fusion | recent H100 results show real end-to-end gains; independent of speculation | roughly 5-13% whole if MLP traffic is visible | Nsight materialization/traffic attribution, then exact fused component |
| 5 | JetSpec/Domino-style causal Gemma draft head | largest upside if existing DFlash architecture remains weak | potentially 20%+ but training-heavy | offline one-forward draft cost and acceptance threshold model |
| 6 | L40S/A40 W4A4 chip-format-kernel route | could improve dollars/token through both lower rent and favorable INT4 balance | potentially 20%+ cost, quality-risked | exact Gemma GEMM roofline and component benchmark before model conversion |
| 7 | DASH-style Gemma hybrid-attention search | cheap way to discover model-specific FA/SWA placement | architectural 10-30% compute opportunity, unqualified | frozen-weight search plus teacher-output divergence curve |
| 8 | B200 FP4/sparsity/FA4 stack | credible alternate hardware frontier | potentially large, but requires new hardware and quantization | price-normalized exact endpoint once B200 is available |

Projects 1-4 can run independently. The director should not wait for the
longer drafter or architecture-search project before dispatching exact
component work.

## What not to infer from the literature

- A 10x or 16x sampling/kernel speedup is not a 10x or 16x endpoint speedup.
- A batch-one megakernel result does not prove a c32 benefit.
- A long-context sparse-attention result does not transfer to a 4.2k-token
  hybrid-attention model.
- A B200 FP4/FA4 result does not transfer to H200.
- “Accuracy preserved” on one benchmark is not exact-token equivalence or
  OpenRouter qualification.
- High mean accepted length does not imply speedup when drafting or
  verification is expensive.
- A failed implementation of a mathematically lossless mechanism is not
  evidence that the mechanism changes quality; localize the first semantic
  divergence before rejecting it.

## Primary sources

Reviewed 2026-07-25:

- DFlash, <https://arxiv.org/abs/2602.06036>
- AdaFlash, <https://arxiv.org/abs/2607.19223>
- D-Cut, <https://arxiv.org/abs/2607.14647>
- DSpark, <https://arxiv.org/abs/2607.05147>
- JetSpec, <https://arxiv.org/abs/2606.18394>
- DominoTree, <https://arxiv.org/abs/2607.08642>
- Progressive Tree Drafting, <https://arxiv.org/abs/2607.10661>
- EntMTP, <https://arxiv.org/abs/2606.27550>
- Saguaro / Speculative Speculative Decoding,
  <https://arxiv.org/abs/2603.03251>
- negative PEFT-BD result, <https://arxiv.org/abs/2607.12422>
- FlashAttention-4, <https://arxiv.org/abs/2603.05451>
- PackInfer, <https://arxiv.org/abs/2602.06072>
- SpecSA, <https://arxiv.org/abs/2605.19893>
- Inference Time Context Sparsity,
  <https://arxiv.org/abs/2605.24168>
- FlashHead, <https://arxiv.org/abs/2603.14591>
- SonicSampler, <https://arxiv.org/abs/2607.20475>
- Tile-Level Activation Overlap, <https://arxiv.org/abs/2607.02521>
- Deep Kernel Fusion for Transformers,
  <https://arxiv.org/abs/2602.11808>
- Ada-MK, <https://arxiv.org/abs/2605.11581>
- APEX4, <https://arxiv.org/abs/2606.08761>
- Moderately Unstructured Sparse Weight Matrices,
  <https://arxiv.org/abs/2607.08786>
- SpenseGPT, <https://arxiv.org/abs/2606.10445>
- SharQ, <https://arxiv.org/abs/2606.26587>
- Multi-Scale Dequant, <https://arxiv.org/abs/2605.13915>
- DASH, <https://arxiv.org/abs/2605.20936>
- ConSA, <https://arxiv.org/abs/2606.18056>
- Learning to Allocate, <https://arxiv.org/abs/2606.27743>
- Albireo, <https://arxiv.org/abs/2606.01927>
- Near-Speed-of-Light GPU Collectives,
  <https://arxiv.org/abs/2607.16100>

## Uncertainty and evidence gaps

- The 666-record inventory is reproducible but broad; keyword counts overlap
  and include papers outside practical GPU serving.
- Most July 2026 results are fresh preprints without independent replication.
- Published models, prompt lengths, output lengths, precision, hardware,
  baselines, and concurrency differ materially from the Gemma benchmark.
- FlashHead's headline result includes smaller models where the head is a
  larger fraction of total compute. Its Gemma 4 31B opportunity must be
  measured, not inferred from 1.75x.
- D-Cut and DSpark strongly match the c32 geometry but have not been integrated
  with Gemma/DFlash.
- APEX4 does not report Hopper. Its main immediate value is the chip-selection
  principle and the L40S/A40 experiment, not an assumed H200 speedup.
- Architectural sparsity and quantization can affect GPQA-Diamond and TauBench.
  Early performance exploration is useful, but a route cannot become a
  product candidate without later scope-matched qualification.
