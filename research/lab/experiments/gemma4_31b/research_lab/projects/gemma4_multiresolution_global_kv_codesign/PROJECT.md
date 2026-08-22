# Multi-resolution global-KV co-design

## Question

Can a source-complete multi-resolution KV path preserve every prompt token,
all 60 transformer layers, the exact 1,024-token local windows, and the full
model width while compressing only older state presented to Gemma 4's global
attention layers enough to reduce the locked exact-c32 service bound from
`0.625149101968745` to at most `0.500119281574996 s/request`, after complete
summary and runtime overhead?

This is a quality-unqualified physical discriminator. It is not permission to
delete tokens, layers, width, parameters, or vocabulary capacity.

## Why this matters

The hash-bound exact-c32 trace assigns `1,488,205.758 us` of its
`2,375,141.908 us` window to 900 `_fwd_kernel` attention calls, roughly 62.7%
of the window. That aggregate contains both sliding and global attention and
must be separated before credit. By contrast, all 3,600 FP8 CUTLASS GEMMs
together account for only `446,863.844 us` (18.8%), so a standalone routed-FFN
proxy cannot close the 20% target even before retaining useful computation.

Gemma 4 executes five sliding-attention layers followed by one global layer.
A multi-resolution path can leave every token's transformer and exact local
attention work intact while replacing only old global K/V positions with
information-carrying summaries. This is materially distinct from the
completed prompt-state compaction candidate, whose late GEMM rows are removed;
do not stack or transfer that result.

The completed tied-head route is preserved at
`../gemma4_hierarchical_tied_head_codesign/HIERARCHICAL_TIED_HEAD_PHYSICAL_SCREEN.json`
(SHA-256
`40b00f5bd09dfbb02420ca4535f80d024a9f2df01e3cfecedaf9f24afb54f206`);
its entire output consumer is only 5.61% of the trace and is closed for this
target.

## Bound evidence

- Exact checkpoint:
  `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Exact geometry:
  `../gemma4_hybrid_attention_placement_codesign/inputs/bound/config.json`
  (SHA-256
  `e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1`);
  60 layers, five-local/one-global ordering, 1,024-token sliding window,
  hidden size 5,376, 32 query heads, 16 KV heads, and head dimension 256.
- Exact-c32 trace:
  `../gemma4_h200_ngram_fixed_m384_executor_rewrite/inputs/trace/exact_c32_profile.trace.json.gz`
  (SHA-256
  `37e2c73a57e8e63bd7ec0a3465cc1edded8b9dc63507d97e85a767306a97a48b`).
- Pinned runtime source identity:
  `28b095c01005d4a3a2a5b637b7d028b07fba31b2`.
- Workload: c32, 4,214 prompt tokens, 358 output tokens, 535 cached-prefix
  tokens, and the locked denominator and target above.

## Scope

Run a zero-provider-spend source-and-physical-cost discriminator:

1. Join the 900 `_fwd_kernel` calls to exact layer type, phase, query rows,
   key positions, and runtime consumer. Separate global attention from local
   attention with source/shape/correlation evidence. If even free removal of
   the complete global-attention portion cannot hit the target, return typed
   `none` immediately.
2. Design a two-tier global-KV representation. Recent positions and all
   positions required by each 1,024-token sliding window remain exact. Every
   older prompt position must contribute mechanically to at least one
   nonempty, causally valid K/V summary used by global attention. All original
   token hidden states still execute every transformer layer.
3. Implement the production path from KV writes through summary construction,
   tier metadata, positions/RoPE semantics, paged request ownership, and the
   actual global-attention consumer for prefill, target verification, and
   ordinary decode. A summary builder, metadata-only patch, or arithmetic
   model that never reaches attention is not source-complete.
4. Charge summary K/V construction, reductions, normalization or learned
   weighting, exact recent-state retention, compact-page reads, page-table
   rebuilds, positions, graph variants, synchronization, fragmentation,
   fallback, and any duplicated exact/summary storage. Credit no late GEMM-row
   savings, local-attention savings, allocator capacity, batching, output-head
   work, or prompt-state compaction.
5. Report sensitivities for recent exact span, summary block size/count,
   protected prefix/tool positions, verification depth, fallback rate, and
   conservative non-scaling floors. The complete bound must reach
   `0.500119281574996 s/request`.

Do not download checkpoint bytes, claim a GPU, contact a provider, train a
model, or run broad quality evaluation. Leave later target-GPU timing,
distillation, GPQA-Diamond, TauBench, tool-call behavior, long-context
retrieval, and exact fallback calibration explicit.

## Success and invalidity

A physical candidate requires:

- every prompt token contributes to exact or summary global-KV state;
- every token still traverses all layers at full hidden width;
- local windows and their K/V consumers remain exact;
- source reaches the actual global-attention consumer in every claimed phase;
- trace attribution separates global from local calls; and
- conservative service time is at most
  `0.500119281574996 s/request` after all overhead.

Return typed `none` if the target requires token/layer/width/parameter
deletion, assumes all `_fwd_kernel` calls are global, drops old positions
without an information path, omits a claimed consumer phase, assumes free
summary construction or page remapping, or misses the target after overhead.
A future training recipe cannot qualify an invalid current mechanism.

## Terminal

Write `MULTIRESOLUTION_GLOBAL_KV_PHYSICAL_SCREEN.json` as exactly one of:

- `source_complete_physical_candidate`, with input and source identities,
  layer/phase trace attribution, information-path proof, full physical
  accounting, sensitivities, limitations, and separate quality-recovery path;
  or
- `typed_none`, with the strongest attempted design and the first attribution,
  information-path, source-consumer, or target failure.

## 2026-07-28 target-H200 execution reactivation

The source-complete physical screen is accepted as the causal discriminator,
not as endpoint evidence. The exact certified output-head line has now closed,
and this candidate is the strongest independent route with a direct path to
the locked target: `0.4999581203857146 s/request` after charged overhead,
only `0.00016116118928138912` below the
`0.500119281574996 s/request` threshold. That narrow margin makes an exact
target-runtime compile and component measurement more valuable than another
analytical refinement.

This is the same scientific project and intervention. First, without a GPU,
implement the smallest execution-equivalent H200 path:

- add `h200_component_runner.py`, which installs or imports the bound
  `multiresolution_global_kv.py` producer/consumer into pinned SGLang commit
  `28b095c01005d4a3a2a5b637b7d028b07fba31b2`, invokes the real global
  attention boundary for the exact prefill, ordinary-decode, and
  target-verification geometries, and emits correctness, compact-entry,
  fallback, compile, and timing records;
- add `h200_endpoint_owner.sh`, a controller-local command suitable for
  `research/factory/tools/detached-owner --unit-manager pid` that reads the
  assigned bench connection from `runtime/gpus.json`, stages only missing
  immutable inputs, preserves repair ownership, runs the component before any
  endpoint, and releases only after a decision-bearing terminal or the
  absolute deadline; and
- emit `H200_EXECUTION_READY.json` binding the runner, owner, intervention,
  pinned source, checkpoint, image, workload, and component command hashes.
  Source/unit tests and an exact CPU fixture must pass, but no static fixture
  may claim target-runtime correctness or measurement readiness.

Do not claim a GPU, call provider APIs, or inspect or mutate the live B200
while this offline implementation is incomplete. If it completes before an
H200 is registered, set the project `paused` with the exact H200 requirement;
do not spend another researcher cycle polling the pool.

The later paid execution requires one H200 SXM bench using
`docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6`
and the exact checkpoint
`google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
Use the qualified c32 workload identity
`7a05fa6218a5fbfd87744bca1ac491949ddd64bf0d58007b4d3569594f08225d`.
The director will select and register the provider resource only after this
project's `$8.00` cumulative reservation is visible.

On H200, use the first tiny real component call as the compile and integration
check, repair ordinary defects in the retained claim, then measure one
profiler-off stock/candidate component pair. Continue to one matched
stock-then-candidate c32 endpoint pair only if every claimed phase stays
within 64 compact entries, fallback is at most
`0.0012873226748728159`, correctness and request ownership pass, and the
component timing still admits the locked endpoint target. This remains a
quality-unsafe model-semantics proxy; no deployability, GPQA-Diamond,
TauBench, tool-path, or long-context claim is authorized.

Budgets are 45 minutes for offline runner integration, at most 150 minutes of
later provider lifecycle, at most 70 claimed H200 minutes for component plus
conditional endpoint work, 6 GiB of new non-checkpoint artifacts, and a
cumulative project spend ceiling of `$8.00`.
