# Exit-35 endpoint phase attribution

## Question

Why did verified forced decode exit after layer 35 improve the exact c16 endpoint by only `1.4119%`, and what measured work family—if any—still supports a materially different path from `552.171055` to `594.466` output tok/s on L40S?

## Why this matters

The terminal exit-35 archive is the first request-complete measurement of a large decode-depth intervention on the current full model. It skipped layers 35–46 during decode yet reached only `559.969097` tok/s, far below the economic gate. The raw delta can close broad classes of decode-only model changes or reveal that fixed prefill, head, scheduling, kernel-shape, or intervention overhead hid the intended savings. That attribution is more decision-relevant than opening another proxy from summed trace time.

## Fixed evidence

- Candidate: `../full_model_exit35_c16_corrected_key/artifacts/nebius_l40s_exit35_c16_2026-07-16-r1/summary.json` and archive, with verified patch/phase behavior, 32/32 requests, `559.969097` tok/s, `58.518` useful GPU seconds, and zero cleanup inventory.
- Current stock context: `../near_stock_c32_memory_frontier/artifacts/near_stock_c32_memory_frontier_r3_control/summary.json`, SHA-256 `23bce62e7a9f10c4d5708630a5351146f0c785ef2bc1281c6757459fb31c8218`, `552.171055` tok/s.
- Consume retained L40S trace regions and the exit patch evidence only when they bind the same exact 8,192-input/1,024-output, cache-off c16 geometry. Do not treat summed overlapping kernel durations as endpoint wall-time shares.
- Authoritative gate: `$1.10/hour`, `$0.514/M`, `594.466` output tok/s, complete requests inside 300 seconds; latency below that envelope is secondary.

## Scope and stop rule

Within 900 seconds, 6 GiB RSS, 64 MiB new artifacts, and `$0`, bind comparability of the r3 and exit-35 artifacts, then decompose the measured endpoint into the smallest defensible prefill, decode-layer, output-head, scheduler/queue, and intervention-overhead terms supported by request rows, server metrics, GPU telemetry, patch counters, and scoped trace intervals. Quantify uncertainty and calculate the minimum removable endpoint fraction still required to reach the gate.

Stress at least: request-duration sampling uncertainty, contextual rather than adjacent control identity, fixed prefill dilution, and the possibility that skipped layer work was overlapped or replaced by another bottleneck. Use analytical bounds where direct attribution is impossible; return `UNIDENTIFIABLE` instead of inventing a wall-time decomposition.

Return exactly one terminal result:

- `DECODE_LAYERWORK_CLOSED`: verified skip behavior plus conservative attribution shows further decode-layer/MoE work removal cannot clear the gate;
- `RESIDUAL_MECHANISM_NOMINATED`: one specifically named, materially different work family has a conservative removable fraction sufficient for `594.466`, with the cheapest next falsifier stated;
- `UNIDENTIFIABLE`: the archives cannot distinguish the causal explanation; state the one measurement that would resolve it, without preparing or executing that measurement.

Do not observe or modify another active project, use CUDA/network/provider resources, run inference, repair a patch, edit shared tools, train, evaluate quality, or open a successor project.

## Artifact contract

Produce one compact JSON with input hashes, comparability checks, measured rows used, interval/phase accounting, uncertainty and stress cases, required-removal calculation, and terminal decision. Append a concise `RESEARCH_LOG.md`; keep any analysis script project-local.
