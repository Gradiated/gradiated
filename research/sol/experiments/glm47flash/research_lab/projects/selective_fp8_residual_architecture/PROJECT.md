# Selective FP8 residual architecture

## Question

Can converting the BF16 components left inside the public AWQ checkpoint to an Ada-native FP8 representation reduce GLM-4.7 Flash c16 L40S cost by at least 10% or unlock c32/a cheaper memory tier?

## Why it matters

The mixed checkpoint leaves at least the output head, dense first block, and shared-expert path outside routed W4 execution. Retained L40S traces assign a 14.09% interval-union ceiling to the BF16 vocabulary projection and up to a 7.10% deliberately optimistic ceiling to the shared/standard-Marlin residual. Factorizing the head and removing the shared expert separately are closed, but selective FP8 can halve representation bytes and use the L40S's fourth-generation FP8 Tensor Cores without deleting those functions. The material hypothesis is the combined residual path, not the head alone.

## Scope

At zero provider spend, parse every current-AWQ tensor header and pinned loader path to identify exact BF16/FP16 residual tensors, bytes, shapes, layer ownership, and current kernels. Test FP8 E4M3 first. Determine whether the pinned or a clearly content-bound current vLLM/PyTorch path can load or stage per-tensor/per-channel FP8 weights for these exact shapes and execute Ada FP8 Tensor Core operations without a per-token dequantization/conversion cost that erases the gain. Use local container compilation/source tests and the smallest exact-shape executable fixture available; do not claim L40S performance from CPU timing.

Quantify representation bytes, c16 arithmetic intensity/work reuse, traced component ceilings, eliminated traffic, conversion/scale overhead, and c16/c32 memory admission. Calibrate a combined endpoint bound against the retained c16 result and prior poor component-to-endpoint transfer. If the exact FP8 path is absent, inspect supported 2:4 structure only as one fail-fast alternative when the existing runtime already exposes it; do not build a new sparse kernel or broaden into general quantization research.

Keep weights/functions present and label all casting or synthetic tensors as an architecture-cost proxy. Do not factorize the head, change expert count/top-k, skip blocks, alter MLA/KV precision, run a provider, train, or perform broad quality evaluation. Leave recovery quantization/training and full quality certification until the cost mechanism survives.

## Resources

- Current control: 535.286 output tok/s and about `$0.571/M` at the fresh `$1.10/L40S-hour` planning rate.
- Exact AWQ checkpoint: `/root/.cache/glm47flash-awq-ab31d120`.
- Exact BF16 checkpoint/config: `/root/.cache/glm47flash-bf16-33faccf4`.
- Retained output-head and MoE evidence: `../output_head_architecture/` and `../adaptive_moe_architecture/`.
- Shared chip dossier: `../../hardware/L40S.md`.
- Pinned runtime/container and traces: `/root/workspace/research/sol/experiments/glm47flash/campaign_100`.

## Portfolio-changing result

Nominate one combined selective-FP8 candidate only if exact tensor accounting plus an executable supported path gives a conservative route to at least 10% lower sustainable c16 cost or a real c32/cheaper-placement discontinuity. State the exact later L40S control/candidate measurement and the minimum instruction/bytes/wall-time counters. Otherwise close this precision lane without a provider or custom-kernel follow-up. This project has no provider authority or spend.
