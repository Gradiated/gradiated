# GLM-4.7 inference co-optimization

## Objective

Minimize sustainable end-to-end dollars per output token for GLM-4.7 Flash on background-agent workloads while preserving the required model quality. Produce a credible measured result that is cheaper than the best comparable offering from major inference providers. This is the first proof of the broader co-design thesis: model-specific data and experiments can make per-model optimization a worthwhile research and business opportunity. GLM-5.2 follows after a convincing result.

Latency is secondary because these are background agents. It may be traded for materially lower cost through larger batches, longer queues, slower hardware, asynchronous scheduling, or other mechanisms, provided the experiment declares and measures a reasonable background-job completion and reliability envelope. Do not preserve an interactive-serving SLO when it prevents a better background-agent operating point.

Use telemetry and experimental data from GLM-4.7 and its target workload to identify the actual bottlenecks and choose interventions; generic stack improvements without model-scoped evidence are not the objective. The intervention surface includes model architecture and weights, representation and quantization, kernels, runtimes, compilers, scheduling, memory, batching, caching, parallelism, hosting topology, and combinations of these. Commercially available alternate hardware and spot or preemptible capacity are in scope, including software or model work needed to exploit them. Cost claims must include the material effects of utilization, interruption, recovery, retries, storage, transfer, and orchestration. Designing new hardware comes later.

## Research context

The existing evidence, telemetry, code, provider tools, model cache, and historical experiments are under `research/sol/experiments/glm47flash/campaign_100/`. Treat measured results there as evidence, including negative and operational outcomes. The previous coordinator spent too long repairing one deep-observer launch lineage; do not assume that lineage is the best next use of time.

Use available GPU resources efficiently and explore independent opportunities in parallel. Preserve enough trace, quality, SLO, cost, and system data to understand results and choose the next experiment. The point of observability is better research decisions, not instrumentation for its own sake.

Researchers may use the already configured external provider credentials and the existing campaign budget authority. Every paid experiment still needs a bounded deadline and reliable cleanup through the provider tools it uses. Do not expose credentials in logs or repository files.

## Lab files

- `DIRECTOR_LOG.md`: portfolio decisions from the Sol research director.
- `projects/<project>/PROJECT.md`: delegated question and scope.
- `projects/<project>/RESEARCH_LOG.md`: durable researcher progress and evidence.
- `projects/<project>/STATUS.json`: compact project state for scheduling.
- `SUPERVISOR_LOG.md`: research-process bottlenecks and improvements.
- `STATUS.md`: generated current view.
- `runtime/`: harness state, timing events, and Codex traces.
