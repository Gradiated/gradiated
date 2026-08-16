# MI210 current-AWQ runtime and economic gate

## Question

Can one commercially obtainable 64-GB AMD MI210 run the exact current GLM-4.7-Flash compressed-tensors AWQ checkpoint on a pinned ROCm serving stack at a sustainable rate that conservatively beats `$0.514/M` on the cache-off 8,192/1,024 background workload?

## Why this matters

MI210 is a materially different cheap-hardware hypothesis from the closed high-memory MI300X/MI325X/MI355X replica screen. The shared accelerator inventory binds one 64-GB `gfx90a` device with 1.6 TB/s HBM2e and model-dependent ROCm support, but it has no joined production price. A single card should avoid the MI3xx multi-replica/topology assumptions and has enough nominal memory for the current AWQ c16/c32 state. Its value depends first on exact W4A16/runtime support and then on a real orderable rate—not on peak math or nominal bandwidth.

## Fixed evidence

- Shared accelerator inventory is current as of `2026-07-15T15:45:00Z`; use its `amd-mi210` record rather than re-researching stable chip facts. The shared price inventory is fresh but has no MI210 join, so one bounded current rate search for this exact accelerator/topology is permitted.
- Exact checkpoint and workload: `/root/.cache/glm47flash-awq-ab31d120` at revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`; cache off, 8,192 input, 1,024 output, complete within 300 seconds.
- Current L40S context: r3 c16 `552.1710554232396` output tok/s at `$1.10/hour`; the authoritative target is `$0.514/M`. Do not transfer this throughput to MI210 by bandwidth ratio alone.
- Consume `../amd_awq_multi_replica_screen/AMD_SCREEN_2026-07-15.json` as a closed MI3xx result. Its generic/partial ROCm compressed-tensors support gap is a prior, not automatically an MI210 conclusion; do not repeat its three-device screen.
- MI210 has 64 GB HBM2e, `gfx90a`, no native FP8, and model-dependent vLLM/SGLang support. The exact checkpoint is W4 group-32 `pack-quantized`; CUDA-only Marlin is not an admissible ROCm path.

## Scope and stop rule

Within 1,200 seconds, 10 GiB RSS, 64 MiB new artifacts, and `$0`, test at most two pinned current ROCm serving stacks, starting with the one most likely to support both `Glm4MoeLiteForCausalLM` and this exact compressed-tensors W4A16 scheme on `gfx90a`. Use source/config/header fixtures only: require architecture registration, exact quantization parsing, a non-CUDA loader and kernel selection, MLA support, 32,768 context, 65,536 batched-token budget, and no dense/dequantized or unsupported fallback. Stop technical work as soon as every candidate fails an exact boundary.

Only if one runtime survives, bind at most two current public MI210 venues/listings and one plausible sustainable production rate. Record exact SKU, memory, topology, region, orderability signal, purchase model, base rate, minimums, CPU/RAM/storage/network, interruption/recovery terms, and retrieval time. Separate experiment venue from production placement. Calculate the required output tok/s at `$0.514/M`, include lifecycle sensitivity, and build a conservative component-wise performance interval from exact runtime geometry and the measured L40S trace without treating summed kernels or HBM ratio as wall-time.

Return exactly one terminal result:

- `NOMINATE_MI210_LOAD`: one exact pinned ROCm path, current orderable measurement venue, sustainable rate, robust memory headroom, and conservative throughput lower bound all clear the target with at least 2% margin; specify one later exact-load c16/c32 falsifier without preparing it;
- `RUNTIME_CLOSE`: the exact checkpoint cannot reach a supported non-fallback MI210 serving path;
- `VENUE_CLOSE`: runtime survives but no orderable/sustainable rate can be bound; or
- `ECONOMIC_CLOSE`: runtime and venue survive but conservative all-in economics miss the target.

Do not invoke or mutate a provider, use credentials, download/convert weights, build a ROCm image or controller, write kernels, train, or claim throughput from vendor peaks. Produce a compact candidate matrix/decision JSON, focused source/config checks, and a concise research-log result.

## Available resources

Use the shared factory inventories/tools, official runtime source already available or shallow-pinned for inspection, the exact checkpoint headers/config, retained L40S artifacts, and `/root/workspace/research/lab/experiments/glm47flash/campaign_100`.
