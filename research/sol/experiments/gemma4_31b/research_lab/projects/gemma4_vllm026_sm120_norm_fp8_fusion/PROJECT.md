# Gemma 4 vLLM 0.26 sm_120 norm-to-FP8 fusion

## Question

Can current official vLLM 0.26.0 fuse one recurring Gemma 4
RMSNorm/fused-add-RMSNorm producer directly into its online dynamic-FP8
quantization and `CutlassFP8ScaledMMLinearKernel` consumer on sm_120, removing
an intermediate BF16 write/read and launch without changing model semantics?

## Why this matters

The campaign needs a complete result equivalent to at most
`0.500119281574996 s/request` on the fixed H200 denominator, or the same 20%
price-normalized improvement on another accelerator. The live current-vLLM
discriminator has already selected online FP8 on the RTX PRO 6000, so an
implementation that removes repeated norm-to-quantization traffic can become a
stackable endpoint intervention if the current runtime comparison is useful.

## Current evidence

- Exact model: `google/gemma-4-31B-it` at
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Current runtime: official vLLM `0.26.0+cu129`, wheel SHA-256
  `6ce4ca30616f0a35810391015622b197a7b8b267ed27f8716f0789db79ff578b`,
  running with Torch `2.11.0+cu130` on sm_120.
- The live runtime selected
  `CutlassFP8ScaledMMLinearKernel for Fp8PerTensorOnlineLinearMethod`.
- Its compilation configuration reports `fuse_norm_quant`,
  `fuse_act_quant`, and `fuse_qk_norm_rope_kvcache` disabled.
- Gemma 4 heterogeneous head dimensions force the current
  `TRITON_ATTN` backend. This project must stay on the norm/activation-to-linear
  boundary and must not duplicate attention-backend work.
- The direct endpoint project owns the only RTX bench and its sole c32 sample.
  No result from this project may alter or delay that in-flight contract.

The exact measured startup observation is recorded in
`DIRECTOR_VLLM026_RUNTIME_BOUNDARY_EVIDENCE_20260729T0633Z.json`.

## Scope

Use `$kernel-research` and trace one production Gemma 4 boundary through the
official vLLM 0.26.0 source:

1. bind the exact module, prefill/decode phase, c32 row geometry, K/N, dtype,
   scale convention, layouts, producer symbol, quantizer, FP8 GEMM method, and
   first BF16 consumer;
2. explain why the existing fusion pass is disabled or inapplicable for this
   path on sm_120;
3. implement one production-bound fusion pass, custom op, or kernel entrypoint
   that invokes the unchanged online-FP8 GEMM consumer without materializing
   the eliminated BF16 boundary;
4. provide an sm_120 build/run command and an exact future oracle against the
   unfused framework path, including a physical prediction for launch count
   and bytes moved.

Do not claim a GPU, SSH to the retained bench, install into its runtime, edit
the active endpoint owner, or submit HTTP/scientific traffic. Source work may
use official public vLLM 0.26.0 sources and controller-local tools only.

## Budget and artifact contract

- Wall-clock budget: 60 minutes.
- GPU budget: zero.
- Provider spend: `$0`.
- Persist implementation bytes before publishing
  `VLLM026_SM120_NORM_FP8_FUSION_OFFLINE_RESULT.json`.
- The result must hash-bind the implementation, exact source identities,
  geometry, future command, oracle, and expected physical change.
- If no credible production boundary survives source inspection, publish a
  typed `none` result with the exact blocking symbols and select no substitute
  mechanism.

## Portfolio-changing result

A concrete semantics-preserving implementation with an exact future oracle
becomes the leading compatible follow-up for a later director handoff to an
sm_120 bench. A typed `none` closes only this specific current-vLLM fusion
boundary and redirects the next mechanism toward another measured FP8 linear
or scheduler/dataflow cost.
