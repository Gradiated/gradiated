# Full-47 MLA-rank robust falsifier

## Question

Does any modest full-47 MLA KV rank in `{448, 416, 384}` both admit the authoritative c32 workload inside the `44,532-MiB` robust L40S envelope and retain a conservative path to `606.355` output tok/s?

## Why this matters

Serial depth restoration is closed, while the campaign explicitly prioritizes near-original MLA-state reduction. Earlier full-model rank screens predated the valid r3 full-model c16 endpoint and the measured depth42/depth43 c32 packing evidence, omitted rank416, or used inconsistent memory arithmetic. A single exact rebase can durably close or nominate the smallest rank without materializing another 20-GB checkpoint. Preliminary reconstruction says only rank384 clears robust memory, but even granting the closest measured packing ratio and the complete scope-matched MLA transfer reaches only about `594.559` tok/s, so the project must fail closed unless independent reproduction overturns that bound.

## Fixed evidence

- Exact full model: `/root/.cache/glm47flash-awq-ab31d120`, revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, compressed-tensors symmetric group-32 W4A16 with BF16 KV, 47 serving layers, `kv_lora_rank=512`, rope width 64.
- Valid full-model r3 c16 summary: `../near_stock_c32_memory_frontier/artifacts/near_stock_c32_memory_frontier_r3_control/summary.json`, SHA-256 `23bce62e7a9f10c4d5708630a5351146f0c785ef2bc1281c6757459fb31c8218`, `552.171055` output tok/s.
- Stock full-model c32 projection `46,875.7 MiB`; robust limit `44,532 MiB`; L40S visible capacity `46,068 MiB`.
- Measured c32 comparators: depth42 `686.910494/616.602087 = 1.114013` c32/c16 and depth43 `636.469100/600.704460 = 1.059538`. Use the latter as the closest smaller-divergence packing credit unless a stricter scope-matched bound is justified; do not transfer raw throughput.
- MLA calibration: `../l40s_model_chip_codesign/RANK_TILE_BOUND.json` records `14.35%` component-work reduction to `1.05%` endpoint gain and a `7.317%` scope-matched endpoint share. Rank384 `BLOCK_N=64`, stage-2 remains `126,720 B` against the `101,376-B` SM89 limit.
- Reconcile rather than inherit `../minimal_change_c32_codesign/CANDIDATE_COMPARISON.json`, `../depth_mla_capacity_codesign/`, and `../depth44_rank448_joint_falsifier/`; their model depth and accounting contracts differ.
- Economics/workload: planning `$1.10/hour`, absolute `594.466` and robust `606.355` tok/s gates, cache off, 8,192 input/1,024 output, c32, 300-second background envelope.

## Execution contract

Work offline at `$0` for at most 600 seconds, 4 GiB peak RSS, and 12 MiB of new artifacts. Independently verify exact source headers, payload accounting, group-32 tensor shapes, and pinned vLLM loader use of `config.kv_lora_rank` for ranks 448, 416, and 384. Recompute BF16 KV savings, projection-payload credits, c32 peak, SM89 tile legality, and endpoint bounds from the fixed measured artifacts. Use conservative interval/ratio reasoning; an optimistic upper bound below `606.355` closes the rank. Do not infer quality recovery.

Return exactly one terminal result:

- `NOMINATE_FULL47_RANK`: exactly one smallest rank has projected c32 `<=44,532 MiB`, a coherent deterministic rewrite/loader route, and a conservative endpoint bound `>=606.355` tok/s; or
- `FULL47_RANK_CLOSE`: all ranks fail memory, representation, tile/runtime, endpoint, or identifiability gates.

Do not write or materialize checkpoint payloads, use CUDA or provider/network resources, edit shared runtime/launcher code, prepare a controller, train, or run quality. Produce one compact decision artifact, an optional calculator/shape fixture, and a concise research-log update. No successor.

## Available resources

Use the fixed local evidence above, `hardware/L40S.md`, `/root/workspace/research/factory/tools`, and `/root/workspace/research/sol/experiments/glm47flash/campaign_100`.
