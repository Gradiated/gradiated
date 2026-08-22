# Research log

## 2026-07-28 — internal local-attention fusion discriminator

Question: can a semantics-preserving change inside the exact window-1024
local-attention path remove launches or intermediate traffic?

Action: bound vLLM `6d4a8e6d` and FlashInfer `0.6.6` from the production inputs
through the first SM100 consumer. The pinned sources prove that each of 17,900
local-layer calls launches `reshape_and_cache_flash_kernel` before submitting
TRT-LLM Gen paged decode. Examined append+decode fusion as the distinct internal
boundary and generated the accounting artifact with a hash-checked source
packet.

Evidence: [B200_FP8_LOCAL_ATTENTION_FUSION_DISCRIMINATOR.json](B200_FP8_LOCAL_ATTENTION_FUSION_DISCRIMINATOR.json)
(`sha256:086d300d269eb82f3bcdbe187b851c12a09c9884e2844018c730af23f0f72ec9`).
A true device fusion would remove 17,900 standalone append launches and bypass
9,384,755,200 current-token cache-read bytes, only 0.09747% of the exact
9,628,758,835,200-byte local-KV path. It cannot remove the equally sized cache
writes or the 9,600,604,569,600 historical-KV read bytes.

Interpretation: typed rejection
`opaque_device_consumer_abi_excludes_fresh_kv_and_slot_mapping`. The exact
FlashInfer API and `TllmGenFmhaRunnerParams` do not carry fresh K/V or slot
mapping, and `TllmGenFmhaKernel` loads the selected device implementation as an
external hash-checked cubin. A host wrapper would still launch both kernels and
is not the intervention.

Next: do not reserve a B200 for wrapper fusion. Reopen only with the exact
TRT-LLM Gen SM100 device source/build path, or scope a separate source-complete
replacement paged-GQA decode kernel whose first target run consumes both the
cache side effect and every output.

## 2026-07-28 — source-complete local paged-GQA replacement

Question: does a source-complete SM100 path exist at the first-consumer
boundary, beyond the rejected host wrapper?

Action: resolved the pinned FlashInfer artifact selector to the exact
`QkvBfloat16/H256/PagedKv/Sliding/P16/MultiCtasKv/Q8/Kv128/Static/SwapsAb`
SM100f cubin (`sha256:a5ae26d06e8463baf3e1dac3251633b70ece90ca612a10afa6b09925578fd9be`).
Inspected the source-complete upstream alternatives at FlashInfer tag
`v0.6.6` (`70b142b7...`). The standard CUTLASS SM100 entry rejects d256 paged
GQA, the Blackwell paged source is MLA-specific, and fmha_v2 is not the
selected SM100 Gen path. The native batch-decode CUDA source does support
strided HND, BF16 d256 GQA2, page-16, and a sliding mask.

Intervention: added a custom native-decode attention variant that writes fresh
K/V from the int64 slot map inside the sole `(request, KV-head)` CTA, then
synchronizes before paged-GQA loads. It rejects split-KV and consumes only the
final 65 page indices, avoiding full 4K-sequence reads while masking exactly
the final 1,024 tokens. Added a one-shot B200 comparator against the exact
stock append plus cubin, with output, cosine, and whole-cache gates. The
official cubin, metainfo, and checksums are materialized read-only under this
project.

Evidence:
[B200_FP8_LOCAL_PAGED_GQA_REPLACEMENT_DISCRIMINATOR.json](B200_FP8_LOCAL_PAGED_GQA_REPLACEMENT_DISCRIMINATOR.json)
(`sha256:e302468b7d85b1465a309388cd40b5f70e3bac9dfd0103737887a104f3202d2d`).
Classification is source-complete but uncompiled and unexecuted. No B200 was
claimed, no CUDA or endpoint ran, and spend remained `$0`.

Next: only after a positive reservation and director lifecycle handoff, run
the hash-bound correctness pair once on B200. Do not time the candidate before
it passes the output and complete-cache gates.

## 2026-07-28 — reservation landed; execution awaits lifecycle binding

Question: does the durable `$4` reservation authorize the retained maintenance
B200 correctness generation?

Action: checked the named reservation gate and the exact pool row once at
`2026-07-28T19:33:29Z`. The campaign reservation is durable, but the immutable
pre-reservation gate still has `gpu_claim_authorized=false`; no newer
local-paged-GQA lifecycle or execution binding exists.

Evidence: bench `b200-nvfp4-computeinstance-i00rqcq5yzr6xc991j` remained
unclaimed and `maintenance` under the predecessor watchdog ending
`2026-07-28T19:40:00Z`. No GPU, CUDA, provider, ready, claim, or watchdog action
was taken; project spend remains `$0`.

Interpretation: typed external lifecycle boundary
`director_revalidation_and_execution_binding_absent_after_reservation`.

Next: the director must revalidate and bind the retained B200 before its
watchdog fence, or bind an exact replacement under the same reservation. The
next researcher then runs the one correctness-only generation from the
hash-bound bundle and repairs ordinary build or harness defects in that claim.

## 2026-07-28 — B200 local paged-GQA correctness execution

Question: can the source-complete fused append-plus-native-paged-GQA candidate
preserve the exact B32/H256/page-16/window-1024 contract?

Action: claimed the bound B200 at `19:41:53Z`, hash-bound the owner and
preclaim terminal, and ran the first exact target-GPU planner call in the
retained claim. A pre-science tar-over-SSH stdin defect was repaired in place;
the corrected attempt staged only the bound source bundle. No timing, endpoint
request, or model load was performed.

Evidence: the retrieved
[CORRECTNESS_TERMINAL.json](artifacts/b200-local-paged-gqa-correctness-20260728t1935z/remote-artifacts/CORRECTNESS_TERMINAL.json)
records `typed_rejection: split_kv_invalidates_single_cta_append_ownership` at
`build_candidate`; the adopted
[final terminal](artifacts/b200-local-paged-gqa-correctness-20260728t1935z/FINAL_TERMINAL.json)
hash is `f83e46...a578caaf`. The native exact plan requires split-KV, whereas
the candidate requires a sole `(request, KV-head)` CTA to append fresh K/V
before paged readers run. Thus its ownership invariant cannot hold.

Interpretation: decision-bearing typed negative, not a consumed comparison.
The bench was released to maintenance at `19:46:33Z`; conservative project
exposure from the reservation window through release is `$0.912`.

Next: do not replay this single-CTA design. Any successor needs a distinct,
split-KV-safe fresh-K/V ownership and visibility design.

## 2026-07-28 — split-KV tail-partition correctness

Question: can the final KV-partition CTA own cache persistence and merge fresh
K/V directly into its partial without a grid-wide visibility dependency?

Action: claimed the exact retained B200 at `19:51:57Z`, implemented and
hash-bound the split-safe owner, runner, preclaim record, and durable controller,
then launched at `19:56:55Z`. The native planner selected split-KV with padded
batch 64 and proved the unique tail rule from `kv_tile_indices` and `o_indptr`.
The one authorized stock/candidate correctness pair then consumed the complete
output and mutated cache. No timing, endpoint request, or model load ran.

Evidence: [terminal](B200_LOCAL_PAGED_GQA_SPLIT_KV_TERMINAL.json)
(`sha256:fe8ac1d3…3682b9c6`) adopts the raw
[correctness result](artifacts/b200-local-paged-gqa-split-kv-20260728t1948z/remote-artifacts/CORRECTNESS_TERMINAL.json)
(`sha256:646a3e0f…0ffe0f0e`). The candidate was finite but failed output allclose
(`cosine=0.9983367324`, `max_abs=3.203125`, `mean_abs=0.0034074`) and the entire
cache was not bitwise equal.

Interpretation: decision-bearing negative against this output-transform
tail-owner implementation. Unique split ownership is available, so the
single-CTA visibility objection is removed, but this submitted merge/persistence
path is not correct. Do not replay the consumed pair or time it.

Disposition: released the unoccupied bench ready at `19:57:14Z`, retaining
image/source/build/checkpoint caches. Conservative cumulative project exposure
is `$1.260` (`$0.912` prior plus `$0.347344` for this 316.566897-second claim).

## 2026-07-28 — split reducer source discriminator

Question: can the measured cache/output failures be localized and replaced by
one exact fresh-state insertion in the final split reducer?

Action: inspected only the hash-matched FlashInfer launch, partial-state,
variable-length reducer, paged-cache, and vLLM append sources. The tentative
`blockIdx.y` attribution is false: native decode launches `grid.y=num_kv_heads`
and derives the two Q heads with `kv_head*2+threadIdx.y`. The cache first
diverged because the prior stock comparator passed HND
`[page,head,entry,dim]` directly to an append ABI indexing
`[page,entry,head,dim]`; 240/256 head-entry offsets differ. The output first
diverged when the tail OutputTransform amended normalized `tmp_v` but left
`tmp_s` as prefix-only LSE.

Intervention: implemented a custom exact SM100a specialization that preserves
native split `(V,LSE)` partials, masks the stale final row, and merges fresh
`(V,QK*log2e)` once per Q head in the final reducer. Cache owner is
`qo_head%2==0`, with `kv_head=qo_head/2`, giving exactly one owner per KV head.
The corrected runner supplies an NHD-ordered append view over unchanged HND
storage, synchronizes/persists each arm separately, and consumes full output
and cache. The durable owner supports request-bound retrieval-only and
scientific-pair repairs.

Evidence:
[discriminator](B200_LOCAL_PAGED_GQA_SPLIT_REDUCER_DISCRIMINATOR.json)
(`sha256:f4c72322…e688d60a`), [target plan](B200_LOCAL_PAGED_GQA_SPLIT_REDUCER_PLAN.json)
(`sha256:2a121e45…e0d7633b`), and
[offline audit](artifacts/offline_split_reducer_source_audit.json)
(`sha256:99d3ede0…3c74f708`). All 16 KV heads have one owner; the reducer
algebra matches direct softmax to `1.11e-16` in FP64.

Interpretation: source-complete, materially distinct candidate. It is not yet
target-compiled or correctness-proven. No bench was claimed and no CUDA,
provider, timing, endpoint, model, or additional spend action occurred.

Next: only a new director lifecycle binding may activate the immutable plan.
Run the exact split plan and at most one new reducer correctness pair; do not
replay the consumed tail-output-transform implementation.

## 2026-07-28 — B200 split-reducer correctness pair

Question: does the distinct final-reducer mechanism preserve the exact B32
split-KV local-attention output and HND cache contract?

Action: under one continuous B200 claim, attempt 0 stopped pre-science at a
FlashInfer JIT unresolved group-1 kernel symbol (`candidate_science_started=false`).
The retained owner accepted repair `split-reducer-repair-0`: dispatch was
restricted to the admitted GQA2 geometry and the JIT URI was refreshed, with
no change to geometry, oracle, reducer algebra, or cache semantics. Attempt 1
then ran the exact plan and sole correctness pair; the owner released the
unoccupied bench available at `20:40:52Z`.

Evidence: [CORRECTNESS_TERMINAL.json](artifacts/b200-local-paged-gqa-split-reducer-correctness-20260728t2036z/CORRECTNESS_TERMINAL.json)
(`sha256: 2fcf2d76…d54e6573`) is `correct`: split-KV with padded batch 64,
finite output, max absolute error `0.015625`, cosine `0.9999980927`, output
allclose at `rtol=0.05, atol=0.03`, and entire HND cache bitwise equality.
It proves one owner for each of the 16 KV heads and one fresh merge per Q
head. No timing, endpoint request, or model load occurred.

Interpretation: the final-reducer mechanism is correctness-positive and is
materially distinct from the consumed tail-output-transform candidate. The
claim cost was `$0.178386`; cumulative assigned project exposure is
`$1.438386`. Wake the director to select a separately authorized timing run;
do not replay this correctness pair.

## 2026-07-28 — stock append/consumer decomposition

Action: after the correct custom reducer timed negatively, ran one exact B32
stock-only decomposition: append-only, pinned TRT-LLM Gen consumer-only, and
their composite, with eight warmups and forty CUDA-event samples per scope.
The candidate was not imported or executed; no endpoint or model load ran.

Evidence: [STOCK_DECOMPOSITION_TERMINAL.json](artifacts/b200-local-paged-gqa-stock-decomposition-20260728t2052z/STOCK_DECOMPOSITION_TERMINAL.json)
(`sha256: 6a33bbee…389a1b2a`) is interpretable with finite output and bitwise-equal
consumer/composite cache mutation. P50 timings are append `0.006112 ms`,
consumer `0.102432 ms`, and composite `0.108512 ms`; projected over 17,900
local calls, those are `0.109405 s`, `1.833533 s`, and `1.942365 s` per
request respectively.

Interpretation: append is only about 5.6% of the stock composite at this
geometry; the TRT-LLM Gen consumer is the material remaining boundary. The
B200 released available at `20:58:11Z`; cumulative assigned exposure is
`$1.691622`. Wake the director to rank an append-specialization route against
the independent runtime screen.
