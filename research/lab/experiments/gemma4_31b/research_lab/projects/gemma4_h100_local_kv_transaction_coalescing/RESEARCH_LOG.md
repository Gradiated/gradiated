# Research log

## 2026-07-25T10:55:05Z — exact v0.5.15 transaction model

**Question.** Does the bound H100 page-size-one local-KV path expose a
payload transaction/coalescing reduction for a request-owned E5M2 ring?

**Action.** Bound official SGLang commit
`f63458b5beaceabbd9d749b9fc956370e1b649e6` through
`ReqToTokenPool`, the token/SWA allocators and full-to-SWA map,
`update_sliding_window_buffer`, and the exact Triton extend/decode kernels.
Ran `analyze_transactions.py` over all 1,036 rows and the exact 32×32 + 1×12
release groups. The CPU oracle checked aligned, chunk-segmented, and recycled
slot permutations plus padded/stale generation mappings.

**Evidence.** A local K or V slot row is 4,096 E5M2 bytes and every selected
head slice is 256-byte aligned. Thus every stock slot permutation and the
ideal ring require exactly eight 32-byte sectors and two 128-byte transactions
per K or V head slice. Payload reduction is exactly zero. Deleting the int64
index stream and replacing it with one optimistic packed ring scalar saves at
most 1.536888% of local consumer requested sectors (1.536622% of 128-byte
regions), before cache-hit suppression and unrelated endpoint work. Strict
endpoint lower relevance is zero. The client trace omits internal batch/chunk,
acceptance, allocator/free, and req-to-token events, so it cannot reconstruct
one live slot sequence or prove prefix/accepted-KV ring lifecycle.

**Interpretation.** `typed_none`: payload coalescing is already invariant;
only metadata remains, which is an explicit typed-none condition in the brief.
The prior H200 v0.5.13 3.10% endpoint result is not transferred.

**Next.** No implementation or H100 use. If the director reopens this
mechanism, run the checkpoint-free batch-32, qlen-12, prefix-1023 exact
v0.5.15 extend consumer and collect only L1 global-load, L2 read, and DRAM
read sectors. Payload-attributed L2/DRAM reduction or a correct latency gain
above the 1.55% local-sector ceiling falsifies this result.

Artifacts:

- `TRANSACTION_RESULT.json`
  (`0c897822359bb2035fc87d23562c8a33d3fcab73439ebcc10abfc640ad9ac71e`)
- `analyze_transactions.py`
- `test_analyze_transactions.py`
