# RTX 6000 Ada c16 transfer bound

## Question

Can the exact current-AWQ c16 workload retain enough L40S throughput on an RTX 6000 Ada to beat the campaign's `$0.514/M` committed-cost discovery target at a real sustainable all-in rate?

## Why it matters

The refreshed accelerator inventory identifies RTX 6000 Ada as the closest hardware counterfactual to L40S: both are SM89 with 142 SMs, 568 Tensor Cores, 96 MB L2, 48 GB ECC GDDR6, the same 99 KiB block limit, PCIe Gen4 x16, and broad CUDA/vLLM support. RTX 6000 Ada reports 960 GB/s bandwidth and 300 W versus L40S's 864 GB/s and 350 W. The earlier hardware screen rejected its `$0.77/hour` RunPod listing against a 355.772-tok/s historical control; the measured current c16 control is now 535.286 tok/s, making the same rate require about 416.13 tok/s, or only 77.74% retained throughput. That denominator change reopens the placement scientifically.

## Scope

At zero provider spend, bind the shared accelerator inventory, fresh L40S planning price, current c16 control, exact checkpoint/memory footprint, retained GPU telemetry and trace families, and the prior `$0.77/hour` venue evidence. Produce a conservative component-wise transfer interval that accounts for identical SM89 kernel legality, SM/Tensor-Core count, L2, memory capacity, bandwidth, clocks/power/cooling, driver/runtime support, and setup/lifecycle utilization. Do not transfer throughput from peak FLOPS alone. Determine the lowest retained-throughput fraction and all-in hourly-rate ceiling that meet `$0.514/M`, the Artificial Analysis-normalized campaign comparator, and sensitivity at the planning range.

Because RTX 6000 Ada is absent from the shared price inventory, refresh only this missing accelerator's current sustainable rate and orderability at at most three venues; do not repeat general GPU-price research. Separate benchmark venue from production placement and label on-demand/market listings rather than treating them as committed production COGS. Reuse existing RunPod and alternate-venue failures as provider-path evidence; an inaccessible venue does not kill the hardware mechanism.

Do not build a provider adapter, request credentials, mutate a provider, run the model, or reopen A40/AMD projects. Name at most one later exact c16 measurement venue and the minimal on-device signals that would collapse the transfer interval.

## Resources

- Shared accelerator inventory: `/root/workspace/research/factory/data/accelerator_inventory.json`.
- Shared price inventory: `/root/workspace/research/factory/data/gpu_prices.json`.
- Measured L40S c16 control and telemetry: `../nebius_current_awq_c16_direct/`.
- Prior hardware screens: `../lower_cost_hardware_screen/`, `../a40_archived_trace_transfer_bound/`, and `../a40_alternate_venue_verification/`.
- Exact checkpoint/memory evidence: `../a40_exact_memory_admission/` and `../current_awq_saturation_bound/`.

## Portfolio-changing result

Nominate one RTX 6000 Ada measurement only if a current real venue/rate plus the conservative transfer interval can meet `$0.514/M` after material lifecycle costs. Otherwise close the placement and retain A40 as the only conditional cheap-hardware lead. This project has no provider authority or spend.
