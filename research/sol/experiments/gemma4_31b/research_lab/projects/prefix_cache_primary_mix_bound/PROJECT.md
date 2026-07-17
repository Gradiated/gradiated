# Primary-mix prefix-cache economic bound

## Question

At the campaign's observed 12.7% cached share of prompt tokens, can exact Gemma 4 31B prefix reuse plausibly reduce sustainable endpoint cost by at least 5%, and what measured H100/L40S/H200 condition would admit one direct prefix-cache on/off arm?

## Why this is independent

The corrected H100 owner still exclusively holds provider mutation while it stages and runs the exact BF16 control. FP8/L40S and BF16/H200 successor packets are already complete. Prefix reuse changes request state and prefill work rather than representation, accelerator, decode proposal, or scheduler overlap, so it is disjoint offline work that can finish without waiting for any paid terminal.

The primary mix is approximately 4,214 prompt and 358 output tokens with 12.7% of prompt tokens reported as cache reads. Prompt tokens are 92.17% of request tokens, so an optimistic token-work ceiling from perfect reuse of that fraction is about 11.70% before cache lookup, residency, eviction, batching, and non-prefill time. Clearing a 5% endpoint gate requires at least `0.05 / 0.127 = 39.37%` of endpoint time to be recoverable cached-prefill work. These are screening calculations, not measured cost savings or evidence that OpenRouter's cache fraction maps directly to a self-hosted prefix distribution.

## Immediate `$0` experiment

Use the exact tokenizer/model/runtime identities in `../exact_geometry_runtime_opportunities/`, the campaign's current OpenRouter mix evidence, current vLLM prefix-cache source/docs, and the shared request/simulation tools. Do not poll the H100 owner, mutate a provider, search GPU prices, or edit another project.

Create a deterministic, content-addressed synthetic request distribution centered on 4,214/358 with exactly stated shared-prefix lengths, reuse frequency, arrival order, and cache churn. Match 12.7% cached prompt tokens in the base scenario and include zero-reuse plus a conservative sensitivity range. Then:

1. Derive exact per-request reusable prefill tokens, hybrid-attention KV bytes, block occupancy, residency, eviction pressure, and the maximum recoverable prefill work for concurrency 1/8/16. Keep vLLM cache-block/source facts, model-geometry derivations, and synthetic assumptions separate.
2. Run the smallest `$0` scheduler/cache simulation or source-exact accounting that distinguishes a real repeated-prefix hit from caller-declared cache credit. Do not claim endpoint throughput from simulated token work.
3. Produce a telemetry-conditioned transfer bound. It must identify the minimum measured prefill wall-time share, cache-hit realization, memory headroom, and queueing behavior needed to clear 5% sustainable cost. It must also state when MTP/async or higher batching makes the cache arm redundant or interaction-sensitive.
4. Bind at most one future direct on/off packet using identical model/runtime/workload/concurrency and raw outputs, changing only current vLLM automatic prefix caching. Require representative raw requests to pass through the actual server/cache metrics boundary; synthetic accounting alone cannot promote it.

## Decision

- Nominate one later direct cache on/off arm only if the conservative bound can exceed 5% and its required telemetry fields are obtainable from the measured endpoint without a new controller lineage.
- Close the line if 12.7% reuse cannot clear 5% under any realistic prefill share, KV residency/eviction makes the base workload infeasible, or current vLLM cannot bind hits to repeated prompt bytes.
- Do not turn missing paid telemetry into another support project. Return a conditional equation keyed to existing result fields.

## Budgets and artifacts

- Provider mutation/spend: prohibited (`$0`).
- Wall clock: 90 minutes.
- Compute: at most 3 local CPU-hours.
- Storage: 2 GiB maximum.
- Artifacts: `PREFIX_WORKLOAD.json`, `PREFIX_BOUND.json`, and `DECISION.md` with at most one `PREFIX_ARM_PACKET.json`.
