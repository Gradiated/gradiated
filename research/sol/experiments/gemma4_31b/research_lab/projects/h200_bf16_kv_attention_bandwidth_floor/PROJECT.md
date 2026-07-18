# H200 BF16 KV-attention bandwidth floor

## Decision question

Does the compulsory BF16 KV-cache read traffic of exact Gemma 4 hybrid attention already exceed the residual H200 c16 service budget left after measured transformer linears and the actual vocabulary head?

This is independent `$0` analytical evidence while `exact_vllm_h200_c16_c32_endpoint` exclusively owns provider mutation. It must not poll, alter, or wait on that owner. It may falsify an operating point but cannot prove endpoint throughput, attention-kernel efficiency, latency, or quality.

## Authoritative inputs

- `../exact_geometry_runtime_opportunities/GEOMETRY.json`: exact 60-layer five-local/one-global pattern, 50 local layers, 10 global layers, local window 1,024, BF16 KV bytes/token/layer, primary 4,214/358 geometry.
- `../h200_bf16_exact_linear_floor/artifacts/RECONCILED_TERMINAL.json`: raw CUDA-event linears-plus-head floors at c16/c32 and the `0.472012-0.477514 seconds/request` ceilings.
- `../h200_campaign_economic_gate_reconciliation/H200_ECONOMIC_GATE.json`: production planning market gate.
- `research/factory/data/accelerator_inventory.json`: H200 4.8 TB/s HBM and 50 MiB L2 prior. Use the shared inventory query; do not search or transfer latency.

## Immediate bound

For every one of the 358 decode positions, compute exact BF16 K+V bytes read by attention for c16 and c32:

- 50 local layers read `min(context_position, 1024)` tokens per request.
- 10 global layers read the full context position per request.
- Use exact `8192 bytes/token/layer` from the model geometry, preserving GQA/head dimensions.
- Include newly written K/V bytes separately, but make the primary falsifier use reads alone.

Sum across requests and layers for each batch step and across the request. Produce both first/median/last position rows. For the most optimistic physical lower bound, subtract at most one entire 50-MiB L2 capacity from each batch step before dividing by the H200 4.8-TB/s peak; also report zero-L2 and 3.35-TB/s H100-sensitivity views. Do not assume any extra inefficiency, paging, metadata, write traffic, or competing weight traffic in the primary bound.

Translate measured linears-plus-head seconds/request back to batch-step time as `seconds_per_request * batch / 358`. Subtract from both strict and lenient whole-service ceilings transformed the same way. If the optimistic H200 KV-read floor alone exceeds the positive residual at an operating point, classify that point falsified. If it fits, preserve it without claiming performance. Report whether c32's larger batch changes per-request traffic or only step traffic.

As a secondary source-bound opportunity screen, quantify the maximum stock-runtime projection saving from exploiting `attention_k_eq_v=true` with global QKV width 18,432 instead of pinned vLLM's executed 20,480, using the measured global-QKV row. Close it unless the architecture-weighted request saving can reach 5% of total market service time; do not nominate a CUDA project from FLOP ratio alone.

## Budgets and artifacts

- Wall clock: 30 minutes.
- Compute: 1 local CPU-hour; no GPU.
- Storage: 256 MiB retained and 128 MiB project-local temporary; no shared `/tmp`.
- Spend/provider: `$0`; provider mutation forbidden.

Write reproducible code, `KV_ATTENTION_FLOOR.json` with formulas/identities/sensitivities, concise `DECISION.md` and `RESEARCH_LOG.md`, and terminal `STATUS.json`.
