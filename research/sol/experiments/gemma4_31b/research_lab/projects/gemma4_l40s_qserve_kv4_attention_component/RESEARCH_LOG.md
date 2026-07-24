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
