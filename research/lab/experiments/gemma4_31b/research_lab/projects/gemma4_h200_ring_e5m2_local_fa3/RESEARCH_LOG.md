# Research log

## 2026-07-23 — admitted

Use `$kernel-research` for one exact direct-E5M2 FA3 consumer specialization over the settled contiguous ring. Prepare offline behind the width-plus-ring interaction; no stock paged rejection or full-cache conversion replay is allowed.

## 2026-07-23 — direct E5M2 FA3 component rejects

Question: can one FA3-v3 E5M2 specialization beat the settled ring consumer without converting the cache?

Action: pinned SGLang `28b095c0`, sgl-attn `bcf72ccc`, and CUTLASS `57e3cfb4`; compiled `cutlass::float_e5m2_t` head-256 packed-GQA kernels; consumed the circular ring as two zero-copy contiguous segments and merged output/LSE. The first H200 smoke passed at relative L2 `0.0028102`. The sole b32×1024 component covered wrap, a negative padded row, and two transition stress cases.

Evidence: production-shape output was finite with relative L2 `0.0041441`, cosine `0.99999332`, and max absolute error `0.0009765625`; padding was exactly zero. The candidate median was `0.39363199 ms` versus `0.26800001 ms` for `ring_decode_attention`, a `-46.8776%` point reduction with 95% interval `[-61.9609%, -39.3975%]`. The two unscaled transition stress queries had relative L2 about `0.0525`; this does not change the independent performance rejection. FA3 used 168 registers and no reported local-memory allocation for the primary direct-E5M2 kernel; raw resource usage is in `artifacts/build/resource-usage.txt`.

Interpretation: direct E5M2 execution is supported and numerically close at the bound production fixture, but splitting every circular row into two FA3 launches plus LSE merge overwhelms the FA3 decomposition benefit. The whole-request bound is non-positive, so the c32 endpoint was not invoked. Spend was `$1.22215505`; the healthy `0.6556567115001144 s/request` ring server was released ready.
