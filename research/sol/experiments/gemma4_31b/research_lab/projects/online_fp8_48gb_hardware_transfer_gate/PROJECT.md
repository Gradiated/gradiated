# Online-FP8 48-GiB hardware transfer gate

## Decision question

If the exact online-FP8 L40S mechanism passes, which materially cheaper compatible 48-GiB hardware is worth one matched component measurement, and how slow may it be relative to L40S while still beating the campaign price frontier?

This is independent `$0` candidate selection. It must not poll, edit, wait for, or infer from the live L40S owner. It cannot transfer throughput or claim availability from price alone.

## Scope

Use fresh shared `gpu_prices.json`, `accelerator_inventory.json`, exact online-FP8/W4 consumer identities, corrected c12 capacity/KV evidence, L40S market gate, and existing 48-GiB hardware screens. Do not browse or duplicate price research while inventory is fresh.

Compare at most RTX 6000 Ada, L40S, and any other inventory-bound 48-GiB candidate with the same required CUDA/SM/kernel support. Record SM count, compute capability, tensor formats, memory/L2/bandwidth, power/topology, committed planning rate/range, exact runtime/consumer compatibility evidence, and missing facts. Compute each candidate's required completed rps and maximum permissible component/request-time slowdown relative to L40S under the strict campaign request cost and planning all-in factors. Treat c12 as primary; reject logical points without at least 0.25 GiB capacity headroom.

Return at most one conditional matched-hardware arm, with exact comparator, shapes, telemetry/counters, availability/quote gate, explicit future wall/provider/compute/storage/spend budget, and trigger tied to a valid L40S component terminal. Or return typed none. No external claim, provider query, image/checkpoint, compilation or GPU work.

## Budgets

- Wall clock: 25 minutes.
- Compute: 1.5 local CPU-hours; no GPU.
- Storage: 384 MiB retained plus 128 MiB temporary.
- Spend: `$0`; provider access/mutation forbidden.

Write `HARDWARE_GATE.json`, source/hash manifest, concise log/status.
