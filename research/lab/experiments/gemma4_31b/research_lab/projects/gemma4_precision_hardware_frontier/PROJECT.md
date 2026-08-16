# Gemma 4 precision and hardware frontier

## Question

Which currently obtainable chip plus supported BF16/FP8/W4 execution path has the best credible production cost for exact Gemma 4 31B, and can a direct exact-shape measurement establish at least 20% potential margin over the current H200 route?

## Work

Rank H200/H100, L40S and RTX 6000 Ada-class 48-GiB hardware, B200, and accessible AMD candidates using committed production rates, capacity, exact Gemma tensors, and current runtime/kernel support. Reuse prior negative venue and consumer evidence; do not repeat a closed launcher failure. Select the shortest checkpoint-free actual-kernel measurement on an authenticated available GPU, comparing only supported quality-plausible representations. Measure exact active text-linear, attention/KV, and tied-head shapes needed to discriminate the candidate, with numerical oracles and price-normalized lower bounds.

Do not claim full-model throughput from component measurements. Return a measured frontier, capacity/accounting model, and at most one next full-endpoint nominee. No broad quality suite; later survivors use GPQA-Diamond and TauBench.

## Limits

60 wall minutes, at most 35 provider minutes and `$1.50`, 4 local CPU-hours, one provider bench, and 3 GiB artifacts. Clean or release through the shared pool contract.
