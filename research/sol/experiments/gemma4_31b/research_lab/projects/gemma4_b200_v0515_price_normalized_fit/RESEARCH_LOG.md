# Research log

## 2026-07-25 — official SM100 fit/support passes; bound-arrival economics close

**Question.** Can the exact official v0.5.15 dynamic-FP8, E5M2 page-1 KV,
depth-12 NGRAM stack fit and sustainably cross `$0.14/M` on one B200 without
changing the bound workload?

**Action.** Mechanically verified all eight `DIRECTOR_BINDING.json` files and
the candidate's complete internal manifest. Retrieved and hash-bound the
official v0.5.15 SM100 loader/build, dynamic-FP8 producer/dispatcher/CUTLASS
kernel, E5M2 KV, Gemma, and Triton attention sources. Derived conservative
B200 capacity and exact raw/sustainable economics from the immutable request
rows.

**Evidence.** Official source builds and loads the SM100 `sgl-kernel` variant,
recognizes CC 10.0 with CUDA >=12.8, online-quantizes BF16 weights, and
dispatches `fp8_scaled_mm` to a native SM100 CUTLASS kernel. Depth-12 c32
target verification has `M=384` and selects its `M>256` 256x128x64,
2x2-cluster path. The E5M2 KV dtype, 50-local/10-global Gemma dispatch,
Triton target-verify consumer, and NGRAM graph capture are all present.

Conservative 180-decimal-GB fit leaves `109.182354 GiB` for the 0.8-ratio KV
pools: at least `318,016` full and `254,412` sliding tokens versus c32 needs
`146,688/33,152`, with `23.715710 GiB` post-graph headroom. These are
source-backed/analytical results; no B200 throughput is claimed.

At `$5.15/GPU-hour`, the exact 3,616,452-token endpoint permits
`353.920739417 s` / `0.4474345631 s/request` raw and `318.528665476 s` /
`0.4026911068 s/request` at 90% sustainable utilization. But the hash-bound
last request is released at `548.741989506 s`. Even zero response latency
therefore floors cost at `$0.217065207/M` raw and `$0.241183563/M`
sustainable. The post-calibration 759-row view has the same contradiction.

**Interpretation.** `typed_none`:
`bound_arrival_floor_exceeds_price_normalized_hurdle`. Support and fit pass,
but an unchanged endpoint cannot pass economics on any B200 speed. A packet
would need to compress/multiplex demand by at least `1.722739737x` for the
sustainable gate, which changes the bound arrival workload and is not
authorized.

**Next.** Reopen only with a binding that explicitly permits the faster demand
geometry, a matching committed B200 rate at or below `$2.989424281/hour`, or a
changed target/workload contract. Artifacts: `B200_SUPPORT_FIT.json` and
`TYPED_NONE.json`; no GPU, provider mutation, model bytes, or spend.
