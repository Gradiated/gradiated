# Query-LoRA rank/channel L40S falsifier

## Question

Can the full-47 query projection reduce `q_lora_rank=768` to a tile-aligned 640 or 512 channels with enough source-bound critical-path leverage and exact-weight proxy fidelity to support at least a 3% c32 endpoint improvement?

## Why this is independent

The exact model uses `q_lora_rank=768`, `kv_lora_rank=512`, hidden width 2,048, 20 attention heads, qk-nope width 192, and rope width 64. This project changes only the q-a -> q-RMSNorm -> q-b channel bottleneck. It preserves KV/MLA state and cache size, all attention head dimensions, MoE/shared experts, depth, head, precision, runtime, and scheduler.

The terminal MLA-rank projects changed `kv_lora_rank` to unlock KV capacity and attention-kernel shared-memory geometry. They did not test query-rank channel reduction. This candidate is worthwhile only if the retained exact-model trace assigns enough non-overlapped serving time to q-a/q-b and the paired channel reduction survives q-RMSNorm output reconstruction.

## Fixed evidence and candidates

- Exact checkpoint `/root/.cache/glm47flash-awq-ab31d120`, revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, config `079f8f...fa7622b9`, and index `b9c534...988695`.
- Retained source/trace artifacts under `../moe_dense_residual/`, `../l40s_model_chip_codesign/`, and `../full47_stock_c32_robust_gap_attribution/`.
- New exact c32 bracket archive `../full47_current_background_knee_direct/artifacts/l40s_background_knee_20260716_r1/vllm-awq-batch.tar.gz`, SHA-256 `94e2f841...86dbf`, anchor mean `602.157121` tok/s and `1.03x` gate `620.221834`.
- L40S resource model `hardware/L40S.md`; planning rate `$1.10/hour`; absolute/robust endpoint gate `606.355` tok/s.

Screen exactly ranks 640 and 512. Preserve the q-a/q-b/RMSNorm topology; use deterministic channel selection or a source-bound paired reparameterization that maps to group-32 W4 shapes and existing SM89 Marlin-compatible multiples. Do not remove q-RMSNorm, change head dimensions, or transfer a KV-rank bound.

## Immediate `$0` falsifier

Within 1,200 seconds, 8 GiB RSS, 48 MiB new artifacts, and `$0`, first bind q-a/q-b operations to source and retained trace intervals without summing overlaps. Compute the impossible endpoint ceiling for removing the proposed fraction of the whole q path. If neither rank can support at least a `3.5%` endpoint reduction before overhead, close immediately.

Only for a surviving rank, inspect exact tensor headers/payloads, reconstruct the paired q path including q-RMSNorm, and compare stock versus candidate outputs on deterministic Gaussian and heavy-tail hidden vectors across a fail-closed stratified set of layers. Report physical bytes/MACs, tile shapes, extra launches/intermediates, trace attribution, relative-L2, cosine, and worst-layer behavior. Do not write a checkpoint, patch runtime code, use CUDA/provider resources, train, or prepare an endpoint.

Return `Q_RANK_CLOSE` on inadequate trace leverage, geometry, or fidelity. Return `NOMINATE_Q_RANK_PROXY` for exactly one rank only if its conservative endpoint path reaches `max(606.355, 1.03x contemporaneous c32 control)`, median cosine is at least `0.99`, p05 cosine at least `0.98`, p95 relative-L2 at most `0.10`, no layer relative-L2 exceeds `0.15`, and all outputs are finite. A nomination is quality-deferred architecture-cost evidence; state but do not prepare the later direct endpoint.

## Available resources

Use the fixed local projects above, `/root/workspace/research/factory/tools`, and `/root/workspace/research/lab/experiments/glm47flash/campaign_100`.
