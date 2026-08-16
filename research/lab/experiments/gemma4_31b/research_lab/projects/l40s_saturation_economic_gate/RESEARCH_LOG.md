# Research log

No researcher turn has completed. The endpoint is one reproducible saturation/memory/economic decision surface, not another paid-run admission gate.

## 2026-07-17 — economic and memory interpretation gate

Question: what throughput must one L40S sustain to beat the captured campaign-mix retail endpoints, and does the admitted c8 contract fit the conservative FP8/KV bound?

Action: ran `calculate_gate.py` against the content-addressed market target, FP8 memory accounting, and fresh shared `gpu_prices.json`; no provider or paid owner was touched. The first run exposed and fixed two input-shape assumptions (a formula metadata row in the market object and the inventory's accelerator list representation), then the complete calculation and JSON parse passed.

Evidence: planning rate `$1.10/GPU-hour`, production range `$1.00–$1.25/GPU-hour`; planning-base cheapest exact-endpoint hurdle 0.717 completed request/s (3,022 prompt, 257 output, 3,278 total tokens/s), conservative hurdle 1.158 request/s. Conservative memory totals are c1 40.062, c2 40.774, c4 42.198, c8 45.046, c16 50.742 GiB against 44.704 GiB capacity; c8 is -0.342 GiB outside the bound. The 10K single stream is 40.504 GiB with 4.20 GiB headroom. These are derived bounds, not CUDA measurements.

Interpretation: c8 is not guaranteed safe; c4 is the highest conservative guaranteed-fit primary concurrency. Paid artifacts should compare measured completed throughput and all-in factors against `SATURATION_GATE.json`; c4 can win without c8. A later saturation arm is justified only if measured memory/queue/GPU telemetry explains a fitting-concurrency miss. Completion time remains a sensitivity, not a hard gate.

Next move: director reconciles the eventual direct L40S result against `DECISION.md` and `SATURATION_GATE.json`; this project is complete and does not launch a successor.
