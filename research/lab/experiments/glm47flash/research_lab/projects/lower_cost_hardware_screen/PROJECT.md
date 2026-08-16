# Lower-cost hardware placement screen

## Question

Does any currently accessible single-GPU placement with enough memory for the GLM-4.7-Flash AWQ background workload have a conservative price/performance break-even that can improve sustainable output-token cost by at least 5% versus V21's L40S control?

## Why it matters

V21's public-AWQ/vLLM/L40S control reaches 355.772 output tok/s at $0.8581222/hour, or $0.670/M output tokens. A 5% improvement requires at most $0.6365/M, and the strong gate is $0.60/M. Batching and prefix reuse are paused on identity failures, while the campaign explicitly permits alternate commercial and preemptible hardware. A cheaper 48+ GiB placement may beat the incumbent even at lower throughput and is independent of quality capture and managed-provider comparison.

## Relevant evidence

- V21's measured throughput, 46,068 MiB device memory, 20.17 GB AWQ weights, 16.82 GiB KV allocation, and $0.8581222/hour VM-plus-disk rate.
- The fixed 8,192-input/1,024-output background workload and allowed latency-for-cost trade.
- Existing Nebius and shared provider placement controls, current read-only catalogs, and official hardware specifications/prices.
- V31/V32 operational costs: any promoted placement must include transfer, storage, interruption, retry, and orchestration sensitivity rather than quote GPU price alone.

## Scope

The zero-cost screen is complete and nominates exactly one RunPod A40. Run one matched V21 background-workload session if and only if a same-turn local preflight reproduces the exact checkpoint, tokenizer/runtime, 8,192/1,024 c8 request geometry, semantic/quality diagnostic, and identity-to-terminal artifact path. Reuse the existing RunPod provider driver under the proven external systemd controller/watchdog boundary. If preflight fails, close without create; do not repair. If the exact A40 create returns no capacity, no pod ID, or an all-in compute rate above $0.50/hour, retain typed provider evidence, verify empty inventory, and close without trying another SKU or placement.

On a created pod, first verify A40 identity, 48 GiB memory, exact model load, and sufficient allocator/KV reserve. Then run one cache-off c8 arm with V21's checkpoint, vLLM/runtime configuration, scheduler budget, seed, and workload fixed. All requests must complete exactly and without truncation inside a 120-second background envelope; retain throughput, TTFT/TPOT, makespan, VRAM/KV, utilization, power, quality/semantic evidence, allocation exposure, interruption/retry state, and terminal cleanup. Promote only if actual all-in steady-state cost is <=$0.6365/M and sustained throughput clears the actual-rate break-even; report the $0.60/M strong gate separately.

## Available resources

Use retained V21 telemetry/manifests, the existing RunPod driver and artifact controls, shared factory tools, and the external controller/watchdog pattern. This project is the sole provider owner for one A40 attempt under a $0.65 all-in cap and 3,600-second absolute timeout. RunPod inventory was empty at director handoff. Arm the watchdog before create, retain bounded provider diagnostics, and require terminal pod deletion plus fresh zero inventory. No other project may mutate any provider concurrently.

## Portfolio-changing result

An exact A40 result at or below $0.6365/M would become a quality-conditional cost candidate; <=$0.60/M clears the strong gate. This project's RunPod path closed before create because exact catalog/capacity access failed. That provider-path result does not falsify A40 capacity or performance at another venue; any venue search belongs to a separately scoped project. No second SKU, placement, repair, or preparation turn is authorized here.
