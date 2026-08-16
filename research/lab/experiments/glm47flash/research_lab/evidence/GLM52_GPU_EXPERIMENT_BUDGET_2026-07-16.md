# GLM-5.2 GPU experiment budget

Date: 2026-07-16

## Question and decision

Question: based on the GLM-4.7-Flash campaign, how much GPU spend should be authorized to explore GLM-5.2 thoroughly?

Decision: authorize `$6,000` for performance discovery in staged tranches, with an `$8,000` hard ceiling before a separate launch-validation decision. A narrow baseline plus first credible intervention should fit in `$750-$1,200`; a broad software, representation, topology, and hardware search should fit in `$3,600-$6,600`; launch-grade quality, reliability, and sustained-load validation brings the cumulative range to `$7,500-$12,000`. Material post-training or architecture recovery is separate and can add `$10,000-$50,000+`.

## Scope and non-scope

This estimate covers inference experiments on official FP8 and NVIDIA NVFP4 checkpoints, exact workload benchmarking, profiling, serving/runtime changes, kernel and representation experiments, topology search, and comparisons across H200, B200, and MI355X-class nodes. It assumes checkpoint caching and several arms per retained allocation. It does not include salaries, API-agent cost, major training, model distillation, a production fleet, custom hardware, or provider subsidies.

## Evidence and assumptions

- Exact pinned GLM-5.2 manifest: 753,329,940,480 parameters, 78 layers, 256 routed experts with top-8 plus one shared expert.
- Pinned local checkpoint payloads: approximately 761 GB official FP8 and 465 GB NVIDIA NVFP4, versus 20.17 GB for GLM-4.7-Flash AWQ.
- vLLM's current recipe uses one 8xH200 node for FP8 and 8xB200 for full-context FP8; NVIDIA's NVFP4 path targets Blackwell and uses TP8 plus expert parallelism.
- Current experimental node rates from the shared price inventory:
  - 8xH200 preemptible: `$19.60/hour`.
  - 8xB200 preemptible: `$31.60/hour`.
  - 8xMI355X current listing: `$23.60/hour`.
  - Weighted planning rate for experiments: approximately `$24/node-hour`.
- The GLM-4.7 work consumed roughly `$25` across the historical campaign and recent lab allocations. Recent paid projects show about half of create-consuming lineages ending as operational nulls or incomplete science, so the GLM-5.2 estimate includes a 25% execution-loss reserve but assumes the newer retained-session and staging fixes reduce the old failure rate.
- GLM-4.7 cold setup commonly consumed 15-21 minutes for a 20 GB checkpoint. GLM-5.2 must use a provider-side cache or persistent volume; repeatedly staging 465-893 GB while an 8-GPU node is billed is economically unacceptable.

## Budget tiers

| Objective | Node-hours | GPU spend including 25% reserve | What it should establish |
| --- | ---: | ---: | --- |
| Baseline and first intervention | 25-40 | `$750-$1,200` | One valid FP8/NVFP4 endpoint, exact benchmark, profiler trace, and one causal A/B |
| Thorough performance discovery | 120-220 | `$3,600-$6,600` | 20-40 retained sessions or equivalent multi-arm work across precision, runtime, kernels, topology, cache, MTP, DSA, and 2-3 hardware classes |
| Launch-grade validation | 250-400 cumulative | `$7,500-$12,000` | Repeated quality-bearing results, sustained load, failures/recovery, hardware confirmation, and production-shaped economics |
| Material post-training | +400-2,000 or more | `+$10,000-$50,000+` | Recovery training for model surgery; highly dependent on tokens, optimizer state, GPU count, and training method |

At the weighted `$24/node-hour`, a two-hour retained session costs about `$48`; a four-hour session about `$96`. The research factory should place multiple predeclared arms into each session. A campaign of 40 useful retained sessions is therefore about `$1,900` before cold-start, hardware-matrix, failure, and validation overhead, and approximately `$4,000-$6,000` after those realities are included.

## Recommended release gates

1. `$1,000`: obtain one content-addressed checkpoint cache, valid baseline, exact Artificial Analysis geometry, and full profiler trace. Stop if no supported endpoint reaches GPU science.
2. Additional `$2,000`: execute the top ranked software/representation interventions and one alternate hardware baseline. Require at least one valid causal result, positive or negative.
3. Additional `$3,000`: broaden hardware/topology and confirm the best candidate in repeated workloads. This completes the recommended `$6,000` discovery budget.
4. Raise to `$8,000` only when a measured candidate warrants extra confirmation. Authorize launch validation and post-training separately.

## Cost controls that materially change the estimate

- Cache each immutable checkpoint once near the GPUs and retain nodes across arms.
- Use NVFP4/B200 or FP8/H200 as the initial full endpoint; use component microbenchmarks before full reloads.
- Separate hardware placement experiments from scientific intervention experiments.
- Require a tested owner and cleanup watchdog, but do not spend paid-node time on validation that can run locally.
- Treat a pre-GPU failure as an operational result and repair it once through the proven path; do not open chains of paid readiness successors.
- Run quality screening after performance mechanism discovery, then perform full quality only for survivors.

## Falsification and uncertainty

The estimate is too low if checkpoint caches are unavailable, multi-GPU nodes must be purchased on-demand, the supported runtime requires repeated image/kernel builds, or model changes require full-parameter recovery training. It is conservative if a provider offers pre-cached GLM-5.2 images, if most candidate screening runs as component benchmarks within one retained node, or if one hardware family clearly dominates early.

## Sources

| Source | Retrieved | Evidence type | Use |
| --- | --- | --- | --- |
| https://recipes.vllm.ai/zai-org/GLM-5.2 | 2026-07-16 | Official project recipe | Runtime, checkpoint variants, 8-GPU deployment geometries, MTP and cache controls |
| https://huggingface.co/zai-org/GLM-5.2 | 2026-07-16 | Model publisher | Model identity and parameter count |
| https://huggingface.co/nvidia/GLM-5.2-NVFP4 | 2026-07-16 | Quantization publisher | NVFP4 scope and tested Blackwell hardware |
| https://nebius.com/prices | 2026-07-16 | Provider pricing | H200/B200/H100 preemptible and on-demand rates |
| `research/factory/data/gpu_prices.json` | 2026-07-16 | Shared derived inventory | Current experiment and production planning rates |
| `research/lab/experiments/glm-5.2/storage-envelope-v1.json` | 2026-07-16 | Exact plus modeled | Checkpoint sizes, residency, and device-count bounds |
| `research/lab/docs/GLM52_DIRECT_PIVOT_DECISION_2026-07-15.md` | 2026-07-16 | Prior decision brief | GLM-4.7 to GLM-5.2 cost and staging comparison |

