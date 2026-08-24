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

The native scheduler emits request admission/completion, prefill, decode and speculative-batch
events into a fixed-size shared-memory SPSC ring. The inference path performs one lock-free copy
and drops rather than blocks when the ring is full. Desmond drains those events, adds periodic
NVML/runtime snapshots, and uploads stable-ID batches into `profiling_events.properties` with
bounded exponential retry. Per-kernel identifiers and CUPTI hardware counters remain opt-in
profiling-run data; enabling them on every production request would perturb the timings being
measured.

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

Cached suffix projections now optionally reuse the retained tensor-E4M3 weights when the complete
cohort has at most 4,096 packed tokens. The FP8 activation workspace covers the full configured
prefill row bound rather than only four speculative rows per slot. Large sliding suffixes continue
to use fused cuDNN attention; the pointer-batched QK/PV path remains restricted to speculative
queries of at most four tokens. On the 257-token cached-turn quality shape, batch-1 agreement is
505/512 with 10/16 exact prompts versus the retained 504/512 and 10/16 gate. At batch eight, the
matched BF16-prefill/FP8-decode control is 502/512 and 9/16 exact, while FP8 suffix is 503/512 and
8/16 exact. The aggregate gate is non-regressing, but the changed exact-prompt membership is
recorded rather than described as a quality improvement.

The more important gain came from admission order. FIFO could admit a new cache miss while a
continuation matching an idle multi-thousand-token slot waited behind it, making small timing
changes cause expensive prefix eviction. Admission now selects the queued job with the longest
resident prefix and bounds starvation by forcing the FIFO head after four bypasses. On a fixed-work
64-conversation/c16/ten-turn run, this alone reduces recomputed input from 374,421 to 341,937 tokens,
raises throughput from 480.87 to 501.87 output token/s, and improves p95 TTFT from 472 to 280 ms.

The combined cache-affine and FP8-suffix policy reaches 516.32 output token/s when model EOS is
ignored solely to fix the benchmark at exactly 81,920 outputs, 7.37% above the matched native
control. With ordinary production EOS semantics it reaches 483.65 output token/s. Cached TTFT
p50/p95 is 153/309 ms, TPOT p50/p95 is 24.60/39.40 ms, and request time p50/p95 is 3.28/5.22 s.
This is 53.1% above the measured 315.94 token/s SGLang agentic control and 6.4% above the prior
454.5 native mean. The observed token mix grosses $1.825/hour at $0.08/M uncached input,
$0.01/M cache read and $0.35/M output: 40.55% of a $4.50 H200, leaving approximately $1,953 per
730-hour month of compute uncovered.

Quantizing full cache-miss prefill projections to tensor-scaled E4M3 was tested and rejected.
Allowing every chunk shape up to 1,024 tokens caused pathological startup latency because the
sixty Gemma projection shapes each acquired a new exact-row cuBLASLt plan for irregular prompt
tails. Restricting FP8 to the prewarmed exact 1,024-token chunks removed that failure and preserved
the retained quality gate exactly (504/512 teacher-forced predictions and 10/16 exact prompts),
but did not improve the complete workload. Two fixed-work candidate runs reached 511.34 and
511.63 output token/s (511.49 mean), versus 513.24 for a same-binary BF16-prefill control, despite
the candidate recomputing slightly fewer input tokens. Candidate median first-turn TTFT was
1.96--2.22 seconds versus 1.85 seconds for control. Full cache-miss prefill therefore remains BF16;
future prefill quantization must fuse activation conversion into the projection or otherwise show
an end-to-end gain rather than relying on the nominal FP8 GEMM peak.

Replacing the global-attention softmax's accurate exponential with Hopper's fast intrinsic was
also below the retention threshold: the saturated B16 primitive moved from 0.2831 to 0.2817 ms
and the ragged path from 0.2839 to 0.2833 ms. Materializing unnormalized BF16 probabilities to
avoid the second exponential reached 0.2823/0.2820 ms at B16 but regressed the latency-sensitive
B1 contiguous path from 0.0410 to 0.0447 ms. These sub-percent saturated changes cannot materially
move the full graph. The remaining global-attention opportunity is eliminating score traffic and
reusing K/V tiles in a Hopper warpgroup/TMA schedule, not approximating scalar softmax arithmetic.

CUDA 13 grouped GEMMs were also tested as an exact-context alternative to padding every ragged
global-attention row to the longest request. Grouping a deliberately wide 4k--8k B16 spread into
256-token context buckets reduced the isolated QK/softmax/PV primitive from 0.2798 to 0.2618 ms,
but narrower 5.6k--8k and 7.2k--8k spreads were neutral or slower. A conservative runtime gate
selected the path only at batch 12 or above when mean padded context was at most 78% of the
maximum. Primitive output was bit-exact for shuffled physical slots, and the forced B16 quality
run reached 505/512 teacher-forced agreement with 11/16 exact prompts. Nevertheless, the gate
activated on 1,773 sustained decode steps and reduced fixed-work agentic throughput from the
same-binary 513.24 to 508.74 output token/s (-0.88%). Cached TTFT p50 increased from 168.2 to
172.2 ms and TPOT p50 from 23.0 to 23.2 ms. Host grouping, extra pointer setup, and less efficient
small GEMM shapes outweigh saved padded KV traffic on the real distribution, so the implementation
was removed. Exact ragged contexts remain a target for a single persistent fused kernel, where
context specialization does not multiply launches or library dispatch overhead.

## Native speculative verifier frontier (2026-08-23)

The retained verifier no longer materializes each sliding layer's 1,024-token ring. It writes the
proposal K/V rows directly into the physical cache, backs up only the overwritten proposal span,
and repairs the few future causal positions around a pointer-batched QK/PV operation. The wrapped
ring path is checked against a scalar reference at draft depths four and eight. At a 6,000-token
context, the warmed depth-four verifier fell from 68.47 ms with ring materialization to 26.3 ms.

Global attention had a separate shape cliff: H200's selected BF16 QK algorithm took about 0.83 ms
at 6,005 keys but 0.105 ms at 6,016. Verification now rounds the masked global-KV extent to a
64-token bucket. Unread cache tails are zero initialized and causal softmax masks those columns,
so this changes work selection rather than model probabilities. The complete B16 verifier improved
from roughly 36.4 to 26.2 ms at the 6k benchmark position.

On 16 parallel coding-agent continuations with 64 new input tokens, 64 output tokens, and 99.0%
prefix reuse, target-only reaches 704.9 output token/s with 277 ms median TTFT, 18.45 ms median
TPOT, and 1.440 s median request time. Retained depth-four speculation with a shrinking-cohort tail
policy produced 826.5, 831.6, and 870.5 token/s in three explicit minimum-one runs (831.6 median,
18.0% over target-only); median TPOT was 12.67--12.97 ms in the two repeat runs. A cohort must still
meet the configured batch threshold to start speculation, but once started it remains speculative
as requests finish. This avoids making an isolated low-traffic request pay speculative overhead.

The next launch-control pass submits each global layer's positioned QKV work as one batch and
reduces all vocabulary rows with two argmax launches rather than two launches per row. Three
fixed-work runs reached 842.8, 894.2, and 916.3 output token/s (894.2 median, 26.9% over target-only),
with 277 ms median TTFT, 12.0 ms median TPOT, and 1.04 s median request time in the median run.
Argmax now occupies only about 47 microseconds of a verification trace. A single device pointer
table also replaces 100 synchronous per-layer backup/restore pointer copies; reusing that table
inside attention reduces the warmed 6k verifier further to 23.8--24.1 ms without changing proposals
or target tokens. The remaining verifier trace is approximately 21.6 ms of GPU kernels and more
than 1,100 launches, making graph/persistent execution and dense FP8 projection kernels the next
frontier rather than host token selection.

Depths two and three reach 728.3 and 729.0 token/s. Depths five, six, seven, and eight reach 731.0,
728.0, 740.0, and 638.2 token/s. The extra accepted prefix does not repay recurrent draft cost, so
depth four remains the default. Skipping the assistant LM head for the forced first proposal is
bit-identical and reduces the isolated draft from about 7.38 to 7.20 ms.

Several variants were measured and rejected. Per-layer fixed FP8 activation scales made each
verification cycle about 4% faster but reduced acceptance enough to fall to 758.9 token/s; the
coarse all-shape version reached only 674.2. Prompt n-gram drafting reached 368.9 token/s with
38.6% accepted proposals. A scalar-CUDA fused ring online-attention kernel passed the numerical
reference but took 94.6--99.8 ms per verifier with 8- and 32-token tiles, versus 26.3 ms for the
tensor-core cuBLAS path. A future fused kernel therefore needs a WGMMA/CUTLASS tensor-core schedule,
not merely fewer launches and score writes.

Live exact-completion A/B remains an invalid quality oracle for this tensor-wide FP8 runtime:
target-only repeats on identical fixed prompts produced different completions as asynchronous
batches changed activation scales. Speculative promotion still requires direct-runner rollback
parity plus teacher-forced agreement on the untouched holdout. The production service remains on
the pinned SGLang image until that quality gate and a production canary are explicitly approved.

## Tensor-FP8 weight calibration (2026-08-23)

The tensor-wide weight scale now accepts an explicit multiplier while activation quantization
retains its measured dynamic maximum. This permits startup-only clipping without changing the
stored one-byte weight layout, decode kernels, launch count, or HBM traffic. A multiplier of 0.98
was selected on the held-out coding-agent prompts using completion-level evidence rather than the
short teacher-forced score alone. Over 16 prompts and 128 free-running tokens, EOS-aware mean token
edit similarity against the serial BF16 runner rose from 0.8364 to 0.9519 and the minimum rose from
0.2656 to 0.6797. Batched BF16 measured 0.9612 mean and 0.5431 minimum on the same gate. Exact EOS-
truncated sequences did not improve over baseline (7/16 for each, versus 13/16 for batched BF16),
so calibration is a strong numerical candidate but not a complete functional-quality proof.

The matched five-session causal A/B showed no material execution penalty: median TPOT moved from
6.055 to 6.089 ms, median TTFT from 45.260 to 45.294 ms, and speculative acceptance from 83.0% to
82.5%. The complete 30-session stationary replay then completed 300/300 requests with 6.242 ms
median TPOT versus 6.208 ms for uncalibrated FP8. Steady output was 77.125 versus 76.726 token/s,
SLO output was 73.049 versus 73.067 token/s, and cheapest-price steady SLO compute recovery was
11.6034% versus 11.5793%. Paired mean TPOT changed by -0.082 ms with a 95% bootstrap interval of
[-0.290, 0.113] ms. The candidate is therefore performance-neutral within run noise.

`GRADIATED_FP8_WEIGHT_SCALE_MULTIPLIER=0.98` remains opt-in. Promotion still requires a task-level
coding/tool-use gate, explicit EOS-quality acceptance, and a production canary; the pinned SGLang
service is unchanged.

## Stationary session-live prefill frontier (2026-08-23)

The active prefill quantum was swept on one fixed Poisson/session-live manifest rather than on
simultaneous or isolated requests. The trace has 120 independent ten-turn conversations, 64-token
suffixes and outputs, 3.438 realized requests/s, 0.344 session starts/s, and approximately 90%
expected prefix reuse. Every point uses the same seed, arrival times, prompts, 24 slots, 23-slot
idle cache reserve, depth-four speculation, and cheapest-provider prices. All five traces are
stationary by session-birth/completion and backlog checks.

| Active prefill quantum | Steady output token/s | SLO output token/s | SLO cost recovery | Cold TTFT p50 | Continuation TTFT p95 | Continuation TPOT p50 / p95 | Request p95 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 128 | 190.650 | 169.302 | 21.397% | 4,060 ms | 404 ms | 7.58 / 16.48 ms | 1,331 ms |
| 256 | 190.754 | 170.139 | 22.161% | 2,470 ms | 368 ms | 7.20 / 15.88 ms | 1,236 ms |
| 512 | 190.913 | 171.653 | 23.342% | 2,429 ms | 393 ms | 7.19 / 16.71 ms | 1,244 ms |
| **1,024** | **192.073** | **172.509** | **23.626%** | 2,058 ms | **365 ms** | **6.95 / 16.04 ms** | 1,248 ms |
| 2,048 | 190.845 | 170.619 | 23.513% | **1,830 ms** | 462 ms | 7.03 / 17.17 ms | **1,226 ms** |

The 128-token policy repeatedly streams Gemma's weights and loses both TTFT and decode efficiency.
Increasing the quantum through 1,024 reduces total interference despite making each individual
prefill slice longer. At 2,048, cold TTFT improves another 11.1%, but continuation p95 TPOT
regresses 7.1% and SLO-qualified recovery falls slightly. The native runtime therefore defaults
both active and idle prefill to 1,024 tokens. An adaptive smaller quantum remains a possible
overload policy, but it is not promoted without a matched higher-pressure stationary frontier.

## Cooperative activation-quantization boundary (2026-08-23)

The cooperative E4M3 activation quantizer was extended from one to two million elements so medium
cached-suffix shapes can collapse their two streaming passes onto a resident grid. The threshold
is configurable rather than encoded in the launch policy. A same-image A/B used the stationary
session-live manifest above; Desmond tracing, the 1,024-token prefill default, model state, and all
other runtime settings were identical.

| Cooperative maximum | Steady output token/s | SLO output token/s | SLO cost recovery | Cold TTFT p95 | Continuation TTFT p95 | Continuation TPOT p50 / p95 | Request p95 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1,048,576 | 191.026 | 171.270 | 23.481% | 7,089 ms | 379 ms | 7.04 / 17.25 ms | 1,269 ms |
| 2,097,152, run A | 190.265 | 171.430 | 23.868% | 6,480 ms | 365 ms | 6.99 / 15.90 ms | 1,208 ms |
| 2,097,152, run B | 191.227 | 172.308 | 23.774% | 6,287 ms | 366 ms | 7.14 / 15.90 ms | 1,239 ms |

The two candidate runs average 190.746 raw and 171.869 SLO-qualified output token/s. Raw throughput
is therefore neutral (-0.15%), while SLO output rises 0.35%, SLO recovery rises 1.45% relative,
and continuation p95 TPOT falls 7.86%. Across the different causal schedules, the candidate
processed 31,493 suffix tokens in 16.54 seconds on average versus 28,786 in 17.40 seconds for the
control: about 13.2% less measured suffix-prefill time per token. The repeated tail improvement
and direct suffix counter retain the two-million-element default; the environment override remains
for regression controls.

## Matched high-rate SGLang control (2026-08-23)

The retained native image and pinned production SGLang defaults were replayed against the same
120-session manifest at 3.438 realized requests/s. SGLang used BF16, TP1, 16 running requests,
8,192-token context, and an 85% static-memory fraction. Native used its quality-gated tensor-E4M3
decode, depth-four assistant, 24 cache slots with a 23-slot idle reserve, 1,024-token prefill
quantum, and the two-million-element cooperative quantizer.

| Runtime | Trace wall time | Cache ratio | Steady output token/s | SLO output token/s | SLO request ratio | Continuation TTFT p50 / p95 | Continuation TPOT p50 / p95 | Request p95 | Session backlog change | Post-arrival drain |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Native | 398.1 s | 89.0% | 191.23 | 172.31 | 91.2% | 66 / 366 ms | 7.14 / 15.90 ms | 1.24 s | +1 | 49.1 s |
| SGLang | 1,497.3 s | 4.5% | 48.84 | 0.91 | 1.5% | 107,304 / 120,100 ms | 238 / 360 ms | 136.59 s | +29 | 1,148.3 s |

SGLang repeatedly reported a full KV pool and retracted requests after each had gained roughly
5,000--7,500 tokens. It completed all requests without transport errors, but session completions
did not keep pace with births, so its apparent steady-window economics are not an admissible
capacity point. The fixed-work comparison remains valid: native finishes the trace 3.76x sooner,
sustains 3.92x the steady output rate, and reduces measured compute cost per million output tokens
from $27.04 to $7.11. Native's 189x SLO-output ratio is real for this offered load but should be
read as SGLang overload collapse, not as an isolated-kernel speedup.

The control also establishes that the dominant realistic-load advantage is cache-system behavior,
not just faster decode kernels. SGLang reused 4.5% of presented input while native reused 89.0%,
allowing the native runtime to remain stationary and preserve low decode tails. Future SGLang
comparisons must either lower offered load until its backlog is stationary or explicitly test a
tuned cache policy; this default control cannot support the target traffic economically.

## Rejected GPU verifier commit and graph replay (2026-08-23)

Moving greedy proposal acceptance and accepted-hidden-state commit from the host to CUDA passed a
new deterministic integration test across 16 physical slots. The test covers mixed acceptance
caps, direct hidden commit, wrapped sliding-ring rollback, replacement tokens and the following
decode. Packing proposals, positions, slots, caps and target tokens into one transfer and using one
dedicated stream reduced the warmed 6k-context verifier from a 23.705 ms frozen median to 23.532 ms
in matched three-run measurements. This is only about 0.7% and did not survive causal scheduling.

On the same five-session Poisson manifest with every request fixed to 64 output tokens, host commit
completed 3,200 outputs at 46.003 token/s with 6.045/7.719 ms p50/p95 TPOT. GPU commit reached
45.863 token/s with 6.054/7.730 ms TPOT and required 825 speculative cycles instead of 814. The
change is therefore a small end-to-end regression despite its isolated verifier win and is removed.

Exact-position CUDA graph replay established a larger theoretical launch-control opportunity: the
warmed verifier fell from 23.532 to 22.276 ms, a 5.3% verifier improvement and about 4.1% of the
combined draft-plus-verify cycle. A bounded canonical graph key based on batch, depth, global
64-token context buckets and slot topology was not correct for live FP8 execution. In fixed-work
traffic it reduced proposal acceptance from 82.0% to 59.3%, increased speculative cycles from 825
to 1,167 and regressed p50/p95 TPOT from 6.054/7.730 to 8.133/15.201 ms. Both graph variants are
removed. Recovering the measured replay ceiling requires refactoring every dynamic position,
pointer, scale and work-selection input into an explicit device-resident graph contract; inferring
equivalence from host branch outcomes is insufficient.

## Exact shared-projection global KV representation (2026-08-23)

Gemma 4 global attention projects only one 2,048-wide KV tensor. For each 512-wide physical head,
the released graph stores V as the BF16-rounded RMS-normalized projection and stores K as the same
unrounded normalized projection multiplied by the learned K-norm weights and then RoPE-rotated.
This creates a model-specific opportunity to avoid reading independent K and V vectors.

A first probe reconstructed K from the stored BF16 V, applying the K-norm weights and RoPE after
V's rounding. It was rejected on the 24-prompt, 128-token free-running coding-agent holdout. Against
the exact control artifact it retained 2,376/3,072 token positions, 0.9410 mean edit similarity and
only 11/24 exact continuations (14/24 through EOS). The approximation changes rounding order and is
not a valid cache compression policy.

The exact representation instead stores the original BF16 shared projection plus one FP32
inverse-RMS scalar per token and physical KV head. Inside an attention tile it reproduces V as
`bf16(raw * inverse_rms)` and K as
`bf16(raw * inverse_rms * k_norm_weight)` followed by the existing BF16 RoPE operation. This keeps
the checkpoint's arithmetic order while reducing global cache source storage and HBM reads from
two 512-element BF16 vectors to one vector plus four bytes. Realizing the byte reduction requires
the planned fused Hopper kernel: materializing K/V back to HBM before separate QK and PV GEMMs would
erase it. The next kernel prototype must prove bit-level K/V reconstruction first, then perform QK,
online softmax and PV from the same shared-memory tile using WGMMA/TMA or an equivalent schedule.

The two-stage correctness probe now proves that representation. It stages raw BF16 projection rows
and FP32 inverse-RMS values, reconstructs ordinary K/V, and compares against the original fused QKV
postprocessor. Positioned prefill and shuffled-slot ragged decode produce bit-identical K, V and Q
tensors in the CUDA operation suite. On the full 24-prompt, 128-token free-running holdout, the
same-binary baseline and raw-roundtrip candidate artifacts have the identical SHA-256
`0ac9f224e90e779057f7112cd710f9e8a275fd427d802c83805410c804a246ee`. The probe is opt-in through
`GRADIATED_SHARED_GLOBAL_KV_ROUNDTRIP=1` and intentionally materializes K/V; it establishes exactness
but is not enabled as a runtime optimization until fused attention consumes the representation.

## Hopper WGMMA global-attention tile (2026-08-23)

The first Hopper-native building block uses CUTLASS/CuTe C++ pinned at
`6c65a175668952f09bcbf66cb97a8de1b734b4a0` and compiles the engine for `sm_90a`. It executes the
exact global QK geometry as 64 tokens by eight queries by 512 dimensions with BF16 inputs and FP32
WGMMA accumulation. Its BF16 score tensor is bit-identical to the retained cuBLAS result on the
deterministic parity fixture.

The initial one-tile-per-CTA implementation used scalar BF16 copies into swizzled shared memory and
reached only 265 GB/s: 2.028 ms at B16/8k versus 0.141 ms for cuBLAS. Replacing that path with
128-bit `cp.async` tiled copies reduced it to 0.277 ms. A sweep amortizing 2--32 contiguous tiles per
CTA found 32 tiles best at B16 (0.167 ms, 3.21 TB/s) and two tiles best at B1 (0.0125 ms), while
cuBLAS remains faster at 0.141 and 0.0071 ms respectively. One persistent CTA per physical head was
also rejected at 12.2 ms because 64 B16 CTAs cannot occupy the 132-SM H200 while serializing 128
tiles each.

The standalone QK prototype is therefore not a runtime replacement. It establishes correct WGMMA
descriptors, swizzled layouts, vectorized asynchronous copies and the useful CTA-granularity range.
Its purpose is the next fused kernel, where the same tile must perform online softmax and PV before
discarding shared K/V, then consume the exact shared-projection cache. That composition can remove
the global score round trip and one of the two physical cache vectors; QK alone has no byte advantage
and is not expected to beat the highly tuned library GEMM.

The second building block fuses one complete 64-token tile: WGMMA QK writes scores to shared
memory, eight warps reproduce the BF16 softmax contract, and eight WGMMA PV tiles produce the
512-wide outputs without a global score tensor. Random Q/K/V output is bit-identical to the
cuBLAS/softmax/cuBLAS composition. A generic CuTe transposed value copy initially failed parity;
zero Q/K isolated it from softmax, and replacing that copy with aligned 128-bit global loads plus
explicit swizzled shared stores restored exact output. At B16/context64 the fused tile takes
0.0164 ms versus 0.0197 ms for the library composition; B1 is 0.0161 versus 0.0170 ms. This is a
correct, modest launch-level win, not yet an 8k result. Full context requires segmented online
softmax with partial max/sum/output reduction while preserving enough CTAs to occupy all H200 SMs.

A full-context split prototype carries FP32 PV accumulators across each segment, emits compact
max/sum/output partials, and combines segments with an exact log-sum-exp reduction. At 128 tokens
it differs from the retained composition by at most `0.00195312` BF16 units (`9.63e-5` mean). It is
not fast enough: B16/8k takes 1.322--1.407 ms across 4--32 tiles per segment versus 0.281 ms for the
retained composition. Batching all eight PV WGMMA tiles into one asynchronous commit group is
neutral. Cubin resource inspection reports 64 registers/thread, zero local memory and no spills;
the 138 KiB shared tile permits one CTA/SM. Runtime is dominated by per-64-token shared-memory
transitions and synchronization, not WGMMA issue or host launches, and the split path remains a
correctness scaffold rather than a runtime candidate.

This result makes the exact shared-projection representation operationally necessary. Separate
64 KiB K and 64 KiB V tiles consume too much shared memory to double-buffer while retaining query,
score and probability state. A single 64 KiB raw tile plus inverse-RMS scalars can be transformed
in shared memory into the exact weighted/RoPE K and normalized V views, reducing HBM bytes and
making a two-stage load/compute pipeline fit. The next integration changes global cache ownership
and QKV writes first, then replaces the split scaffold's two cache loads with that pipelined raw
tile; tuning the rejected two-vector scaffold further would optimize the wrong memory graph.

## Exact raw-KV Hopper attention frontier (2026-08-23)

The exact shared-projection representation is now consumed directly by benchmark-only Hopper
attention. A 64-token tile reads one BF16 raw vector plus its FP32 inverse RMS, reconstructs K with
the released K-norm/RoPE rounding order, reconstructs V as BF16 RMS-normalized raw projection, and
performs QK/softmax/PV without materializing K or V in global memory. Its output is bit-identical to
the same fused tile over separately materialized K/V. Increasing the transform CTA from 256 to
1,024 threads reduces the B16 tile from 45.9 to 24.3 microseconds, but the materialized tile remains
faster at 16.4 microseconds. Repeated normalization and RoPE are therefore material costs, not free
work hidden by the eliminated cache read.

Two one-buffer schedules were explored. Retaining the complete raw tile in registers across QK is
exact but compiles to 128--255 registers/thread plus 896--1,808 bytes of stack and regresses under
saturation. The RS-WGMMA schedule instead leaves raw in a 64 KiB shared tile and constructs only the
current 16-wide K or V fragment in registers. Its one-tile kernel has no spill; a two-fragment
variant uses 63 registers/thread, while four-fragment issue is faster locally but raises register
pressure. This proves the intended register-source tensor-core contract without a second 64 KiB
transformed tile.

The full-context RS path uses 128-thread CTAs, two resident segment CTAs per SM, online softmax and
a 16 KiB FP32 shared numerator so only one output fragment is live. At B16/context 8,192 its best
32-tile segment takes 1.0639 ms. That is 19.1% faster than the 1.3148 ms two-vector WGMMA scaffold,
and B8 improves from 0.6661 to 0.5458 ms, but the retained library QK/softmax/PV composition remains
far faster at approximately 0.282 ms. At context 128 the RS split differs from the materialized
library result by at most 0.00195312 with 0.0001535 mean absolute error, matching the expected FP32
online-reduction-order boundary.

Further issue variants were rejected rather than promoted. Eight QK fragments per commit regresses
B16 slightly to 1.0667 ms. A two-fragment asynchronous ping-pong path causes compiler-inserted
warpgroup dependency barriers, grows to 253 registers plus stack and regresses to 2.038 ms. A
four-warpgroup cooperative CTA attacks the real small-N issue bottleneck by splitting QK's reduction
and PV's dimensions, but a 512-thread block is limited to 128 registers/thread; the combined graph
spills more than 3.4 KiB/thread and is orders of magnitude slower. The cooperative benchmark is not
part of the normal sweep.

The retained evidence changes the integration decision. Exact raw KV is viable and measurably
better than the custom two-vector scaffold, but it is not yet competitive with the existing
batched-library memory path. Persistent cache ownership must not be changed until a schedule closes
most of the remaining 3.8x global-attention gap. Production remains on the pinned SGLang image and
none of these Hopper research kernels is selected by the model runner.

### Exact raw-KV issue and representation optimization

Source-level profiling showed that the first RS kernel was not limited by H200 HBM or WGMMA. It
used 252 registers/thread, reached roughly 12% occupancy, and spent most issue stalls on scalar
normalization, RoPE coefficient access and fragment construction. Pairing each low 16-component
tile with its RoPE-coupled high tile removed duplicated normalization and reduced B16/context 8,192
from 1.0639 to 1.026 ms. Specializing the released graph's `partial_rotary_factor=0.25` then removed
all cosine/sine work for 448 of 512 components and reduced it to 0.722 ms.

The retained kernel now keeps all eight FP32 PV numerators in registers, converts exact K and V
pairs with native BF16x2 instructions, and stores the 64 active RoPE frequencies in transposed
`[frequency, position]` order. Low and high head halves share each coefficient, eliminating three
of four coefficient loads. This reduced the B16 result to 0.5856 ms. Grouping two low/high pairs
per WGMMA commit reached 0.5472 ms; grouping four pairs regressed to 0.5737 ms. Packed BF16x2 PV
conversion produced the retained 0.5409 ms result. The context-128 parity boundary remains
`0.00195312` maximum and approximately `0.000158` mean absolute BF16 error.

The current result is 49.2% faster than the 1.0639 ms RS checkpoint and 58.9% faster than the
1.3148 ms two-vector scaffold. It is still 1.91x the approximately 0.283 ms materialized-library
path, so it remains a research kernel rather than a runtime selection. A 32-token half tile was
rejected at 1.278 ms because half-empty WGMMA and doubled barriers dominate. Shared key-norm
staging was neutral.

A two-warpgroup producer/consumer experiment tested whether scalar transforms could overlap SS-
WGMMA. Two 8 KiB transformed stages, Hopper mbarriers, dynamic 64/192 register redistribution and
maximum shared-memory carveout produced exact output and two CTAs/SM at 25% occupancy. It still
took 1.75 ms at B16/context 8,192. The saturated profile executed approximately 626 million
instructions, reported 60.5% cycles without an eligible warp, and was 3.2x slower than retained RS.

## Materialized FP8-KV cache-write frontier (2026-08-23)

The complementary approximate frontier quantizes global V once when a cache entry is written,
instead of transposing or quantizing it on every decode. Values use fixed `V * 64` E4M3 and are
stored directly in Hopper's K-major swizzled WGMMA layout. Softmax probabilities use `P * 448`;
an `E4M3 x E4M3 -> FP32` register-source WGMMA performs PV and applies the inverse product scale.
The active context length and physical cache capacity are separate kernel strides. The benchmark
deliberately validates a 6,144-token active context in an 8,192-token allocation to prevent a
compact-layout result from hiding a slot-stride error.

Moving the V transform to cache writes reduced the original B16/context-8k implementation from
1.7596 to 0.2810 ms. Register-source PV reduced it further to 0.2586 ms, and context segmentation
keeps at least 512 CTAs available for small cohorts. The final capacity-correct sweep is:

| Batch | BF16 K/V | FP8 K, BF16 V | FP8 K/V |
| ---: | ---: | ---: | ---: |
| 1 | 0.0406 ms | 0.0374 ms | **0.0363 ms** |
| 2 | 0.0531 ms | **0.0465 ms** | 0.0554 ms |
| 4 | 0.0892 ms | **0.0702 ms** | 0.0829 ms |
| 8 | 0.1537 ms | **0.1238 ms** | 0.1446 ms |
| 10 | 0.1881 ms | **0.1542 ms** | 0.1602 ms |
| 16 | 0.2832 ms | **0.2194 ms** | 0.2559 ms |

At B16 the complete FP8-KV call is 9.6% faster than BF16 but 16.6% slower than retaining BF16 V.
Profiling reports 1.67 TB/s, 34.66% DRAM utilization, 42.41% compute utilization, 90 registers per
thread and 23.83% achieved occupancy; 64.12% of cycles have no eligible warp. The extra softmax
quantization and segmented PV reduction consume most of the bytes saved from V. Synthetic parity
against BF16 is 0.997857 cosine, 0.06545 relative L2, 0.001855 mean absolute and 0.01514 maximum
absolute error. K-only is better at 0.998600 cosine and 0.05290 relative L2.

Completion-level quality is the binding rejection. On sixteen held-out prompts and 128 generated
tokens, the retained tensor-FP8 projection control has 0.8714 mean edit similarity and 969/2,048
token agreement against serial BF16. FP8-KV on all ten global layers falls to 0.5344 and 284/2,048;
five layers `{11,23,35,47,59}` reach only 0.7013 and 541/2,048. K-only on those five layers is
slightly worse at 0.6724 and 483/2,048, establishing that the fixed-scale K representation—not V
alone—is the dominant numerical problem. A single layer 5 reaches 0.9560 mean similarity, but its
matched 50-request session-live A/B changes half the completions and produces no causal execution
gain: paired mean TPOT changes by +0.076 ms with a 95% bootstrap interval of
`[-0.434, +0.679]` ms, while SLO-qualified recovery falls by 0.000825.

`GRADIATED_FP8_GLOBAL_KV=1` therefore remains an explicit research boundary and production remains
on the pinned SGLang image. More WGMMA tuning cannot repair this representation. The next one-byte
cache candidate must first improve K resolution—quality-gated symmetric INT8 or a block-scaled
format—before earning another full causal-traffic pass.
Shared staging and synchronization more than doubled instruction work; replacing 128 mbarrier
arrivals with named barriers regressed further. The implementation and public API were removed,
as were the earlier spilling register-retained and 512-thread cooperative implementations.

This closes the obvious on-the-fly shared-staging branch. The larger next avenue is cache-write
amortization: compute K-norm/RoPE and V normalization once when a token enters the cache, then store
materialized K/V in a quality-gated low-bit representation. Two FP8 vectors consume the same bytes
as one raw BF16 vector while avoiding reconstruction of every historical token on every decode
step. That path must pass free-running coding-agent quality, prefix-cache capacity and realistic
Poisson-load economics before replacing exact raw KV.

## Block-scaled INT8 KV quality frontier (2026-08-24)

The INT8 frontier starts as a representation oracle rather than a performance claim. Each selected
global K or V block is quantized symmetrically to `[-127, 127]` using its dynamic absolute maximum,
then immediately dequantized into the existing BF16 cache. Attention, cache ownership and GEMMs are
unchanged. This isolates the error of a future one-byte cache while avoiding an expensive INT8
kernel implementation before the format passes quality. An eventual block-128 layout needs four
scales per 512-byte vector: 3.125% overhead with FP32 scales or 1.5625% after a separately validated
FP16-scale conversion.

On the sixteen-prompt, 128-token free-running coding-agent holdout with tensor-FP8 projections at
weight multiplier 0.98, fixed E4M3 K/V had only 0.5344 mean edit similarity. Dynamic INT8 is much
closer to the projection-only control, but generation bifurcation makes the block sweep
non-monotonic:

| Cache approximation | Exact | EOS-exact | Token agreement | Mean edit | Minimum edit |
| --- | ---: | ---: | ---: | ---: | ---: |
| Projection-only control | 3/16 | 5/16 | 969/2,048 | 0.8714 | **0.4688** |
| INT8 K only, block 512 | 1/16 | 6/16 | 780/2,048 | 0.8081 | 0.2578 |
| INT8 V only, block 512 | 1/16 | 5/16 | 815/2,048 | 0.7929 | 0.2344 |
| INT8 K/V, block 512 | 2/16 | **9/16** | 1,114/2,048 | 0.8712 | 0.3203 |
| INT8 K/V, block 128 | 2/16 | **9/16** | **1,175/2,048** | **0.8853** | 0.2656 |
| INT8 K/V, block 64 | 2/16 | 8/16 | 931/2,048 | 0.7737 | 0.2969 |

The same variants were therefore compared teacher-forced, always appending the BF16 reference
token so every prediction measures one-step perturbation at the same context. The projection-only
control matches 2,009/2,048 predictions (98.0957%). Block-512 INT8 K/V matches 2,017 (98.4863%),
block 128 matches 2,018 (98.5352%), and block 64 matches 2,013 (98.2910%). Block 128 is the current
format candidate: it improves this one-step gate despite quantizing all ten global K/V caches and
is the best free-running aggregate point. It is not promoted because its worst free-running prompt
still regresses and no one-byte storage or INT8 tensor-core attention exists yet.

The next implementation stores signed bytes plus per-block scales at cache write, then benchmarks
an `S8 x S8 -> S32` QK/PV composition before committing to a custom WGMMA schedule. Q is dynamically
quantized per query block; score scaling must be applied before softmax. For V, each probability is
premultiplied by its V-block scale before probability quantization. Only after numerical parity,
held-out quality and causal traffic pass will the BF16 cache be removed. Production remains on the
pinned SGLang image.

### Materialized S8 QK execution baseline

The first physical one-byte primitive stores each 512-component BF16 K row as signed INT8 plus one
FP32 dequantization scale. Decode queries are quantized by the same row contract. cuBLAS performs
`S8 x S8 -> S32` QK; a custom softmax applies the query and per-token K scales before exponentiation,
and the retained BF16 GEMM performs PV. Cache-write quantization is outside the timed decode call,
while mandatory query quantization is included. At an active context of 6,144 inside an 8,192-token
allocation, output parity against BF16 is 0.999934 cosine, 0.01152 relative L2, 0.000321 mean
absolute and 0.001953 maximum absolute error—substantially better than fixed E4M3 K.

| Batch | BF16 K/V | Fixed E4M3 K | Dynamic S8 K |
| ---: | ---: | ---: | ---: |
| 1 | 0.0408 ms | **0.0378 ms** | 0.0484 ms |
| 2 | 0.0540 ms | **0.0472 ms** | 0.0627 ms |
| 4 | 0.0899 ms | **0.0707 ms** | 0.0867 ms |
| 8 | 0.1543 ms | **0.1234 ms** | 0.1390 ms |
| 10 | 0.1885 ms | **0.1497 ms** | 0.1692 ms |
| 16 | 0.2841 ms | **0.2240 ms** | 0.2398 ms |

At B16 the quality-compatible representation reduces attention latency by 15.6% versus BF16, but
is 7.1% slower than the rejected fixed-E4M3 path. B1 loses because dynamic query reduction and
scale-aware softmax cost more than the saved K bytes. The S32 score tensor is also twice the size
of the BF16 score tensor and is reread with K scales during every softmax pass. This is the measured
reason to build block-128 WGMMA rather than an assumption: the custom kernel must accumulate four
scaled S32 partial dots into FP32 on chip, apply online softmax, and avoid materializing scores.
Only that composition can combine the block-128 quality result with the byte reduction at low and
high cohorts.

### Hopper block-128 S8 QK and physical-cache decision

The block-128 format was subsequently implemented as a Hopper-native QK path rather than another
materialized-score cuBLAS composition. At batch 16 and context 8,192, runtime-selected tile 8 takes
approximately 0.234 ms versus 0.284 ms for retained BF16 attention, an 18% attention-call
improvement. Decode cache writes now form normalized/RoPE-applied BF16 K once and, in the same QKV
kernel, reduce four 128-component maxima and emit bit-identical signed bytes and scales. This
removes the separate cache reread and quantization launch. The fused writer is tested over ragged,
non-contiguous slots against the original standalone quantizer, including bit-identical Q, BF16 K/V,
INT8 K, and FP32 scales.

Physical completion quality is stricter than the representation oracle. Quantizing K in all ten
global layers produced only 1,025/2,048 token agreement and 0.8163 mean edit similarity on the
sixteen-prompt free-running holdout; full physical V was worse. A layer-subset search found
`{5,29,59}` to be the strongest strict-gate candidate. On an independent 64-task, 512-token
HumanEval holdout, both the tensor-FP8 control and this candidate pass 61/64 tasks, with zero task
regressions or improvements. Its free-running aggregate has 0.9805 mean edit similarity and 0.8038
minimum edit similarity against the control.

The quality-safe subset still fails the causal-traffic promotion gate. A clean-container A-B-B-A
run replayed the same 50-request, five-session, approximately 90%-cached manifest with speculative
decoding enabled at batch one. Both control runs delivered 39.52 output tokens/s; candidates
delivered 39.50. Across the two nearest brackets, candidate paired mean TPOT changed by +0.0212 ms
(`[-0.0106,+0.0487]` 95% bootstrap interval) and +0.0120 ms
(`[-0.0203,+0.0403]`), while throughput changed by -0.053% and -0.040%. Compute recovery fell by
0.0039 and 0.0030 percentage points. The result is consistent with the cost of quantizing every new
K exceeding the attention savings from changing only three of sixty-two layers.

The physical INT8 implementation remains as reproducible research infrastructure, but production
must leave it disabled. More tuning of this cache branch cannot materially move whole-model
economics under the validated quality constraint. The next decode target is the model-wide
bandwidth frontier. The retained tensor-FP8 projections already sit at their one-byte weight-stream
floor, so a material next step must reduce precision across repeatedly executed layer weights rather
than infer a large opportunity from one isolated matrix.

## Physical W4A8 target LM-head frontier (2026-08-24)

The 262,144-way tied embedding was used to establish a physical Hopper W4A8 path before changing
model-wide projection precision. Each 256-component group is quantized to signed INT4 and carries
an eight-entry E4M3 lookup. CUTLASS mixed-input scales use group-major storage
`group * output_width + row`; the initially assumed row-major order corrupted real weights while
constant-scale synthetic probes hid the error. The strengthened CUDA test varies scale across
K-groups, includes values above the E4M3 `-8 * scale` overflow boundary, and reports at least
0.999999 physical/oracle cosine with zero argmax mismatches over seventeen shapes. The physical
and representation-oracle heads also agree on all 512 predictions of the short real-model gate.

The complete one-kernel head takes 0.196--0.211 ms for one to 32 rows versus 0.330--0.355 ms for
the tensor-FP8 GEMM, a 39--42% isolated reduction. This does not imply an 11% verifier gain. The
authoritative B16/context-6k Nsight trace contains one 0.349 ms target-head GEMM, only 1.6% of
21.6 ms of verifier GPU kernels. An earlier reading of this trace incorrectly attributed 26% to
the head; that figure is withdrawn. The mixed-input reorder also occupies approximately 1.45 GB,
and the opt-in path retains the original FP8 embedding, so this experiment does not reduce current
runtime residency.

Quality remains acceptable at the task boundary. On the independent 64-task, 512-token HumanEval
holdout, tensor-FP8 control and W4A8 both pass 61/64 tasks with zero regressions or improvements.
The corrected full-vocabulary artifact has 11,632/32,768 token agreement and 0.9542 mean edit
similarity against control, illustrating why task-level execution is the binding gate rather than
exact free-running token identity.

A clean-container A-B-B-A replay then used the same 50-request, five-session, approximately
90%-cached session-live manifest, FP8 multiplier 0.98, FP8 assistant LM head, 23 idle cache slots,
and depth-four speculation starting at batch one. Candidate median paired TPOT improved by 0.0379
and 0.0381 ms, but paired mean TPOT changed by +0.0781 ms
(`[-0.1091,+0.3099]` 95% bootstrap interval) and +0.1965 ms
(`[-0.0504,+0.4621]`). Only 23/50 and 26/50 output sequences matched exactly; candidates emitted
117 and 155 fewer tokens, making their 4.1% and 5.3% lower raw output rates different-work results.
SLO compute recovery fell by 0.0381 and 0.0366 percentage points.

The fixed-state B16/context-6k A-B-B-A removes that output-length confound. W4A8 reduces verifier
time from 23.8148 to 23.5910 ms and from 23.7187 to 23.4688 ms: 0.94% and 1.05%. Combined
draft-plus-verify time improves by 0.73% and 0.89%, consistent with the corrected profile bound.
This is a valid primitive but not an economically promotable LM-head-only policy. The implementation
remains opt-in infrastructure for model-wide W4 experiments; production remains on the pinned
SGLang image with both physical INT4 switches unset.

## Selective model-wide W4A8 frontier (2026-08-24)

The physical mixed-input path now supports 64-, 128-, and 256-column output tiles and 128- or
256-component quantization groups. Exact Gemma projection shapes were weighted by their model
multiplicity rather than summarized from the vocabulary head. Applying W4A8 to every projection
is neutral through batch eight and regresses larger cohorts by up to approximately 3.4%. The
winner is shape selective: QKV, gate/up, and the vocabulary head use W4A8 while O and down
projections remain tensor E4M3. The resulting combined-linear primitive bound is 12.0%, 12.4%,
12.9%, 13.8%, 10.2%, and 8.0% at batches 1, 4, 8, 16, 32, and 64 respectively. This is an upper
bound on whole-model improvement, not an integrated throughput result.
The primitive also omits the tensor-wide FP8 input/weight scale because that factor is irrelevant
to LM-head argmax; an internal projection integration would have to fuse that scale into its
consumer. Its cost is therefore absent from the bound.

Neither Stream-K nor explicit split-K improved the underfilled Gemma shapes. Both were slower on
the wide QKV/gate/head matrices and stalled on several O/down geometries, so the scheduler
experiments were removed. A 64-component physical quantization group is also unsupported by the
selected CUTLASS mixed-input contract and is rejected at construction; the representation oracle
may still use it for quality research.

Quality prevents promotion. On the 24-prompt, 32-token coding-agent holdout, the matched tensor-FP8
control reaches 760/768 teacher-forced predictions, 17/24 exact sequences, and 0.990885 mean edit
similarity. Group-256 selective W4 reaches 736/768; group 128 improves to 741/768 but remains well
outside the gate. Isolated group-128 QKV, gate/up, and LM-head variants reach 757, 751, and 754
predictions respectively, showing that no single component explains the accumulated error.

An iterative load-time least-squares scale refinement was then validated against the physical
packed representation: at group 128 and four iterations, physical and oracle GEMMs have at least
0.999999 cosine and zero argmax mismatches over 17 rows. It does not improve model quality. Full
selective W4 with 1, 2, 4, and 8 refinement iterations reaches 740, 742, 736, and 740 predictions;
the best two-iteration point has only 10/24 exact sequences. The refinement remains an opt-in
research knob, but no W4 projection policy is selected by the runtime. A future attempt must use
activation-aware calibration, error feedback, or a larger quality-safe layer subset search before
paying for another causal traffic run. Production remains on the pinned SGLang image.

## Fused GELU and tensor-FP8 activation frontier (2026-08-24)

The decode profile attributes approximately 7.8% of verifier GPU-kernel time to the cooperative
tensor-FP8 activation quantizer. An exact experimental kernel fused the BF16-rounded GELU-gated
down-projection input with its maximum reduction and E4M3 conversion. CUDA parity tests confirmed
bit-identical BF16 activation, FP8 bytes, and scale against the retained sequential operations.

At fixed batch 16 and context 6,000, A-B-B-A reduced verifier time from a 23.7356 ms control mean
to 23.5911 ms, or 0.61%; combined draft-plus-verifier time improved by approximately 0.5%. That
microbenchmark gain did not survive causal traffic. On the 50-request session-live replay, paired
mean request latency changed by -5.49 ms (`[-15.83,+3.53]` 95% bootstrap interval) and -1.21 ms
(`[-3.78,+1.41]`), while aggregate output throughput changed by -0.48% and -0.07%. Compute
recovery also fell slightly in both brackets. The cooperative grid synchronization and occupancy
cost erase the memory-pass saving under realistic mixed cohorts, so the implementation was removed.
Future activation work should avoid grid-wide synchronization, ideally by carrying quantization
metadata directly from a persistent producer into the projection consumer.

## Producer-carried RMSNorm amax (2026-08-24)

The successful replacement for the rejected cooperative fusion carries tensor-scale metadata out
of the existing RMSNorm producers. Input RMSNorm for QKV and the fused post-attention/residual/
pre-MLP normalization now reduce the maximum of their already-rounded BF16 output once per row.
The following E4M3 conversion derives the tensor maximum from that small row vector independently
in every CTA and reads the BF16 activation only for conversion. This removes the activation-wide
amax reread and the cooperative grid barriers without changing the tensor-wide quantization domain.

CUDA tests at the real 5,376-component hidden width establish bit-identical residual BF16,
normalized BF16, tensor scale, and E4M3 bytes against the prior path. The 16-prompt, 128-token
coding-agent quality gate is also exactly unchanged: all 2,048 candidate tokens match the retained
tensor-FP8 artifact bit-for-bit, with the same 2,009/2,048 BF16-reference agreement and 0.988883
mean token edit similarity.

At batch 16, depth four, and context 6,000, fixed-state A-B-B-A reduces verifier time from a
23.6713 ms control mean to 23.4379 ms, or 0.99%. Combined draft-plus-verifier time improves by
0.73%. Single-pair screens at batches 1, 2, 4, 8, and 16 all improve verifier time; observed gains
range from 0.55% to 2.66%, so there is no low-cohort reversal.

Two seeded causal A-B-B-A runs preserve the latency result. Enabling carried amax changes paired
mean TPOT by -0.1076 ms (`[-0.2278,+0.0048]`) and -0.2580 ms
(`[-0.4610,-0.1064]`). Reversing the deployed default and explicitly disabling it changes mean
TPOT by +0.1831 ms (`[+0.0645,+0.3320]`) and +0.0221 ms
(`[-0.0092,+0.0495]`). TTFT does not regress. Raw output rates vary with generation length because
the timing change alters dynamic cohorts and therefore tensor-FP8 batch scales; they are not used
to claim a kernel speedup beyond the fixed-state bound.

Producer-carried amax is enabled by default for tensor-FP8 QKV and gate/up projections. The
`GRADIATED_DISABLE_QKV_NORM_CARRIED_AMAX` and
`GRADIATED_DISABLE_GATE_UP_NORM_CARRIED_AMAX` controls retain reproducible rollback paths.

## Rejected direct speculative layouts (2026-08-24)

An exact layout experiment had the positioned QKV producer emit speculative queries directly as
`[request,head,token,dimension]`. For wrapped sliding attention, the ring-repair producer also
wrote its final output directly as `[request,token,head,dimension]`. This removed the explicit
token-to-head and head-to-token copies from 50 sliding layers while preserving every BF16 value;
the CUDA test compared both output layouts component by component.

The fixed-state result was initially compelling. At batch 16, depth four, and context 6,000,
verifier time fell from a 23.5039 ms control mean to 22.6451 ms, or 3.65%, and combined
draft-plus-verifier time improved 2.89%. Batch 2, 4, and 8 screens also improved by approximately
2.7%, while batch one was neutral. The candidate was therefore restricted to cohorts of at least
two requests before causal evaluation.

Both seeded 50-request session-live brackets rejected that policy. Candidate and control emitted
identical outputs, reused the same 295,542 prefix tokens, and executed the same 716 speculative
cycles with 3,220 proposals and 2,703 accepted tokens. Nevertheless, candidate verifier time rose
from 12.1746 to 12.3025 seconds and from 12.1857 to 12.2716 seconds. Paired mean TPOT regressed by
0.0630 ms (`[+0.0533,+0.0725]`) and 0.0355 ms (`[+0.0187,+0.0484]`); request latency regressed by
2.47 and 1.40 ms. Aggregate output rate fell 0.058% and 0.038%.

The removed copies were profitable in a continuously repeated uniform verifier shape but did not
repay the producer's strided stores and changed launch dependencies across the short-lived cohort
mixture produced by live scheduling. The implementation and its runtime switch were removed. A
future layout optimization must profile and optimize the producer-consumer pair on captured causal
cohort sequences rather than infer whole-runtime value from one fixed batch shape.

## Producer-carried GELU block maxima (2026-08-24)

Down-projection tensor-FP8 conversion was the next remaining activation reread. The first exact
implementation accumulated one maximum per GELU row with atomics and a preceding memset. It was
bit-identical but only improved the fixed B16 verifier by 0.29% and was neutral on low-rate causal
traffic. Having each thread produce two or four GELU values reduced atomics but regressed B16 by
0.52% and 0.40%; those variants were removed.

The retained producer preserves the original one-output-per-thread, 256-thread GELU geometry.
Every CTA writes its rounded-BF16 maximum to a unique scratch entry, so there are no atomics and no
initialization pass. One small CTA per row reduces the 84 block maxima, after which the existing
row-amax E4M3 converter derives the exact tensor scale. Scratch fits in the existing activation
scale arena. The complete sequence emits bit-identical BF16 activations, tensor scale, and E4M3
bytes at Gemma's real 21,504-component intermediate width.

The extra partial-to-row launch has a cohort crossover. Fixed screens regress B2 by about 1.0%,
then improve B4, B8, and B16 verifier time by approximately 0.28%, 1.15%, and 0.61%. The policy
therefore activates only at 16 activation rows, corresponding to four depth-four speculative
requests, and retains the conventional converter below that threshold.

On a matched 400-request, 40-session, high-rate A-B-B-A replay, verifier time per proposed token
improved from 2,052.60 to 2,000.75 microseconds and from 1,965.96 to 1,955.97 microseconds: 2.53%
and 0.51%. Raw output throughput rose 0.64% and 1.01%. SLO-qualified output rose 0.40% and 2.41%;
mean queue time fell 37.1 and 50.8 ms, while mean TTFT fell 28.8 and 44.7 ms. SLO compute recovery
changed by -0.029 and +0.616 percentage points, averaging a 0.293-point gain. Paired TPOT was
neutral within wide dynamic-schedule intervals.

Only 44.0% and 46.8% of candidate/control request outputs matched exactly, but the two control
repetitions themselves matched only 45.0%. Small timing changes alter cohort-wide tensor scales in
this saturated replay. The deterministic quality gate removes that confound: all 2,048 candidate
tokens across 16 held-out coding prompts are bit-identical to the retained FP8 artifact, with the
same 2,009/2,048 BF16 agreement, seven EOS-exact prompts, and 0.988883 mean edit similarity.

Producer-carried GELU maxima are enabled by default for tensor-FP8 down projections at 16 or more
rows. `GRADIATED_DISABLE_GELU_CARRIED_AMAX` retains the rollback path.

## Producer-carried O-projection block maxima (2026-08-24)

The retained post-GELU profile left 61 cooperative tensor-FP8 quantizers in a depth-four B16
verifier. Sixty were O-projection inputs; the final one belongs to the target head. The O input is
already read and rewritten by the mandatory head-major-to-token-major attention transpose, so a
second full BF16 pass solely to find its tensor maximum is avoidable.

The head-to-token producer now preserves its original 256-value output blocks and writes one
maximum per block from the unchanged BF16 value. There are no atomics or initialization passes.
The first implementation reduced those values to one maximum per row in another launch. It was
numerically exact but only neutral at B16 because the reduction and conversion returned most of
the saved 0.404 ms cooperative pass. The retained implementation removes that launch: every FP8
conversion CTA reduces the compact block-max vector directly and derives the same tensor-wide
scale. The CUDA oracle uses a deliberately non-aligned 514-component row and establishes
bit-identical token-major BF16, E4M3 bytes, and FP32 scale against the original transpose plus
cooperative converter.

The retained B16 Nsight trace confirms the intended physical change: cooperative activation
quantization falls from 61 calls/0.404 ms to one final-head call/0.006 ms. Sixty carried O
conversions add 0.325 ms to the generalized producer-amax converter while the transpose is
unchanged within noise, leaving approximately 0.08 ms net kernel time rather than counting the
removed pass as a 0.404 ms whole-verifier gain.

The isolated crossover is real but the smallest cohorts are not retained. Single-pair screens
improved verifier time by 1.02% at B4, 1.65% at B8, and 0.83% at B16. A fixed-state B16 A-B-B-A
then improved 23.6306 to 23.2466 ms and 23.6732 to 23.3590 ms: 1.62% and 1.33%, averaging 1.48%.
Although B2 also improved in isolation, an initial live replay with an eight-row threshold changed
dynamic cohort composition without improving SLO economics consistently. The retained policy
therefore activates only at sixteen rows.

The stricter policy passed a matched 400-request, 40-session, three-arrival/s Poisson A-B-B-A with
the FP8 assistant, depth-four speculation, and 23 idle cache slots. Target verifier time per
speculative cycle improved from 16.5468 to 16.4804 ms and from 16.6667 to 16.5916 ms: 0.40% and
0.45%. Mean queue time fell 11.08 and 11.01 ms. Mean request latency changed by -4.99 ms
(`[-48.57,+34.34]`) and -42.33 ms (`[-74.57,-12.86]`); mean TPOT changed by +0.338 ms
(`[-0.097,+0.834]`) and -0.452 ms (`[-0.946,-0.030]`). SLO compute recovery rose by 0.099 and
0.171 percentage points.

Raw output rates fell because optimized runs generated 332 and 475 fewer output tokens. That is
different work, not evidence of lower kernel throughput: optimized/optimized outputs matched only
47.25%, while disabled/disabled repetitions matched 48.75%. The standard 16-prompt quality gate
was repeated twice with the retained default and produced identical 2,048-token candidate streams,
2,027/2,048 BF16-reference agreement, eight EOS-exact prompts, and 0.993492 mean edit similarity.

Producer-carried O maxima are enabled by default for tensor-FP8 speculative/suffix projection
cohorts of at least sixteen rows. `GRADIATED_DISABLE_O_TRANSPOSE_CARRIED_AMAX` retains an exact
rollback path.
