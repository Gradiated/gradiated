# Research log

## 2026-07-25 — exact-shape output-channel-wide schedule

**Question.** Can the production Gemma 4 31B dynamic-FP8 MLP stream wider
contiguous output-channel regions per CUTLASS scheduler tile at exact M32 and
M384 without changing any consumer semantics?

**Action.** Bound `Gemma4MLP = Gemma3MLP`, `Fp8LinearMethod.apply`,
`apply_fp8_linear`, and the pinned SM90 dispatch by hash. Reused only
scope-matched stock evidence: the exact-width M32 full-chain timing and the
real-weight M384 gate/up and down timings. Implemented an M32
`Shape<128,32,256>, Cluster<1,1,1>, swap_ab` schedule and an M384
`Shape<128,256,128>, Cluster<2,1,1>` schedule. Both retain the stock K tile,
schedule family, scale epilogue, and M multicast. Added a deterministic
full-consumer runner and compiled the extension for SM90 in the pinned image
without a GPU.

**Evidence.**

- Measured: stock exact M32 full MLP median is 125.488 us. Stock exact M384
  gate/up and down medians are 230.640 us and 149.616 us.
- Analytical: modeled M32 intensity is 62.06 FLOP/byte and M384 is 324.03
  FLOP/byte, both below H200's 412.29 FP8 FLOP/byte ridge. The M32 FP8 weights
  are 346.8 MB versus 50 MiB L2.
- Derived: widening only N halves scheduled CTA work tiles at both shapes.
  Dominant weight bytes and the five-kernel MLP launch structure do not change.
- Build-measured: both kernels compile. Dynamic shared storage is 205,824
  bytes at M32 and 214,528 bytes at M384, below H200's 232,448-byte block
  limit. The immutable module SHA-256 is
  `4664d3a6c0ff32bb845bd4d766a549398ecd653191ad1f2f7bfb3da77233b43c`.
- Derived: the measured M384 projections alone occupy at least 1.7107% of the
  qualified c32 batch service window. Each measured M384 microsecond saved
  maps to at least 0.004499 whole-request percentage points before counting
  M32 decode.
- Invalid attempt: the first offline compile used an invalid C++ alias for a
  class-template argument. No CUDA invocation or scientific sample began. The
  alias was corrected and only compilation was retried.

**Interpretation.** The source realization is buildable and physically
distinct from the rejected static-scale, width-16,384, and cluster-orientation
arms. It has a positive service-time mapping but no measured candidate timing.
The causal test is sharp: scheduler tiles must halve while DRAM bytes remain
approximately unchanged; full-chain time must improve at both M32 and M384
with bitwise consumer equality.

**Next.** Stop at `source_complete_candidate`. After the current owner releases
the H200, one director-authorized component-only run may consume the immutable
module with `exact_shape_runner.py`. Admit the result only if every persisted
boundary is finite and bitwise equal and the paired-bootstrap 95% lower bound
on saved time is positive at both row geometries. This project does not
authorize an endpoint.
