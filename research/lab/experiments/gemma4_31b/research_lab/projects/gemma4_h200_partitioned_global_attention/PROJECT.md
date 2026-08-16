# Partitioned global-attention realization on H200

## Question

Can the exact Gemma 4 global extend-attention kernel trade recomputation or L2 traffic for a smaller live value accumulator, higher SM residency, and a material reduction in the retained FP8+QKV endpoint time?

## Why this is the strongest kernel hypothesis

The exact v0.5.13 profile attributes `2.956183111 s` across 610 launches to the ten global layers. NCU measured 255 registers/thread, one CTA/SM, 12.4965% achieved warp occupancy, 10.1004% tensor activity, only 2.2142% DRAM activity, and 36.9558% L2 activity. That is a register-residency problem with room to trade extra score work or cache traffic for parallelism. The rejected BLOCK_M 32-to-16 edit changed tile geometry without reducing the fundamental live value state and regressed the endpoint; do not replay it.

## Scope and immediate experiment

Use the exact model/runtime/workload identities from `../gemma4_h200_v0513_fp8_qkv_residual_profile/BINDINGS.json` and retain its dynamic FP8, QKV epilogue, and deferred local-KV commit in both endpoint arms. Inspect the pinned Triton kernel and design the smallest numerically valid realization that reduces live V accumulation—for example head-dimension slicing, split-V CTAs with a compact merge, or score recomputation—while preserving the model and paged-cache semantics. Use judgment rather than a parameter sweep.

First compile and measure the exact global shape on H200 with a numerical oracle and just enough counters to prove the intended register/residency change. If the component result is promising, continue immediately in the same retained session to one contemporaneous 32-request control/candidate endpoint pair. Repair ordinary compile or integration defects in place. Do not stop at source review, simulation, or profiling when a CUDA falsifier is available.

Record component latency, registers/thread, achieved occupancy, tensor/L2/DRAM activity, candidate-path proof, full endpoint service seconds/request, exact token/cache accounting, output sanity, useful GPU time, and spend. A stable simple improvement is retainable even if it does not alone close the `0.6381105231 s/request` ceiling.

## Continuation after the forced-register result

The measured `maxnreg=128` result proves that spilling one unchanged monolithic kernel is the wrong trade: it doubled theoretical CTA residency but raised L2/DRAM traffic and regressed latency 77.31%. Continue with a genuinely partitioned algorithm that ends the live range between kernels or CTAs—such as QK/softmax followed by sliced V accumulation with compact intermediate state—rather than another register cap or tile sweep. The next result must measure one exact multi-stage implementation and its temporary-memory/recomputation cost on H200. The project remains open until that distinct dataflow is measured.

That required continuation is now measured and rejected. The exact-shape grouped-QK/causal-softmax plus four-way width-128 sliced-V candidate was 5.10% slower than control, failed the numerical oracle because its component path omitted the baseline softmax scale, and materialized 1.376 GB. Its endpoint gate therefore remained closed. This project is complete; no replay, profiler-only retry, register cap, or tile sweep is admitted.

## Resources

- Reuse a director-registered H200 bench; researchers must not create or destroy it.
- Up to 180 H200 claim minutes and `$10.00` total authorized spend.
- Keep the bench warm and release it to the pool after the result.
- Broad quality evaluation, model-geometry changes, backend flag sweeps, and the old BLOCK_M=16 candidate are out of scope.
