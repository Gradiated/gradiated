# Layerwise sliding-window attention architecture

## Question

Can GLM-4.7 Flash retain periodic full-context MLA layers while using bounded local attention in the remaining layers, reducing exact 8K/1K background decode cost by at least 10% on L40S?

## Why it matters

The retained current-AWQ trace assigns 42.53% of summed decode kernel duration to `_fwd_grouped_kernel_stage1`, while the workload decodes 1,024 tokens after an 8,192-token prompt. Prior MLA-rank work changed latent width and transferred poorly; windowing attacks the other dimension of the hot operation—context length and KV traffic—while preserving selected global layers for long-range information. The campaign permits modest architecture changes and later recovery training, so a global/local layer pattern is admissible as an explicitly non-quality-preserving cost proxy.

This is independent of output-head quantization and of the closed prefix-cache line: it changes attention work within every request and requires no repeated prompt identity.

## Scope

At zero provider spend, bind the exact stock-serving graph (47 layers, 20 attention heads, KV latent rank 512 plus 64 rotary dimensions), current checkpoint/runtime hashes, the 8,192-input/1,024-output c16 workload, retained prefill/decode wall regions, exact attention kernel evidence, KV bytes, L40S limits, and the current 535.286 tok/s / 594.466 tok/s economic gate. Do not treat summed kernel duration as wall time.

Screen a small explicit design set such as local windows 1,024/2,048/4,096 with full-context attention every fourth or eighth serving layer. Derive exact per-token context work, KV residency and c16/c32 implications across the full 8K-to-9K decode trajectory. Use the poor retained MLA endpoint transfer as a conservative sensitivity rather than assuming context-work reductions transfer linearly. Identify the minimum local-layer fraction/window that could still clear the gate under defensible overhead and transfer bounds.

Inspect the pinned GLM/vLLM attention source for uniform or per-layer window support and build the smallest CPU-executable source-bound mask/state fixture that proves global layers see the full prefix, local layers see only their declared tail window, positions remain correct, decode KV state is bounded as claimed, and stock mode is unchanged. Absence of existing runtime support is an implementation-boundary result, not by itself an economic falsification; however, do not nominate GPU work unless the conservative cost bound clears and the required change is narrower than a new attention engine.

Do not run a GPU, mutate a provider, edit the shared launcher, train/evaluate quality, assume tenant prefix reuse, reduce MLA ranks, change MoE/head precision, or construct a general scheduler. Label all quality effects deferred and all trace transfers by evidence type.

## Resources

- Current c16 control and traces: `../nebius_current_awq_c16_direct/` and `/root/workspace/research/lab/experiments/glm47flash/campaign_100/allocations/nebius_l40s_vllm_awq_splits_ab_v24r2/`.
- MLA transfer evidence: `../l40s_model_chip_codesign/`.
- Saturation/capacity evidence: `../current_awq_saturation_bound/` and `../a40_exact_memory_admission/`.
- L40S dossier: `../../hardware/L40S.md`.
- Exact checkpoint: `/root/.cache/glm47flash-awq-ab31d120`.

## Portfolio-changing result

Return one content-bound decision artifact with the screened policies, context/KV accounting, conservative endpoint sensitivity, runtime-support boundary, executable mask fixture, and a close-or-measure recommendation. Nominate at most one later exact-shape or server proxy only if a specific global/local pattern conservatively supports at least 594.466 tok/s and has a bounded implementation path in the pinned runtime. Otherwise close sliding-window attention without provider work.
