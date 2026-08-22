# Research log

## 2026-07-30 — exact pinned M384 offline falsifier

**Decision.** `typed_analytical_negative` for the three prescribed packed
decompositions. No GPU contract is promoted. No GPU was claimed, CUDA was not
invoked, provider state was not touched, and spend was `$0`.

**Pinned path.** SGLang v0.5.13 commit
`28b095c01005d4a3a2a5b637b7d028b07fba31b2` creates 32 request-major groups of
12 draft rows in `NGRAMWorker`, marks the batch `TARGET_VERIFY`, and consumes
it through `Gemma4Attention.forward` and the hybrid/Triton prefill
`extend_attention_fwd` path. The exact target launch is
`grid=(32,32,1)`, `block=(256,1,1)` for both local d256/window-1024 and global
d512 layers; page size is one and GQA maps
`kv_head = q_head // group_size`. The FP32 online-softmax output continues
through the tied LM head and unchanged `NgramVerifyInput.verify` acceptance
consumer. Exact symbols, hashes, padding behavior, layouts, and remaining
runtime unknowns are frozen in `artifacts/SOURCE_BINDING.json`.

**Measured calibration.** The retained exact repaired H200 trace contains 900
target `_fwd_kernel` launches: 60 layers across 15 verification steps. Every
launch has 1,024 CTAs, 255 registers/thread, and 81,920 bytes shared memory.
On 132 SMs at one CTA/SM this is eight waves with 32 empty final-wave slots,
only 3.03% tail waste. The summed attention-kernel time is 1.488205758 seconds
for the 32-request batch. A scope-adjacent exact-H200 negative control that
forced 128 registers/thread regressed from 2.425440 ms to 4.300480 ms
(+77.31%), consistent with spill traffic erasing occupancy gains.

**Deterministic falsifier.**

- Scheduling-only persistence retains 1,024 logical tasks, eight waves, the
  same resource limits, and all 60 layer-dependent launches.
- Legal global d512 split-V2 and split-V4 decompositions repeat QK/K/mask work,
  raising issued work and requested KV bytes to 1.5x and 2.5x respectively.
  They require at least 16 waves and have no exact-source evidence of crossing
  the resource threshold without spills.
- A legal score/probability producer plus four d128 consumers creates five
  ordered task families and materializes probability traffic. Page-size-one
  indexed KV gathers cannot use TMA as a contiguous gather shortcut. The
  closest exact-H200 staged evidence was 5.10% slower and materialized 1.376
  GB, so this route does not survive promotion.
- The pure-Python FP64 reference checks the exact page-one/GQA task mapping,
  four-way value slicing, and independent online-softmax state at d256 and
  d512. All checks pass; maximum split-V error is zero and maximum online
  merge error is below `1.8e-16`.

The measured 1.488205758-second attention sum is retained separately as batch
work and normalizes to 0.0465064299375 seconds per completed request. Applying
the measured 62.66% trace share to the fixed qualified denominator gives an
*inferred* attention upper bound of 0.391703118852 seconds/request, not a
measured endpoint delta.

**Invalid attempt and amendment.** The first local runner invocation exited
before producing a result because NumPy was not installed. This was an
ordinary dependency defect, not a sample. The runner was amended to use only
the Python standard library and then executed once to a complete,
interpretable terminal.

**Re-admission gate.** Reopen only for a materially different exact-source
SM90 decomposition that compiles at no more than 128 registers/thread with
zero spills and no more than 81,920 bytes shared memory, avoids materialized
probabilities and repeated QK/K page traffic, captures exact runtime
strides/storage offsets, and passes the same reference oracle.
