# Top-3/shared sustainable COGS bound

## Question

Does the bracketed `644.318005`-tok/s top-3/shared result leave a feasible sustainable all-in operating envelope at or below the authoritative `$0.514/M` output-token target after lifecycle and utilization losses?

## Why it matters

The raw planning-GPU quotient is about `$0.474231/M`, only `7.74%` below the target. The retained bracket amortized setup across three arms but recorded `317.894` useful GPU seconds in `2054.961` typed allocation seconds and `$0.489835297` through post retrieval; the cleanup tail is not aggregated. This project must decide whether top-3 has enough economic headroom to justify later quality/recovery work, without confusing an experimental three-arm session with production utilization.

## Scope

Work offline at `$0` for at most 600 seconds, 4 GiB RSS, and 32 MiB of new artifacts. Verify the three immutable summaries and use the fresh shared L40S planning rate/range; do not search prices. Reuse the measured lifecycle evidence and formulas in `../full47_stock_frontier_sustainable_cogs/` rather than opening another lifecycle study. Separate measured, derived, and assumed terms. Compute minimum productive fraction, batches/session, maximum lifecycle/interruption/retry budget, and rate sensitivity needed to stay at or below `$0.514/M`. Report the experimental typed cost and authenticated cleanup separately from sustainable production COGS.

Return `SUSTAINABLE_HEADROOM_ADMISSION` only if a named conservative operating envelope fits the authoritative target with nonzero allowance for storage, transfer, orchestration, interruption/retry, and headroom. Return `MARKET_ONLY_HEADROOM` if only the exact-model non-reasoning retail hurdle remains feasible. Return `SUSTAINABLE_HEADROOM_CLOSE` otherwise. Every result remains conditional on unresolved model quality and cannot authorize spend or a long session.

## Evidence

- `../full47_top3_shared_c32_direct/`
- `../full47_stock_frontier_sustainable_cogs/`
- `/root/workspace/research/factory/data/gpu_prices.json`
- Fixed bracket: `611.326249 / 644.318005 / 601.371981` tok/s; control drift `1.641673%`
- Planning rate `$1.10/hour`, range `$1.00–$1.25/hour`, authoritative target `$0.514/M`

## What changes the portfolio

Admission plus a non-terminal quality signal can justify a later bounded quality/recovery decision. A sustainable close prevents more L40S/top-k spend even though the architecture-cost mechanism is real. A market-only result keeps the result as competitive evidence but not as the campaign's authoritative economic pass.

## Available resources

- `/root/workspace/research/factory/tools`
- `/root/workspace/research/sol/experiments/glm47flash/campaign_100`
