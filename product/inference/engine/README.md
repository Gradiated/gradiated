# Gradiated native inference engine

This directory owns the native C++/CUDA inference path. The first target is the pinned
`google/gemma-4-31B-it` release on one NVIDIA H200. The public runtime contract will remain
OpenAI-compatible so the gateway and Desmond do not depend on the execution backend.

The engine is split into independently testable layers:

- `gradiated_engine_model`: strict JSON, Gemma 4 configuration, sharded safetensors metadata,
  tensor-shape and parameter-count validation. It builds without CUDA and never maps all 62 GB
  just to inspect a release.
- `gradiated_engine_cuda`: H200 (`sm_90`) BF16 kernels and CUDA/cuBLASLt execution primitives.
- `gradiated-engine-inspect`: release validation and memory-planning CLI.

The CUDA build pins NVIDIA's header-only cuDNN frontend to commit
`b372d39879d44c91a8d5b342022e74802b6a8da2` (v1.17.0) and links the cuDNN 9 graph runtime from the
node image. This makes the fused sliding-prefill graph reproducible while leaving engine-owned
scheduling, cache layout, global D=512 attention, decode, and sampling in this tree.

The execution roadmap is weight loading, parity-tested single-request forward, hybrid paged KV
cache, continuous batching and prefix reuse, then overlapped frozen-KV speculative decoding. Each
optimization is retained only when it improves sustained cheapest-price compute recovery while
meeting TTFT, TPOT and output-parity gates on the held-out agentic trace workload.

The native release uses tensor-scaled E4M3 projections for decode and for cached suffix cohorts
whose packed row count does not exceed 4,096. Full cache-miss prefill remains BF16. The scheduler
prefers a queued continuation with a longer resident prefix, but any FIFO head can be bypassed at
most four times. These controls are exposed as `GRADIATED_FP8_SUFFIX_MAX_TOKENS` and
`GRADIATED_CACHE_AFFINITY_MAX_BYPASSES`; zero disables either optimization. The
`GRADIATED_IGNORE_MODEL_EOS` switch exists only to make performance A/B work counts deterministic
and must remain unset in production.

Active and idle cache-miss prefill use 1,024-token quanta by default. This is the retained point
from the stationary session-live frontier: smaller quanta reread the model weights too often,
while 2,048-token quanta improve cold-start TTFT but regress continuation TPOT tails. Operators can
override the active and idle values independently with `GRADIATED_PREFILL_QUANTUM_TOKENS` and
`GRADIATED_IDLE_PREFILL_QUANTUM_TOKENS` for explicit experiments.

`GRADIATED_FP8_WEIGHT_SCALE_MULTIPLIER` optionally applies startup-only clipping to tensor-FP8
weights; it must be in `(0, 1]`. The current research candidate is `0.98`, which is performance-
neutral on the stationary causal replay but remains gated on task-level and EOS quality. The
default is `1.0`, and production must not enable the candidate without explicit promotion.

`GRADIATED_FP8_GLOBAL_KV=1` is a research-only materialized E4M3 global-cache path. It uses the
same layer selection as `GRADIATED_FP8_GLOBAL_K_LAYERS`, stores V in a Hopper WGMMA-native layout,
and allocates its PV workspace lazily. It is retained to make cache-format experiments
reproducible, but fixed-scale E4M3 K fails the completion-quality gate and the complete path did
not improve matched session-live economics. Production must leave it unset.

`GRADIATED_FP8_COOPERATIVE_MAX_ELEMENTS` controls the largest activation tensor quantized by the
cooperative two-pass CUDA kernel. It defaults to 2,097,152 elements; the former 1,048,576-element
boundary remains available for matched A/B work. Values must be positive.

`tools/generate_layer_fixture.py` creates deterministic BF16 reference fixtures for one pinned
decoder layer without loading the full model. Fixture binaries are runtime artifacts; their
manifest and hashes establish exactly which model, layer, seed and shape a CUDA parity run used.
