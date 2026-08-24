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

Tensor-FP8 QKV, O, gate/up, and down inputs carry maxima from their producer kernels so conversion
does not reread the activation or use a cooperative grid barrier. O-input and down-input carry
activate at 16 rows, the retained live-traffic crossover; smaller cohorts retain the conventional
converter. The O path folds block maxima into the required head-to-token transpose and has each
conversion CTA derive the unchanged tensor scale directly from that compact metadata vector.
`GRADIATED_DISABLE_QKV_NORM_CARRIED_AMAX`,
`GRADIATED_DISABLE_O_TRANSPOSE_CARRIED_AMAX`,
`GRADIATED_DISABLE_GATE_UP_NORM_CARRIED_AMAX`, and
`GRADIATED_DISABLE_GELU_CARRIED_AMAX` provide independent rollback controls.

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

`GRADIATED_INT8_GLOBAL_KV_ORACLE=1` is a quality oracle for the next cache representation. It
round-trips selected global K/V vectors through symmetric INT8 and then runs the unchanged BF16
attention, so it intentionally saves no memory or time. `GRADIATED_INT8_GLOBAL_KV_ORACLE_MODE`
selects `keys`, `values`, or `both`; `GRADIATED_INT8_GLOBAL_KV_ORACLE_BLOCK` selects 64, 128, 256,
or 512 components per dynamic scale; and `GRADIATED_INT8_GLOBAL_KV_ORACLE_LAYERS` optionally lists
global layer indices. The oracle cannot be combined with the FP8 global-cache experiment and must
remain unset in production.

`GRADIATED_INT8_GLOBAL_K=1` materializes block-128 signed-INT8 keys and four FP32 scales for each
global-attention cache row. `GRADIATED_INT8_GLOBAL_K_LAYERS` optionally restricts the physical
cache to selected global layer indices. `GRADIATED_INT8_GLOBAL_KV=1` additionally materializes the
experimental signed-INT8 V layout. These are research paths, not production defaults: all-layer K
and every tested physical V format failed completion-quality gates, while the quality-safe K subset
`5,29,59` failed to improve matched session-live latency or economics. Leave both switches unset in
production.

`GRADIATED_INT4_LM_HEAD=1` enables the research W4A8 target LM head. It quantizes the retained
tensor-E4M3 embedding into group-256 signed INT4 with group-major E4M3 lookup scales and executes
the complete 262,144-column head as one Hopper mixed-input CUTLASS GEMM. The physical kernel passes
the CUDA oracle and HumanEval task gate, and reduces a fixed B16 verifier by about 1%, but it did
not improve matched session-live SLO economics. It also keeps the FP8 embedding resident alongside
the mixed-input representation. Production must leave it unset. `GRADIATED_INT4_LM_HEAD_SEGMENT`
exists for explicit kernel experiments; its default is the complete 262,144-column vocabulary.
`GRADIATED_INT4_BF16_LM_HEAD` is the corresponding W4A16 research control and is also never a
production default.

`GRADIATED_FP8_COOPERATIVE_MAX_ELEMENTS` controls the largest activation tensor quantized by the
cooperative two-pass CUDA kernel. It defaults to 2,097,152 elements; the former 1,048,576-element
boundary remains available for matched A/B work. Values must be positive.

FP8 projection plans use a retained Hopper cuBLASLt heuristic policy for the pinned runtime image.
The policy is keyed by the exact Gemma projection dimensions and packed row count; every unmeasured
shape keeps cuBLASLt's first recommendation. `GRADIATED_DISABLE_FP8_HEURISTIC_POLICY` restores that
first-choice control. `GRADIATED_FP8_HEURISTIC_INDEX` forces one ordered heuristic result in
`[0, 63]` and exists only for isolated algorithm enumeration; production must leave it unset. The
retained table is fail-closed if a selected result disappears and must be requalified whenever the
CUDA/cuBLASLt image changes.

`tools/generate_layer_fixture.py` creates deterministic BF16 reference fixtures for one pinned
decoder layer without loading the full model. Fixture binaries are runtime artifacts; their
manifest and hashes establish exactly which model, layer, seed and shape a CUDA parity run used.
