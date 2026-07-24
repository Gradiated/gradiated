# Gemma 4 L40S QServe-style W4A8 MLP component

## Question

Can a QServe-style progressive W4A8 representation and fused consumer make the
exact Gemma 4 31B decode MLP faster than the actual online-FP8 consumer on
L40S, without the register and shared-memory collapse measured in Marlin?

## Why this matters

The active DFlash endpoint is the direct GPU priority, but it is still staging
its exact models. Homogeneous H200 prefill/decode disaggregation is now closed:
none of 1,980 calibrated scenarios reached the required 20% cost reduction.

L40S has a much lower committed planning rate (`$1.10/GPU-hour`) than H200
(`$3.25/GPU-hour`), and its 48 GiB capacity makes low-bit execution a placement
mechanism rather than only a kernel optimization. The prior group-128 AWQ
Marlin result does not settle this question. It reduced stored weight bytes by
48.05%, but used 200 registers/thread and 233,472 bytes of shared memory per
block, allowed one wave per SM, and made the M=32 MLP chain 8.51% slower than
FP8. QServe's progressive quantization, compute-aware reordering, and fused
dequantization are a materially different dataflow aimed at exactly that
failure.

Use `$kernel-research`. Consume `DIRECTOR_BINDING.json`; do not reopen, tune, or
replay the Marlin implementation.

## First mechanism result

Before any provider request:

1. Pin one current QServe/OmniServe source revision and identify the precise
   W4A8 producer, packed layout, activation-quantization, fused-dequant, and GEMM
   consumer path that can cover SM89.
2. Map the exact Gemma decode geometry:
   `gate_up_proj [M,5376] x [5376,43008]`, `GeluAndMul`, and
   `down_proj [M,21504] x [21504,5376]` for
   `M in {1,2,4,8,12,16,24,32}`.
3. Explain a concrete causal chain from the Marlin counters to one fixed
   candidate schedule. The candidate must avoid materializing dequantized
   weights or activations through HBM and predict changes in registers,
   shared memory, grid waves, and DRAM/L2 traffic.
4. Implement a project-local checkpoint-free exact-consumer harness with a
   dequantized-W4 oracle and the actual online-FP8 baseline. Bind every source,
   layout, dtype, scale, shape, launch, and expected symbol.
5. Emit `PROVIDER_REQUEST.json` only when the harness and immutable manifest are
   ready for one L40S compile/correctness/timing run. The director will create
   and register the bench on a later turn; the researcher must not create or
   claim a provider resource now.

Do not prepare multiple kernels, formats, group sizes, or tile sweeps. If the
selected upstream path cannot cover SM89 without changing the scientific
mechanism, return a typed source-support reject with the shortest distinct
implementation path.

## Paid component after director provisioning

Run one matched actual-consumer component on a single L40S:

- prove the packed W4 producer and W4A8 candidate reach the exact downstream
  gate/up, activation, and down consumers;
- compare complete outputs against the dequantized-W4 reference with finite
  outputs, relative L2, cosine, saturation, and exact shape/cardinality
  evidence;
- measure warm latency distributions at every bound M and call-weight the
  result for the c32 decode MLP;
- collect only the counters needed to test the predicted register,
  shared-memory, grid-wave, DRAM/L2, and tensor-pipe changes;
- retain any correct positive component result and request one real-weight
  coherence/endpoint continuation when its price-normalized whole-request bound
  is credible. Do not impose an arbitrary percentage threshold.

A slower or incorrect exact component closes this fixed QServe-style schedule.
It does not authorize a Marlin replay or a representation sweep.

## Resources and limits

- Profile: `deep` until the causal source/geometry/SM89 binding is complete;
  switch to `execution` for the routine paid component.
- Spend authority: at most `$12`, reserved for the later director-provisioned
  L40S only.
- Offline compute: at most 8 local CPU-hours.
- Paid compute: at most 6 L40S GPU-hours after provisioning.
- Wall clock: at most 10 hours from researcher start.
- Storage: at most 20 GiB project-local and one later 150-GiB provider disk.
- Provider lifecycle is director-owned.
- Do not inspect, wait for, restart, or modify DFlash or its H200.
