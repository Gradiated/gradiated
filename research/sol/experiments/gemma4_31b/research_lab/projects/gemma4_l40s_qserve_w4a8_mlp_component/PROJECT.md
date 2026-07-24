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

## 2026-07-24 continuation — BF16-safe progressive epilogue

The immutable FP16-output schedule above is closed and must not be replayed.
Its measured result nevertheless isolates one materially different numerical
mechanism: all eight production rows were finite and correct at 1.84–1.89x the
online-FP8 control, while only the positive-extreme row was nonfinite. The
candidate writes both the 43,008-wide gate/up intermediate and the 5,376-wide
down output through FP16 epilogues; the actual control preserves BF16 range.
This is evidence for a range failure at the progressive epilogue boundary, not
permission to clip, canonicalize, tune the schedule, or weaken the boundary.

Consume `BF16_EPILOGUE_CONTINUATION.json` and use `$kernel-research`. Implement
exactly one BF16-output variant of the existing group-128 W4A8 dataflow:

- retain the packed weights, INT8 activations, scale conventions, fixed
  `32x64x128`/four-warp/three-stage SM89 schedule, and complete-output
  consumption;
- make the gate/up and down GEMM epilogues BF16-range-safe and update only the
  adjacent activation-quant consumer required by that dtype contract;
- do not add FP16 saturation, clamping, fallback rows, format/group/tile
  choices, or a second candidate;
- run the three-row boundary discriminator first. Only a genuinely finite
  zero/positive-extreme/negative-extreme result may unlock one rerun of the
  eight production M rows;
- require the prior finite/correctness thresholds on every production row,
  candidate-path proof, and a positive warm component result against the same
  actual online-FP8 comparator. Report any extra conversion, launch, register,
  spill, shared-memory, or grid-wave cost introduced by BF16 output.

If and only if both discriminators pass, continue in this same project to one
real-checkpoint placement. Materialize a content-addressed group-128 W4 MLP
representation for the exact checkpoint while preserving the remaining model,
tokenizer, API, attention, head, and workload semantics. Run a cheap coherence
smoke and then one c32 endpoint: 32 requests, 4,214 prompt tokens, 358 output
tokens, and the campaign's cached/fresh accounting. Require 32/32 finite
completions, valid tool/text behavior, stable memory, no reloads, and complete
raw rows. At the committed planning rates, the price-normalized L40S ceiling is
`0.6381105231 * 3.25 / 1.10 = 1.8853265455 s/request`. A result at or below that
ceiling nominates the exact representation for GPQA-Diamond/TauBench; it does
not transfer quality from FP8 or authorize broad quality work here.

Reuse only `l40s-qserve-e00a74kcbps8v00fk4`, its 150-GiB disk, pinned image, and
compiled SM89 cache. Keep one claim through ordinary compile, staging, import,
or consumer repairs. If checkpoint packing or the conditional endpoint
outlives a researcher response, leave one bounded durable owner in this same
project. Do not create a resource, touch the retired DFlash lineage, replay
Marlin, or start checkpoint staging before the component gates pass.

## Resources and limits

- Profile: `deep` until the causal source/geometry/SM89 binding is complete;
  switch to `execution` for the routine paid component.
- Renewed continuation spend: at most `$14` on the existing L40S only.
- Offline compute: at most 8 local CPU-hours.
- Paid compute: at most 5 additional L40S GPU-hours.
- Wall clock: through `2026-07-24T08:15:00Z`; the existing cleanup watchdog
  remains authoritative at `2026-07-24T08:30:59.577420Z`.
- Storage: at most 20 GiB project-local and the existing 150-GiB provider disk.
- Provider lifecycle is director-owned.
- Do not inspect, wait for, restart, or modify DFlash or its H200.
