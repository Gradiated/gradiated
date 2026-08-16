# Gemma 4 small architecture/chip co-design

## Question

Which small, plausibly post-trainable Gemma 4 architecture changes can reduce sustainable serving cost by at least 5% because they improve realization on realistic H200, H100, L40S/RTX 6000 Ada, B200, or MI355X-class hardware?

## Work

Use exact checkpoint geometry, sampled weight evidence, measured endpoint/component telemetry, pinned runtime source, and the shared accelerator inventory. Trace hot tensors onto SM/CU grids, tensor-core tiles, register/shared-memory pressure, L2 working sets, and HBM traffic. Consider changes such as local/global KV geometry, local-to-global cadence, tensor dimensions and grouping, tied embedding/head representation, and other modest dataflow changes. Derive alternatives from measured bottlenecks rather than producing a generic idea list.

Reject blunt layer, expert, width, or parameter removal and any proposal whose speedup is merely proportional to deleted model capacity. Each survivor needs a credible modest post-training route, an exact-shape performance proxy or simulation, expected all-in cost impact, chip-specific mechanism, and a later GPQA-Diamond/TauBench validation plan. Nominate at most two direct experiments and implement/run the cheapest zero-cost proxy now.

## Limits

60 wall minutes, 5 local CPU-hours, 4 GiB artifacts, no provider mutation in the first turn. No broad quality evaluation.
