# Activation-aware AWQ weights on the fixed QServe SM89 MLP path

## Question

Can the already-measured fixed QServe progressive W4A8 SM89 dataflow consume
the exact activation-aware group-128 AWQ Gemma MLP tensors without changing
their semantics, preserving coherence while retaining a credible path to an
L40S c32 endpoint at or below `1.8853265455 s/request`?

## Why this is distinct and decision-relevant

The exact AWQ MLP tensors passed their real-weight dequantized correctness
oracle, but Marlin was 8.51% slower than online FP8 because it compiled at 200
registers/thread, 233,472 shared-memory bytes/block, and one wave/SM. The
fixed QServe SM89 schedule removed that resource collapse and measured
1.87–1.92x faster than online FP8, but its endpoint used newly reconstructed
uncalibrated W4 tensors and collapsed from layer 0. Those results leave one
specific interaction unmeasured: calibrated AWQ semantics on the faster
QServe dataflow.

## Scope

Use `$kernel-research`. Consume `AWQ_QSERVE_BINDING.json` and mechanically map
the existing AWQ `qweight`, `qzeros`, and `scales` into the fixed QServe
compute-aware layout without recalibration or requantization. First prove an
exact unpack/dequantize round trip for the layer-0 gate, up, and down tensors,
then freeze one converter, one source manifest, and one immutable GPU packet.

This cycle is offline only and must not touch the claimed L40S. A later
director may admit the paid packet behind
`gemma4_l40s_qserve_kv4_attention_component`. Its first GPU evidence must be
one exact layer-0 AWQ-dequantized/QServe/FP8 chain with the existing boundary
rows. Only a correct component may run three new coherence prompts, and only
three coherent outputs may trigger one matched c32 control/candidate pair.

## Decision gates

- Reject on any AWQ semantic mismatch introduced by the converter, nonfinite
  boundary, or failure to execute the fixed QServe kernels.
- Do not infer model quality from equality to the AWQ dequantized oracle.
- A later c32 candidate must complete all rows with exact prompt/cache
  accounting and `<=1.8853265455 s/request`; broader quality would remain a
  separate promotion decision.
- Run no calibration, representation, group-size, bit-width, schedule, tile,
  or mixed-precision sweep.

## Limits

- Profile: `deep`.
- Wall clock: 4 hours for the offline binding and immutable packet.
- Compute: 6 local CPU-hours; no GPU in this cycle.
- Storage: 3 GiB new project-local data; reference the 10.8-GiB AWQ MLP
  checkpoint read-only and do not duplicate it.
- Spend: `$0`.
- Provider operations, GPU claims, endpoint execution, and mutation of the
  active KV4 project are prohibited.
