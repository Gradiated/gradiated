# GLM-4.7 inference co-optimization

## Objective

Minimize sustainable end-to-end dollars per output token for GLM-4.7 Flash on background-agent workloads while preserving the required model quality. Produce a credible measured result that is cheaper than the best comparable offering from major inference providers. This is the first proof of the broader co-design thesis: model-specific data and experiments can make per-model optimization a worthwhile research and business opportunity. GLM-5.2 follows after a convincing result.

Latency is secondary because these are background agents. It may be traded for materially lower cost through larger batches, longer queues, slower hardware, asynchronous scheduling, or other mechanisms, provided the experiment declares and measures a reasonable background-job completion and reliability envelope. Do not preserve an interactive-serving SLO when it prevents a better background-agent operating point.

Use telemetry and experimental data from GLM-4.7 and its target workload to identify the actual bottlenecks and choose interventions; generic stack improvements without model-scoped evidence are not the objective. The intervention surface includes model architecture and weights, representation and quantization, kernels, runtimes, compilers, scheduling, memory, batching, caching, parallelism, hosting topology, and combinations of these. Commercially available alternate hardware and spot or preemptible capacity are in scope, including software or model work needed to exploit them. Cost claims must include the material effects of utilization, interruption, recovery, retries, storage, transfer, and orchestration. Designing new hardware comes later.

## Discovery sequence

The current phase is architecture and cost discovery, not final quality certification. Start from first principles: the exact checkpoint architecture, tensor geometry, routing behavior, request workload, c16 telemetry, kernel shapes, memory traffic, and the capabilities and economics of each candidate chip. Derive interventions from the observed model/chip mismatch rather than from a generic optimization checklist.

### Current performance-discovery priority — 2026-07-16

Pause teacher/student distillation, recovery training, broad quality work, and their provider spend. Preserve existing recovery artifacts for later, but use current research capacity to explore materially different performance mechanisms. The immediate anchor is c32 on the full 47-layer current-AWQ model, or the smallest practical divergence from it. Separate exact-model interventions such as KV representation, runtime memory tax, graph/capture geometry, allocator behavior, scheduling, and kernels from near-original model changes such as modest MLA-rank/state reduction or selective residual representation. Measure cost mechanisms now; defer training and full quality adjudication until the portfolio contains several credible performance candidates.

For the current full 47-layer AWQ identity, retained c16 telemetry predicts c32 at 46,875.7 MiB against a 46,068 MiB device envelope: an approximately 807.7 MiB nominal deficit before fragmentation. Treat that small but real deficit as the first design constraint. A c32 candidate must do more than fit: it must preserve complete background requests and improve output-token economics over the measured 535.286 tok/s c16 point. Prefer one retained L40S session that measures the most informative exact-model mechanism while an independent researcher derives and implements a minimal model/chip co-design candidate.

Minor model and weight changes are explicitly in scope. Researchers may assume that a promising structural change can receive modest post-training, distillation, or recovery training later. They should first measure or tightly bound its cost mechanism with an executable proxy even when that proxy is not quality-preserving: for example changing routed experts per token, conditionally executing the shared expert, reducing selected expert widths or layers, changing MLA ranks, factorizing the output head, adding an early-exit or draft head, or making precision and sparsity layer-specific. Label these as architecture-cost evidence, not deployable model results.

Do not make a full BF16 reference capture, broad evaluation suite, matched provider-quality proof, or H100 quality session a prerequisite for architecture exploration. Cheap sanity checks may reject a broken implementation, but candidate discovery is ranked by measured dollars-per-token potential, mechanism clarity, chip fit, and plausible recoverability with post-training. Run full quality and recovery work only after one or more changes demonstrate enough cost reduction to justify it. Quality remains mandatory before a production or provider-beating claim; it is deferred, not waived.

For every model intervention, explain why it should help on the target chip. Account for memory capacity and bandwidth, supported low-precision kernels, tensor-core geometry, launch and routing overhead, interconnect/topology, power, and committed or owned production cost. A change that saves theoretical FLOPs but does not reduce serving wall time or permit cheaper placement is not progress.

### Current L40S focus

The current chip is the L40S, not an abstract CUDA GPU. Use [`hardware/L40S.md`](hardware/L40S.md) as the shared resource model and improve it when an experiment resolves an unknown. Its Ada SM89 limits are part of the research surface: 142 SMs, 48 resident warps and 64K 32-bit registers per SM, 128 KB unified L1/shared storage with at most 100 KB shared per SM and 99 KB per block, 96 MB L2, 48 GB GDDR6 at 864 GB/s, fourth-generation Tensor Cores with FP8 support, PCIe Gen4 x16, and no NVLink or MIG.

The director and researchers should connect GLM's exact shapes to those resources. In particular, investigate whether 64-way sparse expert routing leaves too little work per expert to occupy 142 SMs; whether fewer or merged experts improve grouped-GEMM shape as well as model size; whether quantizing BF16 residual components or reducing KV/MLA state unlocks c32 and greater weight reuse; whether ranks and widths can be changed to fit efficient tensor-core and shared-memory tiles; and whether supported FP8 or 2:4 structure beats the current mixed W4/BF16 path for specific components. The prior grouped-MLA `BLOCK_N=64`, two-stage attempt required 159,744 bytes of shared memory against a 101,376-byte per-block limit. Treat that as model/chip evidence: a smaller latent/value geometry might make the better tile legal while also reducing KV traffic and capacity. Measure the causal chain before investing in recovery training.

### Architecture/kernel co-design priority — user direction, 2026-07-16

The depth-42 and depth-43 results are useful economic bounds, not the desired research product. Do not open another layer-removal, broad expert-width reduction, or parameter-count proxy. Prioritize the full 47-layer model and small changes whose benefit comes from better realization on L40S rather than approximately proportional deletion of parameters.

The immediate portfolio order is:

1. Quantize only the tile-legal BF16 output head and shared-expert linears to the checkpoint's existing group-32 W4 representation. Their measured combined saving is about `1,029.97 MiB`, larger than the full-model c32 nominal deficit, while leaving layer 0 and every routed expert unchanged. Implement the missing output-head/shared-expert binding or a narrow kernel adapter and measure full-model c32; do not reject this combined route because the unrelated layer-0 `[576,2048]` tensor is not Marlin-tile legal.
2. Implement an SM89 FP8-MLA KV path as a custom-kernel/runtime opportunity. The stock vLLM backend incompatibility is evidence of a software gap, not evidence that FP8 KV is a bad L40S mechanism. First prove the exact decode shape and numerical sanity in a bounded component benchmark, then integrate only if it reduces bytes/time and admits c32.
3. Attack the measured 64-expert/top-4 fragmentation directly. At c16/c32 the uniform average is only about one/two routed rows per expert against 142 SMs. Compare an exact-model persistent/fused routing-plus-grouped-W4 executor with the stock path, preserving weights, routing, top-k, and shared expert. Measure active-expert `M`, launch count, grid occupancy, bytes, and endpoint time; high aggregate GPU utilization is not proof the SMs are doing useful tensor work.
4. Explore a small MoE architecture change based on the existing shared/sparse split: represent routed experts as a shared or clustered trunk plus low-rank expert-specific deltas, preserving 64 logical experts and top-4 routing. First measure weight-space approximation and exact-shape execution potential; the intended gain is a large well-filled dense/shared GEMM plus small sparse residuals, not indiscriminate expert deletion.
5. Keep modest MLA-rank reductions such as 480/448 as secondary candidates only when they are paired with a concrete SM89 kernel/c32 mechanism. A memory projection alone or an optimistic linear transfer bound is not a reason to close or promote them.

Use the depth-43 c32 endpoint as an exact per-layer geometry testbed when useful, but make the full-47 c16/c32 endpoint the decision. The L40S already shows about 100% reported utilization and roughly `323–327 W` during c32; the objective is not to manufacture 350 W draw. Improve useful Tensor Core work, effective memory bandwidth, occupancy, and output tokens per joule/dollar. Unsupported stock loader or runtime paths should trigger one bounded implementation attempt when a narrow adapter or custom kernel is the scientific intervention. Do not spend turns repeatedly proving that stock vLLM lacks the feature.

## Research context

The existing evidence, telemetry, code, provider tools, model cache, and historical experiments are under `research/sol/experiments/glm47flash/campaign_100/`. Treat measured results there as evidence, including negative and operational outcomes. The previous coordinator spent too long repairing one deep-observer launch lineage; do not assume that lineage is the best next use of time.

Use available GPU resources efficiently and explore independent opportunities in parallel. Preserve enough trace, quality, SLO, cost, and system data to understand results and choose the next experiment. The point of observability is better research decisions, not instrumentation for its own sake.

Researchers may use the already configured external provider credentials and the existing campaign budget authority. Every paid experiment still needs a bounded deadline and reliable cleanup through the provider tools it uses. Do not expose credentials in logs or repository files.

Nebius is an experimental venue, not the production deployment assumption or the boundary of the opportunity search. Use current online evidence for this exact model—including reproducible serving benchmarks, runtime and quantization results, hardware specifications, provider catalogs, spot/preemptible markets, reserved capacity, and owned-hardware economics—to generate and rank candidates. Search across providers and hardware before spending, and refresh prices because marketplace availability and rates change. Treat online results as priors unless model, representation, runtime, workload, concurrency, quality, and cost scope match; use them to select cheap falsifiers and experiments, not as substitutes for our measured result. Rank production candidates by sustainable all-in dollars per output token, while choosing the safest convenient provider for experiments independently. A production provider's inaccessible catalog or control plane does not by itself kill the hardware or software candidate: benchmark the same mechanism wherever it is safely available (including Nebius), then separately verify that the proposed production placement and all-in rate are real before making the economic claim.

Use the shared [`research/factory/data/gpu_prices.json`](../../../../factory/data/gpu_prices.json) inventory for accelerator economics. Its headline production rate represents a reasonable 12–24 month, 8–64 GPU committed market rate—not on-demand, preemptible, promotional, or a rock-bottom hyperscale floor. Use that planning rate for production `$ / token`, its range for sensitivity, and the actual provider-metered rate only for experiment spend. The director owns one weekly refresh when stale; ordinary projects do not repeat GPU-price searches.

## External provider comparator

Artificial Analysis is the campaign's primary external market scoreboard. Match the exact model and reasoning mode before comparing anything:

- The current performance harness sends raw completions with thinking disabled, so its primary comparator is [GLM-4.7-Flash (Non-reasoning)](https://artificialanalysis.ai/models/glm-4-7-flash-non-reasoning/providers). Retrieved 2026-07-15, Amazon and Novita both list `$0.10/M` blended, `$0.07/M` input, and `$0.40/M` output; their P50 output speeds are about `206.4` and `92.1` tokens/s respectively.
- Use [GLM-4.7-Flash (Reasoning)](https://artificialanalysis.ai/models/glm-4-7-flash/providers) only for a thinking-enabled endpoint. Retrieved 2026-07-15, DeepInfra is cheapest at `$0.06/M` blended and Amazon is fastest at about `181.2` tokens/s. Do not merge its DeepInfra price with the non-reasoning provider set.
- The full [GLM-4.7](https://artificialanalysis.ai/models/glm-4-7/providers) pages describe a different, much larger model and are not campaign comparators.

Refresh these pages before a market claim because prices, providers, and rolling measurements change. Artificial Analysis's displayed blend is 7 cache-hit input tokens : 2 uncached input tokens : 1 output token. Never compare that headline directly with campaign `$ / M output` COGS. Report all four views: cache/input/output retail components, the Artificial Analysis 7:2:1 blend, retail cost for the campaign's actual token mix, and sustainable all-in self-hosted COGS for that same mix. Include cache write/storage, utilization, interruption, reload, retries, storage, transfer, orchestration, and headroom when material.

For speed comparability, follow the [published performance methodology](https://artificialanalysis.ai/methodology/performance-benchmarking): use diverse prompts, streaming, one request at a time, about 10K input tokens, at least 1,500 answer tokens, OpenAI `o200k_base` token counts for speed, post-first-token output speed, TTFT, and repeated measurements summarized as a median. Artificial Analysis generates a unique prompt for every live run, so its exact rolling prompt set is not public; call our result methodology-matched, not an exact replay. Keep aggregate throughput separate. For a public, reproducible saturation comparison, also implement the [Artificial Analysis System Load Test](https://artificialanalysis.ai/methodology/system-load-test): 1K input/1K output, streaming, three-minute phases at concurrency 1/2/4/8/16/32/64 and onward until throughput plateaus.

Before graduating this prototype campaign to GLM-5.2, require: (1) one quality-eligible GLM-4.7-Flash result, (2) one methodology-matched Artificial Analysis performance/cost report, and (3) one retained-allocation session that runs several scientific arms with complete telemetry and cleanup. Then move to GLM-5.2; do not wait for production hardening or continue GLM-4.7 merely because more optimizations exist.

Use the [Wafer AI full-stack deep dive](../../../docs/WAFER_AI_FULL_STACK_DEEP_DIVE_2026-07-15.md) as a model-specific research prior. For GLM-4.7 Flash, rank checkpoint/quality, engine, decode, cache, topology, kernel, hardware, and economic interactions from telemetry rather than opening one project per layer or assuming AMD wins. Wafer's GLM-5.2 MI355X path is a direct competitor blueprint for the follow-on model, not transferable evidence for this smaller checkpoint.

## Lab files

- `DIRECTOR_LOG.md`: portfolio decisions from the Sol research director.
- `projects/<project>/PROJECT.md`: delegated question and scope.
- `projects/<project>/RESEARCH_LOG.md`: durable researcher progress and evidence.
- `projects/<project>/STATUS.json`: compact project state for scheduling.
- `SUPERVISOR_LOG.md`: research-process bottlenecks and improvements.
- `STATUS.md`: generated current view.
- `runtime/`: harness state, timing events, and Codex traces.
