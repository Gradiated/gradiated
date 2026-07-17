# H200 BF16 bandwidth and economic falsifier

## Question

For the exact pinned BF16 Gemma 4 31B workload, can one H200 plausibly reduce sustainable cost versus one H100 by converting its 43.3% higher HBM bandwidth and larger memory into more than the 16.1% throughput gain required by current committed planning rates?

## Why this independent line matters

The H100 stock/MTP owner is live and exclusively owns provider mutation. The completed FP8 project nominates a cheaper L40S representation arm, but current first-party issues make FP8 output correctness a real failure mode. H200 is a disjoint, quality-preserving placement hypothesis with the same SM90 compute architecture, model bytes, tokenizer, runtime family, and BF16 semantics as H100. It provides a fast fallback and tests whether exact-model decode is actually limited by weight streaming rather than scheduler, launch, or compute.

The fresh shared inventory gives H100 SXM 80 GB / 3.35 TB/s at `$2.80/GPU-hour` planning and H200 SXM 141 GB / 4.80 TB/s at `$3.25/GPU-hour`. H200 therefore needs `3.25 / 2.80 = 1.160714x` matched H100 throughput before other overhead; its bandwidth ratio is `4.80 / 3.35 = 1.432836x`. Those ratios are screening bounds, not performance claims. Experiment accounting later uses the actual authenticated rates, currently referenced as `$2.15` and `$2.45` per GPU-hour before disk.

## Immediate `$0` scope

Use the exact geometry and identities in `../exact_geometry_runtime_opportunities/`, the current H100 project specification and telemetry schema, and `research/factory/data/{accelerator_inventory,gpu_prices}.json`. Check the current Nebius H200 one-GPU catalog/placement shape read-only once if needed; do not search prices already present in the fresh inventory. Do not mutate a provider, wait for the H100 terminal, edit another project, or build a new lifecycle wrapper.

Produce content-addressed artifacts that:

1. Map the exact 62.55 GB BF16 weights, 60-layer five-local/one-global attention, 262,144-vocabulary tied head, primary 4,214/358 workload, 10K comparator, and concurrency ladder onto H100 versus H200 HBM bytes, L2, SM/grid, KV, and memory headroom. Bound the maximum endpoint gain under weight-streaming, compute, scheduler/launch, and mixed bottleneck cases. Do not use peak FLOPS or bandwidth as transferred throughput.
2. Calculate the exact production and experiment-rate throughput break-evens, including the shared rate ranges, then define which H100 counters/result fields would admit or kill a paid H200 arm. The packet must be usable whether the current owner returns stock-only, MTP/async, or a typed operational failure.
3. Bind one direct matched H200 packet using the same pinned model revision, tokenizer/workload bytes, BF16 dtype, immutable Gemma 4 image, text-only settings, and proven Nebius create/reconcile/watchdog/retrieval/cleanup lifecycle. Identify only H200-specific mutable placement checks. The first scientific arms are the stock primary workload at the H100 saturation points and the 10K single-stream comparator; no MTP, FP8, or new quality harness belongs here.
4. Nominate the paid arm only when the conservative telemetry-conditioned case can exceed the `1.160714x` base throughput hurdle or creates a concrete replica/headroom discontinuity. If H100 evidence shows scheduler/compute limitation with insufficient recoverable bandwidth or H200 placement is unavailable, close the line with the quantified reason.

## Decision and resources

This project ends with one `H200_PACKET.json` plus `BOTTLENECK_BOUND.json` and `DECISION.md`, or a typed closure. It is successor planning only: the director decides later whether to activate the paid arm after the current H100 allocation is terminal and inventory is empty.

- Provider mutation and spend: prohibited (`$0`).
- Wall clock: 90 minutes.
- Compute: at most 3 local CPU-hours; no CUDA requirement.
- Storage: 1 GiB maximum; no checkpoint materialization.
- A later paid packet may request at most one H200, 2 provider-hours, 200 GiB disk, and `$6.00`, but this project has no authority to launch it.
