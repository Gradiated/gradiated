# Shared GPU price inventory refresh

## Question

What are the current experiment and 12–24 month production-planning prices for the accelerator entries already present in `research/factory/data/gpu_prices.json`?

## Scope

The shared inventory is 7.35 days old and has crossed its seven-day freshness contract. Perform exactly one zero-cost refresh using current primary vendor pricing where available and clearly labeled independent market evidence only where the existing schema requires it. Preserve the distinction between preemptible experiment rates, on-demand references, and committed production-planning rates. Do not search for unrelated accelerators, create provider resources, or block the paid scientific lane.

Update the shared inventory and its source timestamps, run `PYTHONPATH=research/factory/src python3 -m grad_research gpu-prices --require-fresh`, and record a concise evidence note. If a source is unavailable, retain the prior value labeled stale rather than guessing.

## Budget

Zero dollars, no GPU, and at most 45 wall-clock minutes.
