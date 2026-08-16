# B200 exact-Gemma kernel/economic mechanism

## Decision question

Can B200's exact supported low-precision/kernel realization plausibly overcome its `$5.15/GPU-hour` planning rate versus H100 `$2.80/GPU-hour`—a `1.8392857×` price premium—on the exact 4,214-prompt/358-output Gemma 4 31B workload, and what smallest direct experiment would decide it?

This is a materially different `$0` deep hardware-placement project after H100 program lineages closed operationally. Use fresh canonical price/inventory data, exact Gemma six-shape/head/hybrid-attention geometry, measured H200 component floors, valid H100 M8 descriptive rows, L40S falsification, and pinned vLLM/upstream B200 source. Do not transfer performance across chips or representations.

Trace a concrete causal chain from exact shapes and workload through B200 tensor formats/instructions, SM/tile/occupancy, HBM/L2/shared/register limits, runtime consumer selection, and production price. Consider BF16, actual supported FP8, W4/Marlin or Blackwell-native alternatives, paged FP8 KV, and the large tied head only where exact source support exists. Quantify the throughput/service-time hurdle and identify whether decode, prefill, head, or attention is capable of the required >1.84× realization.

Return content-addressed `MECHANISM.json` with either one content-bound direct B200 component/endpoint falsifier—exact program path, comparator, rows, oracles, counters, economic aggregation, provider/venue requirement, and stop rule—or typed none if source support/price physics cannot justify a direct test. No provider mutation, GPU, image/checkpoint pull, or compilation.

Budgets: 30 wall minutes; 3 local CPU-hours; 768 MiB retained plus 384 MiB temporary; `$0` spend.
