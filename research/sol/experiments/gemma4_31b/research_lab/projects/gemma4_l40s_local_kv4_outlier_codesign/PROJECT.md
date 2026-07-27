# Gemma 4 L40S local-KV4 outlier-sidecar co-design

## Question

Can one fixed local-only KV representation—group-64 signed KV4 plus a sparse
E5M2 residual sidecar—make the exact c32 Gemma 4 endpoint resident on a
single L40S and reduce the complete D256 local-attention producer/consumer
boundary, while preserving all ten global layers in the qualified E5M2 path?

## Why it matters

The current-official single-L40S dynamic-FP8/E5M2 rebase is structurally
infeasible before execution. Its candidate-favorable lower bound is
`50,949,152,768` resident bytes (`47.450096 GiB`) against only
`48,305,799,168` exposed bytes (`44.988281 GiB`). The exact local E5M2 K/V
pool alone owns `13,421,772,800` bytes.

For each 256-element local K or V vector, this project fixes one representation:

- 128 bytes of signed packed INT4 values;
- four BF16 group-64 scales, 8 bytes total; and
- four deterministic largest-residual entries, each stored as one uint8
  channel index plus one E5M2 residual byte, 8 bytes total.

The fixed 144-byte representation is 56.25% of the E5M2 vector size. Applied
only to the exact local pool, it saves `5,872,025,600` bytes and changes the
optimistic residency lower bound to `45,077,127,168` bytes, leaving
`3.006935 GiB` before omitted runtime terms. Complete accounting may still
reject the placement; memory fit is a scientific gate, not an assumption.

This is materially distinct from both prior KV4 attempts:

- The H200 group-64 path used a separate pack/dequant/attention realization,
  had no outlier residual, measured `2.330816 ms` versus `0.276512 ms`, and
  failed its numerical gate (`0.107507` relative L2).
- The earlier L40S affine KV4 packet never produced science. Its producer
  stopped before completion on a pre-science Triton `constexpr` defect, and
  its expired packet must not be replayed.

The new hypothesis is that fused dequantization plus four residual corrections
inside the online-softmax value accumulation removes the old intermediate
traffic and recovers the dominant outlier error without sacrificing the
memory reduction needed for placement.

## Bound evidence and identities

- Current-runtime L40S memory terminal:
  `../gemma4_l40s_current_runtime_fp8_endpoint_rebase/L40S_CURRENT_RUNTIME_FP8_REBASE_OFFLINE_TERMINAL.json`,
  SHA-256
  `f7a7960ae8f07f22eea2eaa2e6e77d96692351c18542e471a6cf46e07bb076f5`.
- Reuse its selected official SGLang commit:
  `c6a6200a1a778a799ba61c395ac292317f01ebc9`.
- Closed H200 group-64 component:
  `../gemma4_h200_local_kv_int4_endpoint/artifacts/local-int4-component-20260723t1337z/repair1/retrieved/COMPONENT_TERMINAL.json`,
  SHA-256
  `95810c1f3cf278ce3902265f5659cc5c4ea1967649d3b065958289ab385b864c`.
- Pre-science L40S diagnostic:
  `../gemma4_l40s_qserve_kv4_attention_component/artifacts/kv4-l40s-resident-retrieve-20260724t0722z/resident-retrieved/ERROR_TERMINAL.json`.
- Exact model: `google/gemma-4-31B-it`, revision
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Exact workload: c32, 4,214 prompt tokens, 358 output tokens, 535 shared
  prefix tokens, 3,679 fresh tokens, 50 D256/window-1024 local layers, 10
  D512 global layers, TP1, page-size-one ownership.
- Target: NVIDIA L40S, SM89, measured exposed `46,068 MiB`.

Mechanically bind these inputs and their direct hashes. Do not transfer H200
timing or infer L40S performance from peak specifications.

## Scope

Use `$kernel-research`. Work for at most 90 wall-clock minutes, 4 local
CPU-hours, 3 GiB of new non-checkpoint artifacts, and `$0`. The completed
L40S endpoint project still owns the campaign's pending `$0.59` reservation;
this project may request no spend until a later director observes that
reservation released and a positive source-complete terminal.

Implement one current-runtime, checkpoint-free producer/reference/consumer:

1. Write the exact per-token, per-KV-head D256 local-cache producer with four
   symmetric group-64 scales, deterministic signed-INT4 packing, and the four
   largest residual entries selected by absolute residual with lowest-channel
   tie-breaking.
2. Consume the packed base and residual sidecar directly inside one paged
   local-attention online-softmax path. Do not materialize a full dequantized
   cache or output. Preserve running-max/sum/output rescaling, causal/window
   masks, GQA mapping, page-one slot ownership, negative-slot no-op behavior,
   graph padding, transition reuse, and request isolation.
3. Keep every global layer, global cache pool, full-attention consumer,
   transformer weight, logits, sampler, workload, and output contract
   unchanged at dynamic-FP8 plus E5M2.
4. Establish a high-precision oracle and a justified finite numerical
   envelope. Report max absolute error, relative L2, cosine, nonfinite and
   saturation counts, and error before versus after residual correction.
5. Derive compulsory bytes, pack/write/read bytes, arithmetic intensity,
   grid waves, expected registers/shared memory, and the exact counter
   movement. Charge producer, scales, sidecar, fused correction, padding,
   graph buffers, workspaces, allocator reserve, and all other resident
   terms in a complete single-L40S memory interval.

Cover the exact prefill/decode production layouts plus the smallest
discriminating transition, page-boundary, padded/no-op, zero, extreme, and
partial-window cases. The candidate must reach the unchanged complete
attention-output consumer. Synthetic encode/decode agreement alone is not a
result.

Return typed `none` if the fixed representation cannot fit after complete
accounting, cannot be consumed on SM89 through the real current-runtime path,
cannot plausibly beat the actual E5M2 producer-plus-consumer after all extra
work, or has no defensible numerical path materially better than the closed
no-sidecar group-64 realization.

Do not claim a GPU, use SSH/provider APIs, run CUDA or an endpoint, read/copy
checkpoint shards, change outlier count, group size, scale dtype, cache
precision for global layers, page size, workload, or attention geometry,
sweep schedules, port/replay the closed H200 kernel, or replay the expired
L40S packet.

## Terminal

Persist `L40S_LOCAL_KV4_OUTLIER_OFFLINE_TERMINAL.json` containing:

- exact source, model, workload, hardware, and predecessor hashes;
- producer, packed layout, scale, residual, page/slot, GQA, mask, graph, and
  downstream-consumer contracts;
- source-complete implementation and focused-test hashes;
- exact prefill/decode shapes and all boundary cases;
- base-only and residual-corrected numerical evidence or a precisely labeled
  unmeasured contract;
- compulsory bytes, physical model, predicted counters, complete memory fit,
  and conservative whole-request relevance;
- one lifecycle-pure later L40S component command that reaches the real
  consumer, or typed `none`; and
- explicit evidence labels, uncertainty, and falsification conditions.

A positive terminal may justify requesting the released campaign remainder
for one checkpoint-free L40S component invocation. It does not authorize
provider creation, claim, CUDA, endpoint, quality promotion, or production
deployment.
