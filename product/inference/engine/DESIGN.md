# Gemma 4 31B / H200 execution design

This document is the performance contract for the native engine. It describes the pinned
`google/gemma-4-31B-it@b9ea41a...` text model, not a generic transformer abstraction. Numbers are
derived from the release configuration and all 1,188 safetensors entries; the native inspector
validates the 772 text tensors before any GPU allocation.

## Exact forward graph

The text model has hidden width 5,376, MLP width 21,504, vocabulary 262,144 and 60 dense decoder
layers. Each layer performs:

1. RMSNorm in FP32 accumulation.
2. Q/K/V projection, head-wise Q/K RMSNorm, RoPE, causal GQA, and output projection.
3. RMSNorm of the attention update, then the first residual addition.
4. RMSNorm, gate and up projections, tanh-approximate GELU times up, and down projection.
5. RMSNorm of the MLP update, then the second residual addition.
6. Multiplication of the whole layer output by its learned BF16 `layer_scalar`.

After layer 59 the model applies a final RMSNorm and the tied embedding matrix as the LM head,
then `30*tanh(logit/30)`. Embedding lookup is multiplied by `sqrt(5376)` rounded to BF16. The
learned layer scalars are not all one (they range from about 0.0364 to 0.992), so this operation
cannot be folded into a residual branch.

There are two materially different attention operators:

| Layers | Count | Q heads | KV heads | Head width | Q width | KV width | KV source |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Sliding | 50 | 32 | 16 | 256 | 8,192 | 4,096 | distinct K and V, 1,024-token window |
| Global | 10 | 32 | 4 | 512 | 16,384 | 2,048 | V is normalized pre-RoPE K |

Global RoPE is proportional RoPE. It returns 512 coefficients, but only 64 frequencies in each
half rotate (128 dimensions total); the remaining frequencies are zero and therefore leave those
dimensions unchanged. Its exponent denominator remains 512. Sliding RoPE rotates all 256 head
dimensions. Attention scaling is exactly 1.0 because Q and K are normalized per head.

## H200 roofline

The checkpoint contains 30,697,345,340 text parameters and 61.395 GB of BF16 text weights. The
effective generated-token matrix work is approximately the same size: all decoder matrices plus
the tied 1.409-billion-parameter LM head. It is about 61.4 TFLOP per generated token.

For an H200 SXM with roughly 4.8 TB/s HBM bandwidth and 989 TFLOP/s dense BF16 tensor throughput:

- Reading BF16 weights once imposes a 12.8 ms decode-iteration floor, or 78 iterations/s, before KV
  traffic and kernel inefficiency.
- The machine balance is about 206 FLOP/byte. A decode GEMM with BF16 weights has arithmetic
  intensity near the active sequence count, so batches below roughly 206 are weight-bandwidth
  dominated. Our latency-relevant batches (1–32) are firmly in that regime.
- At batch 16 and 8k context, the idealized floor is about 12.8 ms of shared weight traffic plus
  about 5.0 ms of per-request KV traffic: approximately 900 aggregate output token/s before
  inefficiency. This is a ceiling, not a forecast.

The current SGLang control reaches about 316 aggregate output token/s at concurrency 10 on the
agentic trace, so the primary BF16 opportunity is utilization: low-M matrix kernels, launch count,
batch formation, and KV locality. Peak tensor FLOPS is not the first decode bottleneck.

## Parameter and KV traffic

Per layer, the MLP contains three 5,376x21,504 matrices (346.8 million parameters). Sliding
attention has about 132.1 million projection parameters per layer; global attention has about
187.2 million because Q/O are twice as wide even though K=V uses only four KV heads.

Uncapped BF16 KV storage is 880 KiB per token across all layers. With the 1,024-token sliding cap,
an 8k sequence needs approximately:

- 800 MiB for all 50 sliding-layer K/V tails;
- 640 MiB for all 10 global-layer K/V histories;
- 1.41 GiB total, excluding page metadata and allocator slack.

The physical KV payload at that length is about 1.41 GiB per generated token. A conventional
per-query-head GQA kernel rereads each sliding K/V head twice and each global K/V head eight times,
turning that into about 6.56 GiB of HBM reads. At concurrency 10, that naive traffic plus one weight
stream predicts a ceiling close to the measured SGLang control. The native decode kernel is
therefore organized per KV head: it loads a K/V tile once, computes all two sliding or eight global
queries, and maintains online-softmax outputs for the whole group. The target is the 1.41 GiB
physical floor, not the repeated-query implementation.

Measured cuBLASLt results on the production H200 validate the weight side of the roofline. Packed
QKV, O, gate/up and down matrices sustain about 3.2–4.3 TB/s at batches 1–32. Serially summing the
exact layer multiplicities gives roughly 16 ms of linear work per iteration across this range:
about 63 token/s at batch 1 and 995 aggregate token/s at batch 16 before attention, normalization
and scheduling. The LM head's first-choice heuristic is unstable across row counts, so production
plans must benchmark multiple cuBLASLt candidates and persist the winner per shape.

The parity-tested homogeneous decode runner currently measures 48.2 token/s at batch 1 and 747.6
aggregate token/s at batch 16 on the 27-token fixture. With physically allocated hybrid caches at
8,192 logical tokens it measures 43.4 token/s at batch 1 and 474.9 aggregate token/s at batch 16.
The latter is about 50% above the 315.9 aggregate token/s SGLang control, but is only a kernel
ceiling: it uses equal-length requests and zero-filled synthetic history. Economics are not
reported from it until ragged scheduling, real prefill, prefix reuse, and trace-level latency are
measured together.

## Layout and execution decisions

The BF16 correctness baseline uses a single 256-byte-aligned device weight arena. At load time it
re-packs separate checkpoint tensors into execution groups: Q/K/V (or Q/K for global), gate/up,
and standalone O/down matrices. Prefill and decode may use different packed copies only after a
measured benefit justifies the memory cost.

Decode uses fixed batch buckets and captured CUDA graphs. QKV and gate/up share input loads and one
launch. RMSNorm reductions accumulate in FP32; post-sublayer RMSNorm and residual addition are one
kernel. RoPE is fused with Q/K normalization and KV-page writes. Grouped decode attention uses one
cooperative block (or split block at long context) per request and KV head, staging K/V tiles in
shared memory and updating every query in the group with online softmax. Sampling fuses logit
softcap and top-k reduction so full-vocabulary logits are not round-tripped through host memory.

The first measured grouped-attention implementation used one scalar dot-product dependency chain
per query and reached only 3–50 GB/s. The retained tensor-core formulation groups work by physical
KV head and uses strided batched QK/PV GEMMs, reaching about 3.2 TB/s for sliding attention and 3.8
TB/s for global attention at batch 16. This failed baseline is intentionally recorded: a logically
correct kernel that misses the H200 roofline by two orders of magnitude is not an optimization
endpoint.

Prefill uses cuBLASLt tensor-core GEMMs and a hybrid attention path. The 50 sliding layers use
cuDNN's fused FlashAttention-2 graph with exact causal and 1,024-token left bounds; the 10 global
layers use grouped tensor-core QK/PV GEMMs because Gemma's 512-wide heads exceed the fused Hopper
SDPA contract. Global scores occupy a reusable 4.3 GB BF16 arena at 8k. The latter is a baseline to
replace with a tiled online-softmax kernel, not a permanent reason to alter the model.

On the production H200, sliding attention alone takes 0.437 ms per 8k layer and global attention
takes 9.20 ms per 8k layer. The complete parity-tested BF16 model reaches 8,181 warm input token/s
at 8k, 8,671 token/s at 4k, and 8,961 token/s at 2k. At 27 tokens, reusing initialized plans cuts
prefill from 946 ms cold to 22.0 ms warm. All eight reference greedy tokens remain exact after
prefill populates the global history and sliding rings. These are single-sequence measurements;
prefill must still be chunked so a long cache miss cannot starve decode or violate TTFT. Chunk size
is selected by measured decode interference, not a fixed framework default.

The chunk path reconstructs only the previous 1,023 sliding tokens in logical order, appends new
K/V with absolute-position RoPE, and uses bottom-right causal alignment. Global layers append to
their persistent history directly. An 8-token chunk test across the 27-token fixture preserves all
8/8 greedy outputs after cached decode. At 8k, measured warm tradeoffs are:

| Chunk | Input token/s | Full-pass throughput retained | Approximate scheduling quantum |
| ---: | ---: | ---: | ---: |
| 256 | 6,406 | 78.3% | 40 ms |
| 512 | 7,550 | 92.3% | 68 ms |
| 1,024 | 8,055 | 98.4% | 127 ms |
| 2,048 | 8,160 | 99.7% | 251 ms |
| 4,096 | 8,185 | 100.1% | 500 ms |

The scheduler should therefore use 1,024-token chunks when decode pressure is ordinary, shrink to
512 or 256 under a tight p95 TPOT deadline, and expand to 2,048+ while idle. It does not need to pay
a permanent throughput tax for responsiveness.

An Nsight Systems capture of warm 8k prefill attributes about 73% of GPU time to tensor-core
linears, 2.7% to fused sliding SDPA, and roughly 20% to engine-owned elementwise/layout work. The
largest non-GEMM targets are GELU (4.8%), global causal softmax (4.5%), Q/K norm plus RoPE (about
8.5%), RMS/residual kernels (3.7%), and global token/head transposes (1.6%). The apparently long
final D2H copy is only the host synchronization point waiting for those kernels.

The KV allocator is hybrid rather than uniform:

- global layers use refcounted paged history;
- sliding layers retain only the last 1,024 tokens per live branch;
- a radix tree maps token-prefix hashes to shared global pages and sliding tails;
- cache admission accounts for recompute cost, byte size, reuse probability and age.

This is essential for the target workload: around 90% of input is an already-seen conversation or
agent prefix. A real cache hit bypasses transformer FLOPS; merely batching the repeated prefill does
not.

## Precision and speculation

BF16 is the parity baseline. FP8 is tested as W8A8 with per-block weight scales and dynamic
per-token activation scales, because H200 can both halve dominant weight traffic and increase
tensor-core throughput. It is promoted only if held-out completion parity, similarity, TTFT and
TPOT remain competitive. Mixed precision by matrix/layer is allowed when sensitive outliers make
uniform FP8 fail.

Frozen-KV MTP is integrated into the scheduler rather than bolted on as a mutually exclusive mode.
At low effective target batch it uses otherwise underutilized arithmetic to propose four tokens;
the target verifies all proposals as one causal micro-batch. It is disabled or shortened when
verification would cross the latency-optimal batch bucket. There are no CPU synchronization points
between draft steps, verification and accepted-token commit.

## Optimization gates

Every retained change must pass, in order:

1. kernel parity against pinned Transformers outputs for sliding layer 0, global layer 5, final
   logits and multi-token cached decode;
2. deterministic greedy completion comparison on an untouched trace partition;
3. sustained agentic traffic at realistic concurrency and approximately 90% prefix-cache reuse;
4. p50/p95 TTFT, TPOT and request-time comparison against the production control;
5. cheapest-OpenRouter-price revenue divided by measured H200 hourly cost.

Desmond records sampled per-stage GPU timings, batch shape, prefix hit bytes, KV bytes, accepted
draft depth, precision path and kernel identifiers in `profiling_events.properties`. CUPTI hardware
counters are sampled in profiling runs, not enabled on every production request.

## Measured optimization frontier (2026-08-22)

The retained tensor-scaled FP8 decode projections take about 7.75 ms per model step. The measured
30.7 GB FP8 weight stream at approximately 4.0 TB/s has a 7.67 ms lower bound, so further work on
the dense projection kernels can recover at most about 1% unless it changes weight precision or
fuses away traffic. Optimization effort therefore moves to KV traffic, attention and scheduling.

On the asynchronous 16-conversation agentic workload (ten turns per conversation, 256 new input
tokens and 128 output tokens per turn), the exact non-speculative engine sustains 385.6 output
token/s. Cached-turn mean TTFT is 660 ms and mean TPOT is 28.8 ms. At the same traffic mix and the
cheapest measured OpenRouter price, this is approximately 31.6% H200-cost recovery: about
$1.42/hour gross against $4.50/hour compute, leaving about $3.08/hour or $2,245/month uncovered.

The exact four-token MTP path is not promoted. At concurrency 16 it accepts 3.24 candidates per
target verification on average, but sustains only 281.9 output token/s; drafting takes 8.35 s and
target verification 28.9 s over the measured run. The base path is 36.8% faster and also has lower
TTFT and request time. A two-token depth, minimum speculative cohort thresholds, context-sorted
verification, eager execution and alternate legacy cuBLAS algorithms were measured and rejected.

Nsight attributes 34.5% of a long-context FP8 decode step to the ten global QK operations. Dense
FP8 projections, global QK, global PV, sliding attention and elementwise work account for nearly
all GPU time; host transfers are negligible. This establishes the next first-principles target:
reduce physical global-KV bytes (quality-gated FP8 KV or equivalent compression) and use a
Hopper-native fused D=512 GQA kernel that performs QK, online softmax and PV without materializing
scores. The current engine is close to the weight-stream lower bound, but the complete inference
graph is not yet mathematically optimal.

A standalone cuBLASLt experiment on the exact global QK geometry measured 0.1340 ms with BF16
keys/queries (4.01 TB/s) and 0.0705 ms with E4M3 keys/queries (3.81 TB/s), a 1.90x QK speedup from
halving bytes. This proves the hardware path but not model quality or full-attention speed: PV,
softmax and quantization scales remain. A fragmented-slot Lt integration was rejected after the
full production-shape suffix parity suite failed. The failure persisted after reverting Lt and was
isolated to an undersized staging arena in the existing batched cuDNN sliding-suffix path at 10
requests by 257 tokens. The arena had accounted for one 1,023-token prior instead of one per
request, so the path overwrote adjacent GPU memory. Both K/V arenas now cover the exact worst case,
`max_tokens + max_batch * (sliding_window - 1)`, and the complete production-shape parity suite
passes with the fast path enabled. The temporarily disabled correctness-first setting sustained
387.1 output token/s, within measurement noise of the former 385.6 token/s result.
