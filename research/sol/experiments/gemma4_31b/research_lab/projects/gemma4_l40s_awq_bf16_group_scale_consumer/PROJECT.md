# Exact AWQ BF16-group-scale consumer on L40S

## Question

Can one fixed SM89 W4A8 consumer preserve the existing activation-aware AWQ
weights exactly by scaling each K-group tensor-core partial with its original
BF16 group scale, while retaining enough of QServe's measured resource and
weight-traffic advantage to improve the actual L40S endpoint?

## Evidence and mechanism

The fixed QServe representation is closed before CUDA: zero output channels
can factor the AWQ BF16 group scales into QServe's byte group multiplier and
signed-int8 stage-1 ranges. Approximation would be prohibited requantization.
The distinct consumer in `EXACT_CONSUMER_BINDING.json` instead accumulates one
K=128 int32 partial at a time, applies the original BF16 AWQ and per-token
activation scales, and adds it to an FP32 output accumulator.

This preserves the calibrated AWQ semantics and packed W4 bytes. It tests
whether serial group scaling can keep QServe-style packed staging while
avoiding the measured Marlin collapse at 200 registers/thread, 233,472 shared
bytes/block, and one wave/SM. The real downstream chain is gate/up,
GeluAndMul with dynamic int8 production, and down—not an isolated convenient
GEMM.

## Execution

Use `$kernel-research`. Implement exactly one fixed source path for the bound
SM89 shapes and freeze its source, reference, runner, and immutable packet.
Do not tune before CUDA. After priority-6300 KV4 releases and a director-owned
watchdog covers the run, claim the retained L40S, make the smallest discovery
call, and repair ordinary compile/API defects in that same claim.

Run complete-chain boundary correctness and the frozen `M=1..32` timing
packet profiler-off against the actual online-FP8 control. Collect only the
compiler/counter evidence needed to distinguish register/shared-memory
collapse, spills, tensor activity, and W4/scale traffic. A correct positive
component immediately runs three new coherence prompts; three coherent
outputs trigger one matched c32 pair with exact accounting and the
`1.8853265455 s/request` ceiling.

## Limits

- Profile: `deep`.
- Spend: `$8` cumulative project authority.
- Wall clock: 5 hours from first researcher start.
- Compute: 6 local CPU-hours and at most 1.5 L40S GPU-hours.
- Storage: 4 GiB new project artifacts; consume the existing AWQ checkpoint,
  pinned image, and compiled caches read-only without duplication.
- No calibration, requantization, clipping, scale approximation,
  representation/schedule sweep, provider mutation, or interference with the
  active KV4 owner.
