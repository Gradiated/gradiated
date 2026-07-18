# Gemma 4 global-head-256 Hopper backend unlock

## Question

Would changing only Gemma 4's ten full-attention layers from a 512-wide attention head to a 256-wide head remove enough exact H200 work, while unlocking Hopper's fused TRTLLM/FlashInfer XQA path, to justify a later weight-surgery or distillation experiment?

This is an explicitly non-quality-preserving architecture proxy. It may nominate a model change for later quality recovery; it cannot establish a deployable checkpoint, output equivalence, or production economics.

## Why this is the next bottleneck

The canonical retained c32 endpoint is `0.9194573941250042` service seconds/request. The serving-flag frontier has now produced clean negatives for continuous decode steps, mixed chunking, Triton KV splits, stream interval, and max-prefill capacity. Exact tied-head timing is only `0.02028762177626292` seconds/request in BF16, so even deleting the entire 262,144-way vocabulary head cannot clear the campaign's 5% endpoint gate.

The exact model config instead exposes a hardware boundary: 50 sliding layers use head dimension 256, while 10 full-attention layers use head dimension 512. Pinned SGLang reached the actual TRTLLM MHA warmup and failed only because FlashInfer XQA accepts head dimensions in `[16, 256]`. The prior exact-shape discriminator also selected a fast fused kernel for local head-256 attention, whereas global head-512 native GQA fell back to a slow path. Halving the global head therefore changes both nominal Q/K/V/O and KV work and the realizable kernel family.

## Immediate experiment

Use warm bench `h200-attention-endpoint-e00vbbb709tzxscaan` at `$2.46/hour`, the resident pinned SGLang image, and its Hopper/FlashInfer/TRTLLM stack. Stop the currently loaded max-prefill server only after claiming the bench; preserve the resident checkpoint and image. Build and run one exact-shape component discriminator with:

- immutable workload geometry: c32, 4,214 prompt tokens, 358 output tokens, 12.7% cached prompt share, 32 query heads, 10 global layers, 50 local layers, and peak global context 4,571;
- frozen current geometry: hidden size 5,376, global head dimension 512, four global KV heads, BF16 projection weights/activations, and FP8-E5M2 paged KV;
- sole candidate geometry: global head dimension 256 with the same hidden size, 32 query heads, four global KV heads, and ten global layers; local layers remain unchanged;
- prompt and decode measurements for the affected Q/K/V projections, global attention, output projection, and KV traffic, including the actual page-64 TRTLLM/FlashInfer XQA path for the candidate rather than dense KV repetition;
- a current-geometry reference through the pinned supported Triton path, plus source/kernel identity, raw timings, GPU utilization/power/memory, and any profiler evidence needed to distinguish compute, bandwidth, launch, and unsupported-path effects.

Require finite deterministic outputs and a candidate-kernel numerical oracle against a straightforward head-256 reference. Do not compare candidate activations with the current 512-wide model: those semantics intentionally differ. Record all assumptions used to weight prompt/decode and ten affected layers into seconds per exact request.

Emit a typed `RESULT.json`. Nominate the model change only if the non-repeating head-256 fused path is proven and the conservative measured subgraph delta is at least `0.04597286970625021` seconds/request, 5% of the canonical endpoint. If the supported path, oracle, or savings gate fails, close this architecture/backend line. A larger analytical upper bound without a measured exact-shape path is not a pass.

## Bound identities and limits

- Model/config: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`; config SHA-256 `e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1`.
- Image: `sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a`.
- Checkpoint: exact eight-file, 62,578,655,208-byte resident checkpoint at `/home/glmrunner/gemma-attention-endpoint/checkpoint`; it is retained state, not candidate weights.
- Canonical endpoint terminal SHA-256: `1a7e778eff080bf2eec27da939ea85a894ea9884036bdebd562af371405e78c3`.
- TRTLLM incompatibility terminal SHA-256: `b6b16097bd57aec0fc816f081b521211186291b5803ca8923106798a86578dbf`.
- Prior exact-shape SDPA result SHA-256: `92fa69d260407343a2d9defe742e61a89d33068644bc8896774fdffde059e01c`.
- Prior compute result SHA-256: `02b833cdaa6878816b350ca7cae6982e203fb91a98bdabde2e604d91f66d624a`.

Finish the claim by `2026-07-18T22:20:00Z`, release without teardown, use at most 70 H200 minutes, 5 GiB of temporary artifacts, and `$3.25` cumulative provider exposure. One ordinary import/API/runtime repair is allowed on the retained mutable environment; a second repair, dimension/backend/page sweep, full endpoint checkpoint rewrite, training, quality run, provider allocation, or watchdog mutation is not. A passing proxy returns to the director before any checkpoint or quality work.
