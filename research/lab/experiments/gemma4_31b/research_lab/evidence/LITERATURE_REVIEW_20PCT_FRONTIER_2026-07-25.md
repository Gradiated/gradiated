# Literature review: routes to another 20% on Gemma 4 31B

Date: 2026-07-25

## Decision

The literature supports one primary route and two complementary routes:

1. **Primary:** make parallel speculative decoding work correctly for Gemma,
   then choose speculation geometry from measured H200 cost and acceptance
   curves. DFlash/AdaFlash, SMART, JetSpec, and Saguaro all attack the number
   or serialization of full target passes, which is the only currently
   evidenced mechanism with a plausible independent 20%-class whole-request
   gain.
2. **Complement:** replace the current generic M384 attention execution with a
   packed, Hopper-native, warp-specialized verifier attention kernel. PackInfer,
   FlashAttention-3, and FlashInfer provide the relevant design pattern. This
   is likely stackable rather than independently 20%-class.
3. **Complement:** use an SM-level persistent target-verifier executor only
   after measuring the complete operator boundary. Mirage Persistent Kernel
   demonstrates the right scope. The current `BLOCK_M=8` attention patch is a
   tile specialization, not the cohesive executor rewrite contemplated by that
   literature.

The failed adapted DFlash diagnostic should be classified as a **Gemma/SGLang
correctness bug**, not evidence that diffusion drafting changes target-model
quality. Speculative verification is supposed to preserve target semantics,
and the DFlash paper reports lossless generation. The next DFlash action should
be a single-cycle verifier/KV-commit oracle, not a broad quality run.

## Scope and local evidence

Target:

- model: `google/gemma-4-31B-it@b9ea41a...`
- hardware: H200 SXM
- workload: c32, approximately 4,214 prompt and 358 output tokens/request
- quality-qualified NGRAM baseline: `0.625149101968745 s/request`
- 20% target: `0.500119281574996 s/request`
- required saving: `0.125029820393749 s/request`

Measured/derived critical-path evidence:

- target verification accounts for an estimated
  `0.158548-0.180858 s/request`, or `25.36-28.93%` of the qualified baseline;
- attention is `67.13%` of the captured target-verification GPU union;
- therefore even eliminating the measured attention family entirely has only
  a `17.03-19.42%` whole-request ceiling;
- the target verifier needs a `69.13-78.86%` reduction to deliver the entire
  20% objective alone;
- the current global attention kernel uses 255 registers/thread, one CTA/SM,
  `12.50%` achieved occupancy, `10.10%` tensor activity, `2.21%` DRAM
  utilization, and `36.96%` L2 utilization;
- the fixed M384 trace contains 750 local and 150 global attention launches,
  3,600 FP8 projection launches, and 180 depth-sliced tied-head launches over
  15 captured cycles;
- native NGRAM already accepts nearly the full 12-token proposal block, so
  improving NGRAM proposal quality is not the bottleneck;
- DFlash reached real drafting and target verification but matched the AR
  control on only 2/4 deterministic requests. Only two acceptance log events
  were observed, with mean accepted length 4.77; this is too little valid
  telemetry for a performance conclusion.

These local measurements are the basis for the rankings below. Published
speedups are not transferred to Gemma without a scope-matched endpoint result.

## Ranked opportunities

### 1. Repair DFlash correctness, then add hardware-aware adaptive block length

**Priority: highest. Confidence: high in the mechanism, medium in the existing
Gemma checkpoint/integration. Effort: moderate.**

DFlash generates a full block in one draft forward and verifies it with the
target. The paper reports lossless acceleration, uses five target hidden
features and typically five draft layers, and reports large speedups on Qwen3.
Its serving results use SGLang Spec-v2 overlap. Most importantly for an
immediate experiment, a drafter trained at block size 16 generalized well to a
smaller inference block size, while the reverse did not. The authors explicitly
identify adaptive block-size scheduling as a deployment opportunity.

AdaFlash adds the missing deployment control: diffusion-drafter acceptance
varies strongly by domain and token position, and later positions become less
likely to be accepted. It learns an adaptive length head and reports its
largest gains at high concurrency. DFlare separately shows that using
layer-specific mixtures of a broader set of target hidden layers improves
DFlash by roughly 5-11%, but this is a later training improvement rather than
the first experiment.

SMART and Sequoia provide a simpler systems formulation that does not require
starting with a learned controller:

`expected accepted tokens / (measured draft cost + measured verify cost)`.

SMART fits drafting and verification cost curves with five forward passes and
expands speculation only while marginal benefit exceeds marginal cost.
Sequoia similarly demonstrates that hardware-aware tree dimensions can be up
to roughly 40% better than fixed dimensions in its settings.

**Gemma experiment:**

1. Preserve the current block-16 draft and Spec-v2 runtime.
2. Build a one-cycle deterministic oracle that records:
   target AR argmax tokens, draft tokens, verifier target logits/argmax,
   accepted prefix, bonus token, KV write locations, committed sequence length,
   and the first subsequent AR token.
3. Fix the first divergence in the Gemma capture/acceptance/KV-commit path.
   Draft disagreement is valid; accepted target-token or committed-state
   disagreement is not.
4. Once exact, run only block sizes 4, 8, 12, and 16 at c32. The paper supports
   using the block-16-trained draft at smaller inference lengths.
5. Fit `C_verify(M)` and combine it with per-position acceptance telemetry.
   First deploy a table/controller based on observed batch geometry; train an
   adaptive head only if the simple controller leaves material variance.
6. Retain Spec-v2 overlap, which the current server already reports as enabled.

This should precede another fixed-attention tile experiment because it can
remove full target passes rather than reducing one family inside each pass.

### 2. Train a causal one-forward parallel drafter for Gemma

**Priority: high, after the DFlash verifier oracle. Confidence: medium. Effort:
high. Upside: 20%-class or larger.**

JetSpec identifies a weakness in bidirectional block-diffusion drafts:
individually plausible position-wise predictions can be mutually inconsistent
because they are not branch-conditioned. It trains a causal parallel draft
head over fused hidden states from a frozen target model, generating a
path-conditioned candidate tree in one forward. It reports up to 9.64x over AR
on MATH-500 and 4.58x on open-ended conversation on H100 for Qwen3-family
models.

P-EAGLE is a lower-risk related design: a shared hidden state converts
autoregressive EAGLE drafting into parallel multi-token prediction and reports
1.10-1.36x over EAGLE-3. DFlash is cheaper to try because a Gemma draft exists,
but JetSpec/P-EAGLE are good fallback architectures if the block-diffusion
checkpoint has weak or unstable acceptance on the exact OpenRouter workload.

This is model-specific co-design in the desired sense: train only a small
Gemma-specific drafting head/adapter while the unchanged target verifier
preserves output semantics. Training data should be on-policy Gemma outputs
with GPQA-Diamond, TauBench, and production-like chat/tool traffic represented.

### 3. Overlap drafting with verification beyond ordinary Spec-v2 scheduling

**Priority: high if draft time remains visible after DFlash correctness.
Confidence: medium. Effort: high.**

Saguaro observes that ordinary speculative decoding still serializes drafting
after verification. While verification runs, it predicts likely verification
outcomes and precomputes drafts for them. The paper reports up to 2x over
optimized speculative-decoding baselines and more than 20% even at larger
batches in its tested settings.

SGLang Spec-v2 is already enabled in the measured DFlash launch, so merely
turning on overlap is not a new experiment. The new mechanism would be
outcome-conditioned pre-drafting on a separate stream or device, with a small
cache keyed by likely accepted-prefix/bonus-token outcomes. It is relevant
only if a trace shows draft work on the critical path after the adaptive
block-size fix.

### 4. Build a packed, Hopper-native M384 verifier-attention kernel

**Priority: medium-high and parallelizable. Confidence: medium-high for a
stackable gain, low for an independent 20%. Effort: high.**

The current kernel is register-residency limited and gives one CTA per SM, but
the fixed `BLOCK_M=16` test regressed and the new `BLOCK_M=8` candidate cannot
independently reach 20%. Literature suggests changing the execution
decomposition, not merely shrinking the query tile:

- FlashAttention-3 uses Hopper TMA, warp specialization, and asynchronous
  matmul/softmax pipelining; it reports 1.5-2.0x attention speedup on H100.
- PackInfer packs heterogeneous request/query-key regions into load-balanced
  groups and reorganizes KV for compute and I/O locality; it reports 13.0-20.1%
  inference-latency reduction and 20% throughput improvement in its workloads.
- FlashInfer combines composable sparse KV formats, JIT specialization,
  load-balanced scheduling, and CUDA-graph compatibility.

**Gemma kernel design:**

- specialize jointly for c32, q-length 12, local head dimension 256/window
  1,024 and global head dimension 512;
- group requests by actual context work rather than assigning one static CTA
  geometry per request/head;
- pack query/KV regions so long-context requests do not create tail waves;
- use TMA producer warps and separate WGMMA/softmax consumer warps;
- reduce live query/accumulator state by splitting over context and applying an
  exact online-softmax reduction, rather than reducing `BLOCK_M` alone;
- consume the paged E5M2 KV cache directly and preserve exact target semantics.

A 2x improvement to the measured attention family would imply only about
`8.5-9.7%` whole-request saving under the current bound. It is valuable for a
stack, but it should not displace speculative-decoding work.

### 5. Rewrite the complete target-verification boundary as an SM task graph

**Priority: medium. Confidence: medium-low at c32. Effort: very high.**

Mirage Persistent Kernel turns a tensor program into an SM-level task graph
inside one persistent kernel, enabling cross-operator pipelining and
fine-grained overlap; it reports up to 1.7x end-to-end latency reduction.
ThunderKittens supplies Hopper-native tile, TMA, WGMMA, and load/store/compute
pipeline abstractions. FlashDecoding++ similarly emphasizes asynchronous
softmax, flat-GEMM specialization, and hardware-dependent dataflow.

The useful lesson is scope: a real executor rewrite should span recurring
boundaries such as:

- RMSNorm / dynamic FP8 quantization / QKV GEMM;
- attention / output projection / residual;
- RMSNorm / FP8 quantization / gate-up / activation / down / residual;
- verification hidden states / depth-major LM-head and acceptance handling.

The current trace says queued GPU work, not host launch latency, dominates.
Gemma's 31B weights also prevent a small persistent kernel from retaining the
whole model on chip. Therefore MPK's published 1.7x is not directly
transferable. Even a 1.7x reduction applied only to the measured target
verification share projects to roughly `10.4-11.9%` whole-request saving.
This is a stack route and a framework for the fixed-M384 project, not the
first independent 20% bet.

### 6. Reopen 4-bit only as W4A8 system co-design, not another W4A16 Marlin run

**Priority: medium-low on H200. Confidence: low-medium. Effort: high. Quality
risk: material.**

The negative Marlin experiment does not falsify all 4-bit serving. QServe
argues that ordinary INT4 methods lose 20-90% to dequantization and designs
W4A8KV4 jointly with weight reordering, register-level dequantization, and a
memory-bound fused attention kernel. It reports 1.2-3.5x serving-throughput
improvements over TensorRT-LLM on A100/L40S depending on model. QQQ similarly
uses W4A8 kernels rather than W4A16.

For H200 c32/M384, FP8 tensor-core execution is already strong and the prior
W4 kernel was slower, so this is not the leading route. Reopen only with:

- an H200-native W4A8 kernel at the exact Gemma projection shapes;
- dequantization fused into tensor-core staging;
- a component roofline proving at least 20% over the current FP8 GEMMs before
  endpoint work;
- later GPQA-Diamond/TauBench qualification using rotation/smoothing or QAT.

SpinQuant and QServe improve low-bit accuracy but do not establish unchanged
Gemma quality; this route cannot be called quality-neutral until measured.

## Recommended immediate portfolio

Keep the portfolio small:

1. **DFlash verifier correctness + block 4/8/12/16 controller** — highest
   information and highest whole-request upside.
2. **Packed M384 Hopper attention kernel** — independent kernel lane using the
   existing trace and exact consumer.
3. **JetSpec-style Gemma drafter feasibility** — offline architecture/training
   lane; first establish data, head parameter count, one-forward draft cost,
   and predicted acceptance threshold required to beat NGRAM.
4. **Current M8 attention candidate** — run once because it is already
   source-complete, retain any simple gain, but do not represent it as the
   20%-class executor rewrite.

Do not spend another cycle on proposal ensembles, masks, penalty kernels,
allocator bookkeeping, generic quality sweeps, or more attention tile-size
sweeps. Those mechanisms are already bounded or measured below the objective.

## Sources

All source claims below are author-reported and were reviewed on 2026-07-25.
They are not Gemma measurements.

- Chen, Liang, Liu, “DFlash: Block Diffusion for Flash Speculative Decoding,”
  ICML 2026. <https://arxiv.org/abs/2602.06036>
- Qian et al., “AdaFlash: Adaptive Speculative Decoding via On-Policy
  Distilled Diffusion Drafters.” <https://arxiv.org/abs/2607.19223>
- Zhang et al., “DFlare: Scaling Up Draft Capacity for Block Diffusion
  Speculative Decoding.” <https://arxiv.org/abs/2606.02091>
- Hu et al., “JetSpec: Breaking the Scaling Ceiling of Speculative Decoding
  with Parallel Tree Drafting.” <https://arxiv.org/abs/2606.18394>
- Hui et al., “P-EAGLE: Parallel-Drafting EAGLE with Scalable Training.”
  <https://arxiv.org/abs/2602.01469>
- Kumar, Dao, May, “Speculative Speculative Decoding.”
  <https://arxiv.org/abs/2603.03251>
- Wang, Zhou, “SMART: When is it Actually Worth Expanding a Speculative
  Tree?” <https://arxiv.org/abs/2604.09731>
- Chen et al., “Sequoia: Scalable, Robust, and Hardware-aware Speculative
  Decoding.” <https://arxiv.org/abs/2402.12374>
- Shah et al., “FlashAttention-3: Fast and Accurate Attention with Asynchrony
  and Low-precision.” <https://arxiv.org/abs/2407.08608>
- Ning, Zhang, Lai, “PackInfer: Compute- and I/O-Efficient Attention for
  Batched LLM Inference.” <https://arxiv.org/abs/2602.06072>
- Ye et al., “FlashInfer: Efficient and Customizable Attention Engine for LLM
  Inference Serving.” <https://arxiv.org/abs/2501.01005>
- Cheng et al., “Mirage Persistent Kernel: A Compiler and Runtime for
  Mega-Kernelizing Tensor Programs.” <https://arxiv.org/abs/2512.22219>
- Spector et al., “ThunderKittens: Simple, Fast, and Adorable AI Kernels.”
  <https://arxiv.org/abs/2410.20399>
- Hong et al., “FlashDecoding++: Faster Large Language Model Inference on
  GPUs.” <https://arxiv.org/abs/2311.01282>
- Lin et al., “QServe: W4A8KV4 Quantization and System Co-design for Efficient
  LLM Serving.” <https://arxiv.org/abs/2405.04532>
- Liu et al., “SpinQuant: LLM Quantization with Learned Rotations.”
  <https://arxiv.org/abs/2405.16406>

## Uncertainty

- DFlash, AdaFlash, DFlare, and JetSpec results are not on Gemma 4 31B.
- DFlash's strongest serving table uses B200/FA4, while the campaign uses
  H200 and a Triton target backend.
- Published speedups use different prompt lengths, output lengths, batching,
  model sizes, and baselines.
- The target-verification whole-request share is derived from 15 captured M384
  cycles and counters; one short scope-matched capture should replace that
  estimate before claiming an endpoint projection.
- The DFlash 4.77 acceptance observation comes from only two log events in a
  semantically invalid run and is useful only as a debugging clue.
