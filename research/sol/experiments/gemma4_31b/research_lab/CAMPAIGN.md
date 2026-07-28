# Gemma 4 31B inference co-optimization

## Objective

Minimize sustainable end-to-end serving cost for the exact instruction checkpoint `google/gemma-4-31B-it` at revision `b9ea41a2887d8607f594846523f94c6cc75ac8a4`, initially in its default non-reasoning text mode. The commercial goal is to win paid OpenRouter traffic while remaining a credible Gemma 4 31B endpoint. Latency is secondary for background-agent traffic; trade it for lower cost when completion time and reliability remain usable.

This is a fresh campaign. Do not inherit GLM-4.7 model identity, target prices, workload assumptions, admission gates, project backlog, or conclusions. Reuse generic provider, profiling, measurement, and cleanup mechanics when they save time.

Research progress means measured or tightly bounded movement in cost, throughput, capacity, or a causal bottleneck. Prefer a useful experiment over more process. One bounded compatibility check is enough before changing approach. Broad quality evaluation is deferred until a performance candidate deserves it, but no candidate becomes production-eligible without quality and feature validation.

## Current portfolio priority — 2026-07-17

The stock BF16 H200 floor has too little margin over the Artificial Analysis price frontier to be the default optimization path. Prioritize hardware placement, supported lower-precision execution, and kernel changes that can create a material cost margin. Keep one direct GPU lane measuring an actual runtime consumer and one independent lane comparing hardware/kernel opportunities from exact Gemma geometry and measured telemetry. Current leading branches are L40S online FP8 with a same-session W4 Marlin comparison, materially cheaper compatible 48-GiB hardware if that mechanism passes, and H200/H100/B200/AMD alternatives only where exact runtime support and price-normalized throughput justify a direct test.

Prefer checkpoint-free exact-shape kernel falsifiers before another full checkpoint transfer. Focus custom-kernel work on measured or compulsory costs: prefill linears, paged hybrid local/global attention, KV reads/writes, precision conversion, normalization/activation fusion, and scheduler-visible batching. Use roughly 5% as a threshold for opening or extending a standalone research line, not as a reason to discard a measured improvement. Do not spend another allocation merely reproducing a known launcher failure or measuring a component already shown to be off the economic critical path.

## Exploration-first phase — 2026-07-18

Map and push the performance opportunity space before running broad quality evaluation. Keep independent work active across measured bottleneck profiling, kernels/runtime/scheduling, precision and hardware placement, and small model/chip co-design. A candidate-specific quality investigation must not become the sole active portfolio while credible performance hypotheses remain unexplored.

Prefer interventions that are plausibly quality-preserving or recoverable with modest post-training: exact serving and kernel changes, batching and cache policy, hardware placement, supported FP8/W4 representations, KV precision, and small architecture changes tied to a measured hardware bottleneck. Do not pursue blunt layer, expert, width, or parameter deletion whose expected speedup simply tracks removed model capacity. During exploration, use only cheap output/coherence and numerical sanity checks needed to reject obviously broken implementations; defer broad model-quality runs until a short performance frontier exists.

OpenRouter promotion later requires benchmark-specific capability evidence, not generic code holdouts. Performance survivors must eventually be evaluated on GPQA-Diamond and TauBench with the exact served model, tool-call/request path, and production representation. Rank candidates by cost improvement first, but retain only changes with a credible route to ranking sufficiently well on those benchmarks and preserving required OpenRouter behavior.

## Kernel and cost-frontier phase — 2026-07-20

Reopen the campaign around the remaining price-normalized performance gap. The retained exact-mix H200 endpoint is approximately `0.91946 s/request` and `$0.1816/M total tokens` at the current committed-price planning assumption, versus an Artificial Analysis frontier target near `$0.14/M`. Treat this as a working target to refresh before a market claim: closing it requires roughly 23% lower cost, or 30% more throughput at the same hourly price.

Keep at least two materially independent performance lanes active while budget permits, with at least one lane running direct endpoint measurements on a GPU. Prefer reusing and patching a warm machine. The highest-priority opportunity classes are:

1. **Deployable low-precision linear execution.** Turn the already observed FP8/W4 component potential into an exact Gemma 4 endpoint. A framework exporter or serialization failure does not falsify the mechanism: use a custom loader, in-memory conversion, alternate consumer, or a small model-specific execution path and measure the actual endpoint. Focus on fused dequantization plus GEMM and avoid materializing converted weights or activations through HBM when a fused epilogue can avoid it.
2. **Price-normalized hardware placement.** Test the smallest plausible production endpoint on H100 and L40S-class hardware with W4/FP8 representations, and compare measured tokens per dollar with H200. Absolute speed is secondary. Use the shared committed-price inventory, include memory fit and saturation geometry, and require an end-to-end result rather than extrapolating from isolated GEMMs.
3. **Residual hot-kernel optimization.** Profile the canonical endpoint just deeply enough to attribute wall time and bytes to the top kernel families, then immediately build and test the highest-value exact-shape change. Promising boundaries include QKV projection epilogues fused with Q/K normalization and RoPE, FP8 KV conversion/write, launch elimination, persistent execution, and local-attention dataflow. Do not duplicate stock fused GQA or optimize an operation that telemetry shows is immaterial.

Stack simple, compatible measured gains. Retain a clean improvement without demanding a full quality campaign, but reject changes that are obviously destructive. There is no fixed minimum percentage for a useful intermediate result: inexpensive endpoint measurements should run when a component has a credible positive whole-request bound, because sub-3% gains can compound. The campaign objective remains the full frontier gap. Do not terminalize merely because the previous shortlist was exhausted while a materially distinct precision, kernel, or hardware route remains untested and spend authority remains. Generate the next hypothesis from the latest bottleneck telemetry.

Avoid generic flag sweeps, repeated environment verification, broad quality evaluation, and architecture training in this phase. Profiling and setup are means to an experiment and should not become projects of their own.

## Residual frontier phase — 2026-07-20

The user explicitly reopens the campaign after the v0.5.13 dynamic-FP8 plus QKV result. The exact c32 endpoint is now `0.6928421805 s/request`, approximately 25.3% faster than the scope-matched `0.9280403085` BF16 control. At the committed H200 planning rate it is about `$0.136807/M` at theoretical full utilization but `$0.152008/M` at 90% utilization. The next sustainable frontier target is therefore at most approximately `0.6381 s/request` on H200 at 90%, another 7.9% service-time reduction, or an equivalent price-normalized result on another accelerator.

Do not transfer the old BF16 critical-path attribution to this new FP8 runtime. Current coarse telemetry only establishes saturation: the QKV candidate averaged 97.3% GPU utilization with 99% median, averaged 564 W with 604 W median, and held about 123 GB of HBM; c48 and c64 were already measured negative versus c32. The next H200 profile must attribute non-overlapping wall time on the exact v0.5.13 FP8+QKV endpoint across prefill/decode, FP8 linear families, attention/KV, normalization/activation, cache conversion/write, launch and scheduler gaps. Use Nsight Systems or equivalent first, then collect only the minimum Nsight Compute counters on the top one or two kernels needed to distinguish tensor-core compute, HBM/L2 traffic, occupancy/register/shared-memory pressure, underfilled grids, and synchronization. Layer/NVTX ranges are useful only when they make that attribution clearer. In the same scientific project, immediately implement and measure one source-justified change against the hottest boundary; profiling alone is not a terminal research result.

Keep at least one independent direct economic falsifier active while profiling proceeds. The leading placement is the exact v0.5.13 dynamic-FP8 endpoint on H100 using the same checkpoint, c32 workload, KV precision, QKV intervention, and current committed-price inventory. At `$2.80/GPU-hour`, it reaches the `$0.14/M` target at 90% utilization if service time is approximately `0.741 s/request` or better, so it can be modestly slower than H200 and still win. This is materially different from the closed older H100 W4/vLLM route and requires a fresh matched endpoint result.

The current-runtime MTP eager-buffer shape failure is also an admissible software hypothesis if source inspection identifies one bounded semantic repair. Measure one same-session FP8 control/MTP pair with acceptance telemetry after the repair; do not replay the failed arm unchanged or turn compatibility investigation into a project chain.

Continue stacking simple positive kernel changes. Prefer fused FP8 GEMM epilogues, activation/normalization fusion, attention/KV dataflow, launch elimination, or persistent execution only when the new profile assigns them enough non-overlapping wall relevance. Do not close the campaign while these materially distinct measured routes remain and spend authority is available. Broad quality replay remains unnecessary until another performance or placement survivor changes the production candidate.

## Incremental-wins policy

Keep reproducible improvements when they are operationally simple, compatible with the intended serving path, and have no observed material downside, even when they fall below a project's promotion threshold. Fold them into the working baseline so independent gains can compound. A small gain does not justify prolonged tuning by itself: record it, retain it, and move to the next bottleneck. Drop it only when a later interaction, reliability result, quality result, or all-in cost measurement shows that it is no longer beneficial. In particular, retain the measured SGLang dynamic-chunking configuration (`--enable-dynamic-chunking --chunked-prefill-size 2048`) for compatible exact-mix c32 follow-up comparisons: it improved service time by 4.05% with matching token/cache accounting and valid outputs, while not warranting a chunk-size sweep.

## Market scorecard

Use current external data and refresh it before any market claim. The launch-mode references at campaign start on 2026-07-16 are:

- Artificial Analysis: exact [Gemma 4 31B (Non-reasoning)](https://artificialanalysis.ai/models/gemma-4-31b-non-reasoning/providers) page. Its current cheapest displayed blend is about `$0.14/M`; its standard performance view uses about 10K input tokens and single-stream generation. Keep this methodology-matched view separate from aggregate throughput.
- OpenRouter model ID: `google/gemma-4-31b-it`, whose default reasoning mode is disabled. The current credible low-price frontier is approximately `$0.12/M` fresh input, `$0.09/M` cache read, and `$0.35/M` output. Compare components, not only a blended headline.
- Recent OpenRouter traffic is prompt-heavy: approximately 4,214 prompt and 358 output tokens per request, an 11.76:1 prompt/output ratio, with cache reads around 12.7% of prompt tokens. Treat these as a starting distribution, not an immutable synthetic benchmark.

Report at least fresh-input, cache-read, and output economics separately; then report retail and sustainable self-hosted cost for the measured workload mix. Use actual provider rates for experiment spend and the shared committed-production rates in `research/factory/data/gpu_prices.json` for production comparisons. Include utilization, queueing, replicas/headroom, failures/reloads, storage, orchestration, and other material costs.

## First research cycle

Start both lanes immediately and let evidence change the portfolio:

1. **Measured baseline:** get the exact pinned model serving on one suitable GPU placement and measure complete requests, prompt/decode throughput, TTFT, memory, power, utilization, queueing, failures, and experiment cost. Choose the fastest credible route to evidence: BF16 on enough memory or a well-supported quantized representation. A 30.7B dense checkpoint is roughly 61.4 GB in BF16 before runtime state, so a 48 GB placement requires a lower-precision representation; do not repeatedly rediscover that constraint. Use a bounded initial run and always clean up provider resources.
2. **Opportunity derivation:** inspect the exact architecture, tensor shapes, runtime support, and target-chip hierarchy while the baseline runs. Rank interventions by expected all-in cost reduction and cheapest falsifier. Gemma's hybrid five-local/one-global attention, 1,024-token local window, unified global K/V, very large vocabulary/output head, precision choices, batching/cache geometry, and possible MTP path are starting hypotheses—not a required checklist.

The primary workload is a reproducible distribution around the OpenRouter token mix under background concurrency and batching. Also preserve an Artificial Analysis methodology-matched 10K-input single-stream view. Measure saturation rather than assuming interactive settings are economical.

Use text-only, non-reasoning traffic for initial cost discovery. Vision/video and reasoning are separate product modes; add them before claiming full OpenRouter feature eligibility, not before the first useful performance experiments.

## Autonomy, spend, and stopping

Experiment spend from `2026-07-17T21:59:00Z` onward has a hard cumulative authorization cap of `$400`: the original `$100`, an additional `$100` on `2026-07-19`, an additional `$50` on `2026-07-24`, an additional `$50` authorized by the user on `2026-07-25`, an additional `$50` authorized on `2026-07-26`, and an additional `$50` authorized on `2026-07-28`. The harness durably reserves each paid project's full authorized maximum before scheduling it, never releases that reservation implicitly, and refuses projects whose combined reservations would exceed the cap. There is no separate concurrency cap on paid GPU experiments: the director may run independent allocations concurrently up to the harness's five-researcher limit while staying within the shared `$400` authority. Each allocation needs its own owner, declared deadline, actual metered rate, durable telemetry, and reliable cleanup. A failed placement or runtime route is one branch result: switch hardware, provider, runtime, representation, or experiment geometry rather than spending cycles polishing the same failure.

The director should keep a small portfolio of independent, falsifiable projects and retire weak lines quickly. Researchers use their judgment, record concise decision-relevant evidence, and continue until the project decision is supported or its stated budget expires. The supervisor improves research cadence only when traces show a real bottleneck; it must not add ritual or deterministic gates.

## 2026-07-22 residual-frontier reopening

The user explicitly reopens performance exploration because the retained H200 stack remains behind the sustainable provider frontier. The retained dynamic-FP8 + QKV + deferred-local-KV endpoint is approximately `0.689220 s/request`; the `0.6381105231 s/request` H200 ceiling therefore requires about another 7.42% service-time reduction. Do not treat the July 20 exhausted shortlist as campaign closure.

Run three materially different lanes: (1) a register-pressure redesign of the exact global head-512 attention kernel that partitions the value accumulator or otherwise trades cheap recomputation/L2 traffic for materially higher SM residency, (2) fusion of dynamic-FP8 quantization with adjacent normalization/activation/residual dataflow, and (3) a current full-stack runtime comparison that can replace pinned v0.5.13 when exact Gemma 4 hybrid-attention and FP8 support have improved. These are new mechanisms, not permission to replay BLOCK_M=16, the rejected gate/up tile, old runtime startup failures, MTP without accepted-draft proof, or broad flag sweeps.

Prefer one or two retained H200 benches shared across compatible experiments once their reservations are durable. A simple stable gain should be stacked even below 5%; the full campaign decision still depends on closing the price-normalized endpoint gap. Keep broad quality replay deferred until a performance survivor changes the production stack, while rejecting obviously incoherent outputs immediately.

The campaign is perpetual until the user explicitly pauses it or authorized spend is exhausted. Negative experiments close only their measured hypothesis. The director must admit a materially different replacement before the final active project terminates; “portfolio exhausted,” “shortlist exhausted,” and an empty quiescent lab are invalid outcomes while authority remains. Change mechanism, runtime, representation, hardware, serving topology, or model intervention and continue producing GPU evidence.

## 2026-07-26 — seed-frontier execution directive

The immediate company objective is a defensible cheapest-provider result that
can support a seed round. Optimize for a sustainable, quality-qualified,
committed-capacity cost of at most approximately `$0.11/M` total tokens on the
campaign workload, with enough margin below the current Artificial Analysis
frontier to absorb availability, orchestration, storage, and serving overhead.
Spot economics are useful supplementary evidence but are not the primary
fundraising claim.

Preserve the live H100 native BF16-versus-E4M3 paged-KV experiment and repair
its unconsumed integration boundary in place. Treat it as a stackable kernel
mechanism rather than the sole route to the seed result. In parallel, maintain
a compact portfolio of independent high-upside work:

1. **Price-normalized accelerator placement.** Run the existing exact-shape
   MI355X falsifier first when an authenticated MI355X bench becomes available;
   run the source-complete B200 FP8 falsifier when an authenticated B200 bench
   is available. Do not wait idly for either venue: preserve their bound
   runners and continue the software lanes below.
2. **Lossless Gemma-specific speculation.** Reopen the strongest DFlash or
   equivalent parallel-draft mechanism at the first-divergent target/accepted
   token and KV-commit boundary. Establish exact target semantics, then measure
   hardware-aware adaptive draft depth on the real c32 workload. If the
   existing drafter cannot produce enough accepted work, design a small
   Gemma-specific causal one-forward parallel draft head as the next
   intervention rather than extending verifier plumbing indefinitely.
3. **Packed Hopper-native target verification.** Use `$kernel-research` to
   build an exact-consumer M384 verifier/attention kernel for Gemma's local
   d256/window-1024 and global d512 geometry. Explore packed heterogeneous
   request work, TMA producer/consumer specialization, partitioned exact
   online-softmax reduction, and direct FP8 paged-KV consumption. Measure
   against the strongest current exact-shape consumer and proceed quickly to a
   matched endpoint when the component is positive.
4. **Cross-operator target executor.** Independently test a persistent or
   task-graph execution boundary spanning the recurring RMSNorm, dynamic-FP8
   quantization, GEMM, attention/MLP, residual, target-head, and acceptance
   work. Bind it to measured target-verification telemetry and require one
   working exact-shape or hot-block implementation; do not create a generic
   executor-design or literature project.

Normally keep several of these independent lanes advancing while researcher
capacity and budget permit, without filling slots with documentation,
readiness, or duplicate repair projects. A long integration repair on one GPU
must not serialize source/kernel implementation that can proceed offline.

The promotion sequence for a survivor is: exact component or mechanism result,
scope-matched full endpoint, sustainable load/cost measurement, then
GPQA-Diamond, TauBench, tool-path, and reliability validation. Finish with an
Artificial Analysis methodology-matched 10K-input view and the campaign
OpenRouter traffic mix. Do not call an analytical hardware screen, component
speedup, spot-only estimate, or quality-unsafe model proxy the cheapest
provider result.

## 2026-07-23 — deepen positive routes and remove arbitrary endpoint gates

The user explicitly directs the lab to pursue and measure incremental gains. Do not use a fixed 3% promotion gate. The measured 16,384-wide MLP proxy has a positive `2.6481%` conservative whole-request bound and an already-implemented endpoint path, so run its unstarted quality-unsafe c32 endpoint without replaying the settled component. The contiguous local-KV component was bit-identical and had a positive `24.8346%` local-consumer reduction; its first multi-token endpoint failure therefore warrants one focused integration repair rather than abandonment. Test the request-slot-to-ring-row mapping, padded graph rows, dynamic request reuse, sequence positions, and prefix ownership, then run the smallest multi-token discriminator and a c32 endpoint if semantics pass. Preserve quality labeling: these performance measurements do not authorize deployment.

## 2026-07-22 — continue beyond the first residual shortlist

The latest negative results close only current SGLang/vLLM/TensorRT-LLM replacement, the tested static-FP8 producer ABI, forced register caps, and the tested partitioned global-attention implementation. They do not close the campaign. The retained control is `0.689220013 s/request`; continue toward `0.6381105231 s/request` or a lower price-normalized hardware result.

Rank the next portfolio from fresh telemetry rather than replaying those candidates. Strong starting directions are: (1) the dominant FP8 linear and weight-stream path, including source-level schedule, epilogue, persistent/grouped execution, and launch/dataflow changes; (2) measured scheduler, CUDA-graph, and inter-kernel gaps around the exact c32 endpoint, with one source-level intervention rather than a flag sweep; (3) a matched B200 or other price-normalized accelerator endpoint where the required speed-per-dollar hurdle is explicit; and (4) the native assistant/MTP route only after a cheap exact-path test demonstrates useful accepted-draft depth. A researcher may replace these with a better hypothesis when current evidence supports it. Keep at least one direct endpoint lane and one independent deep mechanism lane while authority remains.

Historical project maxima are not actual spend. The conservative settlement at `artifacts/SPEND_RECONCILIATION_2026-07-22.json` charged `$110` against the then-current `$200` cap and opened a new reservation epoch with `$90` unreserved. The later `$50` amendment raises only the cumulative authority; it does not alter settled spend or prior evidence. New paid projects must record conservative cumulative exposure in `STATUS.json.actual_spend_usd` before terminalization so the harness can settle actual spend and release unused allowance without weakening the hard cap.

Do not spend GPU time on an untrained 2:4 sparsity proxy. The exact-weight screen already found zero natural 2:4 structure and only 86.29–89.09% retained energy after magnitude pruning, so this is not a plausible quality-preserving near-term intervention. It can reopen only with a concrete recovery or training method. Continue first with quality-preserving dense-FP8 kernel/dataflow work, source-proven scheduler/graph reductions, and price-normalized hardware placement.

## 2026-07-25 — additional 20% from the current qualified result

The user sets the next objective as approximately 20% lower cost than the
current best quality-qualified Gemma 4 result, not 20% relative to the original
BF16 or pre-optimization baseline. Use
`0.625149101968745 s/request` as the current qualified H200 service-time
denominator. At unchanged hardware price, utilization, workload, and token
accounting, the next target is therefore at most
`0.500119281574996 s/request`.

The corresponding derived 90%-utilization planning cost is approximately
`$0.109725/M total tokens`, using the existing mapping under which
`0.6381105231 s/request` equals `$0.14/M`. Lock the `0.625149101968745`
denominator for this objective and count subsequent compatible improvements
cumulatively; do not reset the target after each incremental gain. Refresh the
absolute dollar figure only when a scope-matched production rate or accounting
assumption changes. Older `0.6381`, `$0.14/M`, BF16, and early-FP8 thresholds
remain historical comparators rather than the new campaign finish line.

## 2026-07-28 — reaffirm the 20% efficiency objective

The user reaffirms that the next campaign result must deliver approximately
20% lower sustainable cost than the current qualified result. Continue to use
`0.625149101968745 s/request` as the fixed denominator and
`0.500119281574996 s/request` as the scope-matched H200 target, or demonstrate
an equivalent 20% price-normalized improvement on another accelerator. A
component result is progress but does not satisfy the objective; the campaign
needs a complete measured endpoint and sustainable cost result.

Use the new authority for decision-bearing GPU work. Prefer a cheap
target-hardware discriminator before a long setup, preserve and repair warm
environments in place, and keep independent high-upside mechanisms advancing
in parallel. Do not spend the increment on broad quality replay, repeated
setup validation, or another full lifecycle that lacks enough time to reach
the scientific invocation.

Nebius experiment placement is region-agnostic. Before provisioning, use the
shared `research/factory/tools/lab-nebius-placement` read-only capacity
selector across every authenticated regional project. Prefer preemptible
capacity whenever the experiment can checkpoint, resume, or cheaply restart;
use on-demand when spot is unavailable or interruption would waste more than
the price difference. Bind the selected regional project, platform, preset,
allocation type, and actual rate in the paid-run evidence. Do not infer
accelerator unavailability from the profile's default-region catalog.

## 2026-07-25 — ambitious mechanism portfolio

Shape part of the portfolio around difficult changes that can alter a major
fraction of inference cost, while keeping direct GPU experiments running.
Normally keep one or two deep mechanism projects alongside execution work;
they may span multiple researcher turns and should iterate within one project
rather than being closed because the first integration attempt fails.

The leading deep mechanisms are:

1. lossless one-forward parallel drafting plus confidence- and
   hardware-aware c32 verification depth, beginning with localization of the
   existing DFlash semantic divergence;
2. replacement of Gemma's 262,144-way dense output head with a
   retrieval/clustered or otherwise sublinear head, measured separately from
   the exact grouped-projection optimization;
3. model/chip co-design of Gemma's full-versus-sliding attention placement,
   followed by hardware-specific low-bit or sparse execution when a current
   deep slot frees.

Progress on a deep project means a sharper causal model, working source,
exact-shape simulation or component measurement, or a falsified mechanism—not
additional planning. Give each project an early discriminator, but do not
require an endpoint win in its first cycle. Do not serialize quick compatible
experiments behind these projects, and do not fill all five researcher slots
with long projects waiting on the same GPU.

## Shared resources and lab files

- Shared factory tools: `research/factory/tools/`
- GPU prices and accelerator capabilities: `research/factory/data/`
- Proven Nebius lifecycle mechanics, reusable after replacing GLM-specific model assumptions: `research/sol/experiments/glm47flash/campaign_100/nebius/`
- `DIRECTOR_LOG.md`: portfolio decisions.
- `projects/<project>/PROJECT.md`: delegated question and scope.
- `projects/<project>/RESEARCH_LOG.md`: concise progress and evidence.
- `projects/<project>/STATUS.json`: scheduler state and next action.
- `SUPERVISOR_LOG.md`: process bottlenecks and useful improvements.
- `STATUS.md` and `runtime/`: generated current status, events, timings, and Codex traces.
