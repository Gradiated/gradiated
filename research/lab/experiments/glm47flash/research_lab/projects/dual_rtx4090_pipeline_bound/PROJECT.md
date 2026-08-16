# Dual RTX 4090 pipeline-placement bound

## Question

Can two commercially hosted 24-GB RTX 4090s use layer pipeline parallelism to serve the exact current-AWQ c16 background workload below the campaign's `$0.514/M` sustainable-cost target?

## Why it matters

The shared accelerator inventory identifies RTX 4090 as SM89 with 128 SMs, 512 Tensor Cores, 72 MB L2, 24 GB at 1,008 GB/s, broad CUDA/vLLM support, and no NVLink or ECC. One card cannot admit the measured 48-GB-class workload, but two pipeline stages can split roughly 20.17 GB of checkpoint weights and the 7.436-GiB c16 BF16 KV band without a per-layer tensor-parallel all-reduce. At background concurrency, a single stage boundary may be materially cheaper than preserving an interactive single-card topology. This exact two-card pipeline option has not been screened; prior work considered single 48-GB cards and PCIe expert offload instead.

The economics are stringent but plausible: a sustainable all-in pair rate of `$0.80/hour` needs 432.339 output tok/s, while `$1.00/hour` needs 540.424 tok/s. Price alone is not evidence of throughput, and two consumer cards require explicit allowance for power, cooling, interruption, reload, non-ECC reliability, and orchestration.

## Scope

At zero provider spend, bind the shared accelerator inventory, current c16 L40S result, exact checkpoint/tensor placement, MLA KV geometry, pinned vLLM model implementation, and retained request timing. Screen only a two-card RTX 4090 single-node topology. Compare layer pipeline parallelism against tensor parallelism just far enough to choose or kill the pipeline route; do not open a general multi-GPU or consumer-GPU survey.

Produce a conservative component bound for a legal 23/24-serving-layer split, including embeddings/final norm/head imbalance, per-stage weights and KV, vLLM compressed-tensors model support, scheduler/microbatch behavior at c16 or a justified higher background concurrency, activation bytes across the sole boundary during prefill and decode, PCIe/P2P fallback, stage bubbles, clocks/power/cooling, and lifecycle utilization. Fail closed if either stage lacks credible memory headroom or pinned vLLM cannot pipeline this exact model/checkpoint without a new runtime implementation. Do not transfer throughput from peak FLOPS or nominal bandwidth.

RTX 4090 is missing from the otherwise fresh shared price inventory, so refresh only a current two-card same-node benchmark rate and a sustainable production-rate basis at no more than three venues. Separate market/on-demand listings from a 12–24 month all-in rate, and require exact two-card co-location; two unrelated single-card listings do not establish a topology. A current matching quote supersedes the analytical rate allowance. Do not mutate a provider, build an adapter, request credentials, run the model, or broaden into RTX 5090/L4/A10/A40.

## Resources

- Shared accelerator inventory: `/root/workspace/research/factory/data/accelerator_inventory.json` (`nvidia-rtx-4090`).
- Fresh shared price inventory and policy: `/root/workspace/research/factory/data/gpu_prices.json`.
- Exact current control and telemetry: `../nebius_current_awq_c16_direct/`.
- Exact memory evidence: `../current_awq_saturation_bound/` and `../a40_exact_memory_admission/`.
- Checkpoint: `/root/.cache/glm47flash-awq-ab31d120`.
- Runtime sources: `/root/workspace/research/lab/experiments/glm47flash/campaign_100` and the pinned vLLM 0.15.0 image.

## Portfolio-changing result

Nominate at most one later exact two-card measurement only if an orderable same-node venue, conservative per-stage admission, supported exact runtime path, and lower-bound throughput/cost calculation jointly clear `$0.514/M` after lifecycle costs. State the one measurement and minimal topology/GPU/request signals without implementing it. Otherwise close dual-4090 placement and retain A40 as the only conditional cheap-hardware lead. This project has no provider authority or spend.
