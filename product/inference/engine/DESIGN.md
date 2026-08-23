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
shared memory and updating every query in the group with online softmax. The planned stochastic
sampling path fuses logit softcap and top-k reduction so full-vocabulary logits are not
round-tripped through host memory; the retained release currently executes exact greedy argmax
only.

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

The production-shaped FP8-QK follow-up uses independent architecture-derived scales: global Q is
multiplied by 64, while global K is multiplied by 1,024 because every global K RMSNorm weight is
approximately 1/16. At B16/D512/8k, the complete QK/softmax/BF16-PV call falls from 0.2832 ms to
0.2199--0.2420 ms. Synthetic Gemma-scaled output has 0.9986 cosine similarity to BF16, but the
held-out coding-agent gate rejects the approximation. FP8 K on all ten global layers gives
487/512 teacher-forced agreement and 3/16 exact prompts with BF16 weights. Alternating layers
`{5,17,29,41,53}` give 500/512 and 8/16; the complementary set
`{11,23,35,47,59}` gives 502/512 and 10/16. Combining the better set with retained tensor-FP8
projections falls to 499/512 and 8/16, below the 503/512 projection-only baseline. The path remains
explicitly opt-in for research and allocates its cuBLASLt workspace lazily; it is not a production
precision policy.

cuDNN SDPA was also measured as a BF16 fused-decode candidate at the same shape. It takes 0.702 ms
at batch 1 and 0.862 ms at batch 16 versus 0.040 ms and 0.283 ms for the retained GEMM composition.
The retained B16 composition moves the physical 1.07 GB K/V payload at about 3.79 TB/s, roughly
79% of the 4.8 TB/s H200 HBM roof. A perfect BF16 fused attention kernel therefore has only about
0.059 ms/layer left at this exact contiguous geometry; further material gains require improving
fragmented cohorts or reducing bytes without the quality loss observed above.

The production protocol now streams native token IDs as soon as each scheduler step completes,
carries cumulative authoritative usage on every event, and cancels/reclaims a slot when the
downstream socket closes. Gemma's pinned EOS set (`1`, `106`) is loaded from `config.json`; it is
no longer optional caller state. The AWS gateway performs stateful incremental decoding,
including split-byte tokens, and emits normalized OpenAI SSE chunks. The initial catalog contract
intentionally advertises greedy `temperature=0` only. Native stochastic sampling is not
implemented yet and must not be inferred from the sampling design above.

The former 387.1 token/s trace result corresponds to 41.3 ms per full 16-request output wave when
all slots are productive. The fully parity-gated synthetic 8k frontier is 477.6 token/s
homogeneous (33.5 ms/wave) and 407.1 token/s ragged (39.3 ms/wave). Against the measured 7.67 ms
FP8 weight-stream floor plus approximately 5.0 ms for one physical BF16 KV pass across sixteen 8k
sequences, the complete decode graph is therefore only about 32--38% of its rough 1.2k token/s
byte-traffic ceiling. Dense projections are near their own bound; the whole engine is not yet near
the mathematical bound.

The measured FP8-QK experiment gives a bounded next-step forecast. Applying its 1.90x QK speedup
to the 34.5% Nsight share yields an Amdahl limit of 1.195x, or about 463 trace token/s before
quantization and layout overhead. At unchanged traffic mix and prices that would raise
compute-cost recovery from 31.8% to about 38.0%, still far from break-even. A fused grouped-query
kernel that loads each physical global K tile once, performs online softmax, and immediately
accumulates V is required to attack the remaining gap; merely tuning the dense GEMMs cannot do so.

A correctness-complete WMMA prototype tested that fusion boundary directly. One block owns a
physical KV head, computes 8x64 QK with four tensor-core warps, performs online softmax, and uses
sixteen warps for the 8x512 PV update. It never writes the score matrix to HBM and matches the BF16
GEMM path at 127 tokens with maximum/mean absolute errors of `4.58e-5`/`1.09e-5`. It is rejected:
at batch 16 and 8k it takes 5.55 ms per global layer versus 0.282 ms for the retained QK/softmax/PV
GEMMs. A 32-token tile takes 5.65 ms, proving that shared-memory capacity and tile barriers are not
the only problem. CUDA WMMA's 16x16 operation wastes half the rows on Gemma's eight-query group,
and repeated block-wide synchronization prevents enough independent tensor-core work. A viable
single-pass kernel needs Hopper warpgroup MMA with asynchronous TMA/cp.async pipelining (or an
equivalent CUTLASS/CuTe schedule), not a larger version of this WMMA kernel.

FlashInfer was measured as an independent Hopper baseline at the exact global shape rather than
assumed to be an upper bound. Its supported non-tensor-core D=512 decode path takes 0.0557 ms at
batch 1 (1.21 TB/s of physical K/V) and 0.698 ms at batch 16 (1.54 TB/s). Its tensor-core prefill
dispatcher rejects D=512 as an invalid MMA configuration. The retained strided cuBLAS composition
is therefore still the best measured primitive at this geometry; adopting a framework kernel
would regress the batch-16 layer from 0.282 ms before any integration overhead.

Part of the gap between that primitive and the production graph was traced to cache addressing.
Decode graphs now specialize consecutive active cache intervals with
`cublasGemmStridedBatchedEx` and retain per-row position masks, so a saturated `[0,16)` cohort gets
the strided path without
changing model arithmetic. Exact tensor-FP8 greedy parity passes for all eight fixture tokens at
batch 16, and also for the offset interval `[1,16)` at batch 15. At 8k the production-shaped
ragged frontier rises from 407.1 to 465.9 output token/s, only 2.4% below the 477.6 token/s
homogeneous ceiling.

The original asynchronous harness queued exactly sixteen conversations and included their uneven
terminal drain, producing 391--393 output token/s with a mean active batch of 12.20. The retained
sustained harness queues 64 unique conversations through sixteen workers and reports exact token
classes and latency percentiles. Even with backlog, cached turns temporarily leave decode while
their new suffix is computed. Batching two or more waiting suffixes of at most 512 tokens through
the parity-tested multi-request prefill path raises mean active batch from 13.06 to 13.79 and cuts
batch-8-or-lower steps from 20.3% to 8.7%. Existing decoders retain their original clocks, so the
reported TPOT includes every interleaved prefill pause rather than hiding scheduler interference.

The confirmation run sustains 421.1 output token/s over 64 conversations and 640 turns. Cached
TTFT p50/p95 is 143.8/628.5 ms, TPOT p50/p95 is 28.15/44.04 ms, and request time p50/p95 is
3.685/6.006 seconds. A second run reached 428.8 output token/s. Against the SGLang coding-agent
control, native TTFT and median request time are materially better; p95 request time and decode
tail remain the competitive weakness. Exact usage over 181.4 seconds was 404,510 uncached input,
2,608,294 cached input and 76,396 output tokens. At $0.08/$0.01/$0.35 per million respectively,
that is $1.690/hour gross, 37.56% of the $4.50/hour H200, leaving $2.810/hour or about $2,051/month
of compute uncovered.

On the current held-out fixture, tensor-scaled FP8 decode agrees with the independent BF16 runner
on 503/512 teacher-forced coding-agent predictions (98.24%); 10/16 prompts match all 32 evaluated
positions. An isolated rebuild of the immutable `d0a7e548` source produces the same 503/512 and
10/16 result, so this is the reproducible baseline rather than the previously recorded 508/512
figure. Block-128 has no cuBLASLt algorithm for every Gemma projection shape. The next precision
experiment must beat this exact matched-source gate and include completion-level quality, not rely
on an unreproducible prior count.

Splitting a fragmented mask into several library GEMMs was measured and rejected. For the same
four-run B12/D512/8k cache mask, one pointer-array QK/softmax/PV sequence takes 0.2307 ms while four
strided sequences take 0.3052 ms, a 32.3% regression from smaller GEMMs and repeated launches. The
exact FP8 model path remained 8/8-token correct, but sustained agent traffic fell to 385.5 output
token/s with TPOT increasing to 29.16 ms. The experiment was removed. Fragmented slots need one
persistent slot-indexed kernel (or physical compaction proven cheaper than the extra KV traffic),
not a graph assembled from multiple contiguous library calls.

Cached-suffix preemption was tested at the model graph's two natural boundaries. Splitting the
usual 257-token extension at 192 tokens repeated a complete model-weight pass for the 65-token
tail. It reduced neither end-to-end latency nor cost: sustained output fell from 422.2 to 411.9
token/s, median request time rose from 3.626 to 3.837 seconds, and p95 request time rose from 5.958
to 6.034 seconds. Token-quantum suffix splitting is therefore rejected for this traffic shape.

The retained implementation instead keeps dedicated in-flight suffix hidden states and preempts
only at exact transformer-layer boundaries. Decode uses separate workspaces and stable cache
slots; partial suffix KV is not exposed by the logical slot position. Ten-layer slices execute
every one of Gemma's sixty layers exactly once while permitting a decode wave between slices.
Production-shape 10-request/257-token parity matches the unsliced path through the next decode
token. Cancellation aborts the cohort state and leaves the old logical prefix valid.

Always slicing improved decode tails but delayed admission enough to make aggregate throughput
unstable. The retained pressure policy slices only while at least 14 of 16 requests are already
decoding and finishes all remaining layers immediately below that threshold. On the same
64-conversation, c16, ten-turn trace it sustains 431.0 output token/s. Cached TTFT p50/p95 is
166/514 ms, mean TPOT p50/p95 is 27.49/44.26 ms, and request time p50/p95 is 3.636/5.917 seconds.
The observed billed token mix recovers 37.46% of a $4.50/hour H200, effectively equal to the
37.49% matched unbounded run; normalizing both policies to the baseline token mix raises recovery
from 37.49% to 38.28%. A 12-request threshold traded another 1.2 ms of p95 TPOT for lower TTFT and
throughput, while 15- and 20-layer slices were dominated and rejected.

The retained RMS schedule now uses 1,024 threads per long Gemma row instead of 256. At B16 there
are only sixteen independent rows, so the smaller blocks left most H200 SMs idle while each thread
serially processed many columns. The full-SM blocks preserve 8/8 pinned generation tokens and
produce 504/512 teacher-forced FP8 agreement with 10/16 exact prompts on the coding-agent holdout.
The homogeneous B16/8k
frontier rises from 782.7 to 857.2 output token/s. A fused RMS-to-FP8 kernel was exact but reached
only 779.1 token/s because its sixteen CTAs under-parallelized quantization; per-row FP8 scaling
reached only 569.1 token/s; both are rejected. Keeping 256-thread RMS only for prefill was also
rejected at 431.8 sustained token/s because slower suffix admission reduced the active decode
cohort.

On a cold same-fixture 64-conversation/c16/ten-turn A/B, the frozen 256-thread binary sustains
412.87 output token/s. Two cold 1,024-thread runs sustain 456.17 and 452.84 token/s (454.50 mean),
a 10.08% gain. Candidate cached TTFT p50/p95 ranges are 166--171/562--600 ms versus 163/712 ms for
control; TPOT p50/p95 is 25.24--25.33/41.01--41.92 ms versus 27.42/44.06 ms; request p50/p95 is
3.356--3.384/5.549--5.584 seconds versus 3.671/6.057 seconds. At each run's observed token mix,
candidate gross is $1.781--$1.797/hour, recovering 39.58--39.92% of a $4.50 H200. The remaining
loss is $2.70--$2.72/hour, approximately $1,974--$1,985 per 730-hour month.

The final activation-quantization launch uses 256-thread cooperative CTAs below 65,536 elements
and 512-thread CTAs at or above that boundary. The larger grid width reduces the two streaming
passes and grid barriers for saturated decode batches without adding reduction overhead to B1.
Across the complete B16 FP8 linear schedule, quantize-plus-GEMM time falls from a three-run
9.968 ms mean to 9.849 ms; end-to-end ragged B16/8k decode rises from 491.64 to 492.84 token/s
(three-run means). The gain is deliberately small because the retained GEMMs already stream
weights at about 4.10 TB/s and the retained attention path streams physical KV bytes at about
3.78 TB/s, respectively 85% and 79% of the H200's 4.8 TB/s HBM ceiling.

The native HTTP listener is nonblocking. Under connection churn a readiness edge can disappear
before `accept4`; a blocking listening descriptor could then strand the only accept loop and make
health or metrics unreachable after a successful inference burst. A 512-request concurrent burst
test now gates post-burst responsiveness.
