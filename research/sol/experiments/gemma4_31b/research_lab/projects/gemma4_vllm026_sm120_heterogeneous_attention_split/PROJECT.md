# vLLM 0.26 sm_120 heterogeneous-attention split

## Question

Can exact Gemma 4 layer-aware attention dispatch replace the current
whole-model `TRITON_ATTN` fallback with supported specialized local and global
consumers on sm_120, without changing attention or KV-cache semantics?

## Why this matters

The exact current-vLLM RTX PRO 6000 endpoint is materially faster than the
matched SGLang result but remains 22.79% above its price-normalized economic
ceiling. Measured vLLM startup forces every layer onto `TRITON_ATTN` solely
because Gemma 4 mixes `head_dim=256` local attention with
`global_head_dim=512`. Gemma 4 has fifty 1,024-token sliding layers and ten
global layers, so a layer-aware split could affect every forward pass and is
independent of the admitted norm-to-FP8 fusion.

## Bound evidence

- Model: `google/gemma-4-31B-it` at
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Runtime: official vLLM `0.26.0+cu129`, wheel SHA-256
  `6ce4ca30616f0a35810391015622b197a7b8b267ed27f8716f0789db79ff578b`,
  Torch `2.11.0+cu130`, sm_120.
- Measured boundary:
  `../gemma4_vllm026_sm120_norm_fp8_fusion/DIRECTOR_VLLM026_RUNTIME_BOUNDARY_EVIDENCE_20260729T0633Z.json`.
- Strongest baseline: exact vLLM `TRITON_ATTN` path at c32,
  4,214 prompt plus 358 output tokens per request.

## Scope

Use `$kernel-research`. Inspect only the vLLM 0.26.0 Gemma4 attention,
backend-selection, paged-KV, and candidate backend sources needed to bind the
actual local and global consumers. Derive exact Q/K/V layouts, KV ownership,
mask/window behavior, prefill/decode shapes, and backend support on sm_120.
Implement one production-bound layer-aware dispatcher or return typed none if
no official consumer can preserve both exact variants.

Do not claim a GPU, SSH, call provider APIs, alter the running norm-FP8
project, or propose a generic attention rewrite. Preserve exact model
semantics and bind the first correctness-bearing future consumer.

## Result that changes the portfolio

Persist `VLLM026_SM120_HETEROGENEOUS_ATTENTION_SPLIT_OFFLINE_RESULT.json`
within 60 minutes with final source hashes, a concrete patch or typed none,
an exact future sm_120 oracle/build/run command, and one predicted physical
change such as removed padding, reduced bytes, fewer launches, or lower
kernel time. A concrete candidate becomes a future component measurement only
after the norm-FP8 warm-bench itinerary resolves.

## 2026-07-29 execution preparation

The offline result is accepted as a concrete stock-runtime component candidate.
Prepare `run_sm120_attention_split_component_owner.py` under
`DIRECTOR_VLLM026_SM120_ATTENTION_SPLIT_COMPONENT_OWNER_PREPARATION_20260729T0740Z.json`.
This is execution-profile, zero-GPU work while the norm-FP8 project retains
the serial RTX bench.

The owner must remain inert until a later director binding. After a future
claim it must use the shared exact-bench claim session, stop only the
future-bound resident server generation, fence VRAM, and run the existing
control/candidate oracle once through the resident official vLLM runtime.
Preserve completed arm evidence across repair, use a fresh repair generation
for every incomplete attempt, and do not perform the c32 endpoint measurement
in this preparation.
