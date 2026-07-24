# Gemma 4 L40S QServe-style KV4 attention component

## Question

Can one QServe-style progressive KV4 producer and fused attention consumer
reduce the exact Gemma 4 hybrid-attention cost on L40S enough to complement the
W4A8 MLP route, without repeating the slow and inaccurate group-64 INT4 paged
consumer already rejected on H200?

## Evidence and distinction

Read
`../../evidence/HIGH_IMPACT_INFERENCE_LITERATURE_REVIEW_2026-07-24.md`
(SHA-256 `a182503e20eecfec49d200267d377632b65be9d1b059ea45523ae5ba682a02e6`)
and use `$kernel-research`.

QServe's reported W4A8KV4 result combines progressive quantization,
SmoothAttention, compute-aware layout, and fused consumption. That is
materially different from the closed H200 group-64 signed-INT4 path, which
reduced local stage-1 DRAM sectors by 46.90% but measured `2.330816 ms` versus
`0.276512 ms`, relative L2 `0.107507`, and cosine `0.994270`. Bind that terminal
at
`../gemma4_h200_local_kv_int4_endpoint/artifacts/local-int4-component-20260723t1337z/repair1/retrieved/COMPONENT_TERMINAL.json`
(SHA-256 `95810c1f3cf278ce3902265f5659cc5c4ea1967649d3b065958289ab385b864c`);
do not port, tune, or replay its pack/dequant/attention realization.

The independent L40S residual bound is
`../l40s_fp8_attention_kv_residual_floor/ATTENTION_KV_RESIDUAL_FLOOR.json`
(SHA-256 `f38704b6ae0e47e389643062c239a492d430079bf80754d8819f9a36b79aef08`).
It is analytical context only, not achieved latency.

## Offline decision packet

This turn has no GPU or spend authority. Produce one source-bound packet:

1. Pin the precise QServe/OmniServe KV4 producer, scale/SmoothAttention
   convention, packed layout, and fused attention consumer that could execute
   on SM89. One bounded source-support check is enough.
2. Derive the exact pinned Gemma geometry from model/runtime bindings: 50 local
   and 10 global layers, the 1,024-token local window, query/KV heads and head
   dimension, block table, prefix/cache ownership, decode M values, and the
   campaign's 4,214/358 c32 context progression. Do not guess a Llama geometry.
3. Choose exactly one KV4 representation and one fixed SM89 schedule. Explain
   how progressive quantization and fused consumption avoid the closed path's
   separate pack/dequant traffic and why the expected grid, registers, shared
   memory, L2/DRAM bytes, and tensor-pipe activity are plausible on L40S.
4. Implement a checkpoint-free actual-consumer harness with a dequantized-KV4
   oracle and the pinned BF16/FP8-KV control semantics. It must test local and
   global transitions, first extend-to-decode ownership, padded rows, positions,
   and complete attention outputs; synthetic bytes alone are not a packet.
5. Freeze source, build, geometry, producer, consumer, oracle, thresholds,
   symbols, and hashes in `KV4_ATTENTION_GPU_INPUT_MANIFEST.json`. Return either
   `packet_ready` or one typed source/geometry incompatibility.

Do not claim `l40s-qserve-e00a74kcbps8v00fk4`. The priority-6100 BF16-epilogue
MLP project owns the next use of that bench. Even a ready packet remains offline
until that project releases and a later director decision admits paid
execution. Do not create a provider request that implies automatic allocation,
download the checkpoint, alter the MLP project, or broaden into a full endpoint
or quality run.

## Later paid gate

A later director may admit one checkpoint-free L40S correctness/timing run only
if the immutable packet exists. That run must first prove transition semantics
and useful numerical quality, then compare complete local/global attention
outputs and producer-plus-consumer time against the actual control. A positive
component may be stacked with the MLP placement; a negative component closes
the fixed KV4 mechanism without a representation or schedule sweep.

## Limits

- Profile: `deep`.
- Wall clock: 2 hours.
- Compute: 4 local CPU-hours.
- Storage: 2 GiB project-local plus 2 GiB temporary.
- Spend: `$0`.
- Provider operations, GPU claims, checkpoint downloads, and DFlash/H200 work
  are prohibited.
