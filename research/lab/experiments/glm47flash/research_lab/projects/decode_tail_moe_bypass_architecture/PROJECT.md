# Decode-tail MoE bypass architecture

## Question

Can GLM-4.7 Flash preserve full-depth attention and KV state while bypassing routed-plus-shared MoE work in selected late layers during decode, reducing sustainable L40S c16 cost by at least 10% with a smaller state disruption than exit-35?

## Why it matters

The current exact-AWQ c16 endpoint is 535.286 output tok/s at about `$0.571/M` using the authoritative `$1.10/L40S-hour` planning rate; the campaign gate is 594.466 tok/s or at most `$0.514/M`. A retained cache-off trace attributes 34.16% of summed kernel duration to dense GEMM/GEMV and 3.72% to MoE routing/sort, versus 33.26% to grouped MLA and 26.49% to unclassified work. Those sums are not wall-time shares, but they identify expert execution as a material target that faster H100 hardware did not eliminate: the same-identity H100 conservative screen closed at only 935.036 tok/s against a 1,513.186-tok/s economic gate.

Exit-35 removes the last 12 complete decode blocks, including attention and future tail KV. This project tests a distinct model change: execute attention, residuals, and KV writes in all 47 layers, but replace the late decode MoE sublayer with its residual identity path. The model has 46 MoE layers, four routed width-1,536 experts per token, and one always-on width-1,536 shared expert, so a late MoE bypass may remove substantial fragmented W4/BF16 work while retaining more of the model's state evolution for later recovery training.

## Relevant evidence

- `../sequence_early_exit_architecture/` binds full-prefill/decode phase detection and the current 47-layer serving graph, but its scientific arm skips whole tail blocks.
- `../adaptive_moe_architecture/` binds the exact routed/shared MoE implementation and a 13.288% ideal top-2-plus-no-shared ceiling; that endpoint arm remained operationally unmeasured.
- `../layer_depth_architecture/depth_bound.json` and `/root/workspace/research/lab/experiments/glm47flash/campaign_100/allocations/nebius_l40s_vllm_awq_splits_ab_v25r1/trace-regions.json` contain the retained layer and kernel accounting. Summed kernel durations must not be treated as endpoint wall time.
- `../h100_current_awq_c16_bound/h100_current_awq_c16_bound.json` identifies grouped MLA and non-GEMM scheduling tail as the reason hardware-only transfer is uneconomic.

## Scope

At zero provider spend, bind checkpoint revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, the exact `glm-vllm:0.15.0-transformers-1618d44` runtime, 47 serving layers, and the cache-off c16 8,192-input/1,024-output workload with `max_num_seqs=16` and `num_kv_splits=4`. Full prefill must remain stock. Decode must still execute all 47 attention paths and all KV writes. In nominated late MoE layers only, skip post-attention normalization, routing, routed experts, shared expert, and their residual add so the attention-updated residual passes directly to the next layer. Preserve layer 0, final norm, and the stock vocabulary head.

Screen the smallest useful family: last-12 MoE layers first, then at most two nearby patterns only if needed to locate the 594.466-tok/s boundary. Account exactly for routed/shared weights, active FLOPs, routing launches, attention/KV work retained, prefill dilution, head work, and possible fixed scheduling tail. Calibrate conservatively against the measured c16 endpoint and poor prior transfer from summed kernel work; report an ideal ceiling separately from the portfolio decision bound.

Build one source-bound fail-closed fixture against the pinned model implementation. It must prove stock full-depth identity, full-depth prefill, all-layer decode attention/KV calls, absence of MoE calls only in the nominated late decode layers, stable hidden/logit shapes, final norm/head execution, and deterministic handling or rejection of mixed prefill/decode batches. Reuse the phase-contract evidence conceptually, but do not edit the exit project, shared launcher, or provider tools. Do not allocate CUDA, mutate a provider, train recovery, change top-k/expert width/attention/KV precision, or build scheduler infrastructure.

## Available resources

- Current checkpoint: `/root/.cache/glm47flash-awq-ab31d120`.
- Current measured control and traces: `../nebius_current_awq_c16_direct/` and `/root/workspace/research/lab/experiments/glm47flash/campaign_100`.
- Model/chip dossier: `../../hardware/L40S.md`.
- Shared tools: `/root/workspace/research/factory/tools` and `/root/workspace/research/lab/experiments/glm47flash/campaign_100`.
- Fresh production prices: `/root/workspace/research/factory/data/gpu_prices.json`.

## Artifact contract

Produce `decode_tail_moe_bypass_bound.json`, `source_bound_decode_tail_moe_bypass.py`, and `RESEARCH_LOG.md`. Label evidence as measured, derived, source-bound, or inferred, and record exact source paths and hashes.

## Portfolio-changing result

Nominate at most one later matched L40S c16 ceiling only if the source fixture passes and a conservative endpoint bound reaches at least 594.466 output tok/s after unchanged prefill, retained all-layer attention/KV, final head work, and explicit overhead. Otherwise close at `$0`. A passing cost proxy would justify later recovery-quality work; it is not deployable or provider-beating evidence.
