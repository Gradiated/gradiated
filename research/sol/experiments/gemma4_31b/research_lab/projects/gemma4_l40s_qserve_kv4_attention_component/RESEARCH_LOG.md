# Research log

## 2026-07-24 — director admission

- Decision: open one `$0` offline QServe-style KV4 attention packet as a
  mechanism independent of the active W4A8 MLP epilogue continuation.
- Evidence boundary: the closed group-64 H200 path reduced DRAM sectors but was
  8.43x slower and numerically outside its gates. QServe's progressive
  quantization, SmoothAttention convention, and fused consumer are a different
  dataflow, not permission to tune the closed implementation.
- Next: bind one exact SM89 producer/consumer and pinned Gemma hybrid geometry,
  then emit a content-addressed actual-consumer packet or typed incompatibility.
  No GPU claim, checkpoint download, provider operation, or MLP interaction is
  authorized.

## 2026-07-24 — pinned OmniServe source/geometry reject

- Question: can OmniServe revision `02b2925aa6fa3b92b06316a1524b7f38922cd9c8`
  provide one exact SM89 progressive-ZINT4 producer and fused decoder for both
  Gemma attention types?
- Action: bound its packed per-token/per-KV-head affine producer, paged pointer
  layout, fused decoder, SM89 build target, and fixed 256-thread
  preload/multiblock dispatch; independently derived the SGLang-transformed
  Gemma geometry and c32 transition contract. Added a source/config hash
  verifier.
- Evidence: exact Gemma uses 50 local layers at Q32/KV16/D256 and 10 global
  layers at Q32/KV4/D512. OmniServe's decoder dispatch has one active case,
  D128, then `default: assert(false)`; its producer handles at most D256 and
  prints an unsupported-head terminal above it. The verifier passes against
  the exact commit and config.
- Interpretation: this is a typed source/geometry incompatibility, not missing
  harness wiring. A checkpoint-free actual-consumer packet cannot truthfully
  bind these upstream symbols without designing new D256/D512 decoder
  instantiations and a D512 producer.
- Result: `KV4_ATTENTION_SOURCE_GEOMETRY_REJECT.json` SHA-256
  `c9580f8f4d6f87ed1414becda414ae199700e155160df5c09c713520403ca814`.
  No GPU claim, CUDA invocation, provider mutation, checkpoint download, or
  spend occurred; the candidate arm remains unconsumed.

## 2026-07-24 — director replaces upstream dispatch with exact Gemma kernels

- Decision: preserve the OmniServe D128/source reject and reactivate the same
  scientific project under `EXACT_GEMMA_KV4_CONTINUATION.json`.
- Intervention: one source-bound SM89 progressive-KV4 producer and fused
  attention consumer for exact D256 local and D512 global geometry, with the
  already-bound per-token/per-head affine representation and no full
  dequantized-cache materialization.
- Execution order: prepare offline behind priority-6200, then claim the retained
  L40S only after the QServe MLP discriminator releases it.
- Limits: `$8`, 1.5 L40S GPU-hours, through `08:15Z`; one fixed schedule, one
  correctness/timing component, minimum causal counters, no endpoint or sweep.

## 2026-07-24 — exact packet frozen; durable owner queued

- Implemented only the admitted Gemma paths: D256/Q32/KV16 local and
  D512/Q32/KV4 global. The progressive producer writes unsigned affine packed
  nibbles plus independent FP16 K/V scale and zero for each token/KV head; the
  grouped split-KV consumer dequantizes directly in QK and P@V operands.
- Fixed schedule: 32-token KV blocks, geometry-exact head blocks (2 local,
  8 global), eight splits, four stage-1 warps/two stages, and eight producer
  warps. The actual FP8-E5M2 control is the hash-pinned installed SGLang v0.5.13
  grouped decoder with the same physical slot table and progressive append.
- The checkpoint-free packet executes all admitted M values, negative-slot
  no-op, padded zero rows, disjoint physical ownership, complete-output
  dequantized-cache oracles, and an actual local ring overwrite at logical
  position 1,024 (`2..1024,1` physical order). Production timing is fixed at
  local context 1,024 and global context 4,214 with 10 warmups/50 alternating
  samples and 50:10 layer weighting.
- Offline validation passed. Manifest
  `KV4_ATTENTION_GPU_INPUT_MANIFEST.json` is
  `ceba9153fb5b472b16e048e18d79a17db67017c804dec354dd7044073fea40fd`;
  immutable packet `KV4_GPU_PACKET.tar.gz` is
  `5a99a16532ee0fd984b292009ab3802f7bd815d789d487cf52b4b0d90257c769`.
- Priority-6200 was still active and the exact L40S remained in maintenance.
  Started `gemma4-kv4-l40s-20260724t0550z.service` as the bounded owner. It is
  only queue-waiting: no pool claim, guest access, CUDA invocation, or spend
  occurred. It may claim only after the predecessor is non-active and the pool
  exposes this exact bench as available.

## 2026-07-24 — terminal pre-science compilation boundary

- Question: did the one admitted immutable L40S packet produce its required
  correctness/timing component evidence?
- Action/evidence: the existing owner claimed `l40s-qserve-e00a74kcbps8v00fk4`
  at `07:00:03Z`, transferred the bound packet, and retrieved the compact
  evidence before release. Its first transition-suite producer compile failed
  in `_pack_affine_kv4`: Triton rejects tensor indexing `k[even]`/`v[even]`
  outside pointer arithmetic (`ERROR_TERMINAL.json`). `INVOCATION_STATE.json`
  records no completed producer and no scientific terminal; no complete-output
  row, timing sample, or counter packet exists.
- Interpretation: this is an ordinary pre-kernel Triton integration defect, not
  numerical evidence for or against KV4. The owner marked its pre-call intent
  as scientific and released the bench anyway, so the required same-claim
  repair route was unavailable after the `08:15Z` deadline. Do not alter or
  replay the frozen packet without a new director admission.
- Cost/cleanup: `COST.json` records 28.060699 seconds of L40S claim exposure
  at `$0.8629833/hour`, or `$0.006726643004733981` cumulative project spend.
  The compact diagnostic archive and raw stdout/stderr are retained under
  `artifacts/kv4-l40s-20260724t0550z/`; the bench was released and is no longer
  owned by this project.
