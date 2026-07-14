# GLM-4.7-Flash research-harness review

Date: 2026-07-14

## Question and decision

Question: Is the campaign using measurements to identify and attack causal bottlenecks across model architecture, representation, kernels, serving, memory hierarchy, hardware, and providers, or is it selecting changes by intuition without enough localization evidence?

Decision: the harness is scientifically disciplined but only partially mature as a bottleneck-discovery engine. It is strong at identity, preregistration, fail-closed gates, evidence retention, cleanup, and claim boundaries. Its best measurement-to-intervention loop is the retained L40S session covering V19 through V22R1. Its current weaknesses are phase attribution, hardware-counter coverage, statistical replication, factorial controls, prediction scoring, and workload breadth. Continue narrowly, but require the typed observation-to-candidate contract in `OPPORTUNITY_REGISTER_2026-07-14.json` before promoting another intervention.

## Claim scope and non-scope

This review covers the local GLM-4.7-Flash campaign through V22R1:

- Complete BF16 checkpoint revision `33faccf4c2ba82142214d0d4e16232a4e9ccfe10` on one Nebius H100 with pinned SGLang.
- Public AWQ checkpoint revision `ab31d120fbe79988fe2a0259993cf3c222aa8881` on one Nebius L40S with pinned vLLM 0.15.0 and Transformers revision `1618d44b9295361607ec74d7be860ba886aac039`.
- Frozen fixed workload of 8,192 input and 1,024 output tokens at c1 and c8, plus the compact paired quality diagnostic.
- V19 BF16 activation control, V20 FP16 activation arm, V21 65,536-token scheduler arm, V22 illegal 64-token MLA tile, and V22R1 legal one-stage repair.

It does not establish general GLM quality, a Fireworks or Baseten comparison, fully loaded serving cost, a custom co-design improvement, simulator calibration, or a hardware/tapeout case. Public-paper and tool documentation below is prior art that motivates measurements; it is not evidence that the same effects hold for this model or workload.

## Hypothesis and falsification rule

Methodological hypothesis: a useful co-design harness should form a closed causal loop:

1. Measure a workload- and phase-scoped bottleneck.
2. Record competing explanations and uncertainty.
3. Rank interventions by prospective removable cost, risk, and information per dollar.
4. Falsify cheaply at component scope.
5. Promote only to a matched, repeated end-to-end A/B when correctness and prospective effect gates pass.
6. Measure the bottleneck transition and score the prior prediction.

This hypothesis is falsified for the current harness if interventions routinely lack a scoped measured observation, if component time is treated as end-to-end wall time, if changes are not matched against a tuned control, or if negative measurements do not update the opportunity ranking.

## Evidence labels

- **Measured**: produced by a campaign allocation or retained local artifact.
- **Derived**: arithmetic over measured values under an explicit formula.
- **Vendor-reported**: provider or tool-vendor documentation and pricing.
- **Prior-art claim**: a primary paper's result in its own model, workload, software, and hardware scope.
- **Inferred**: a causal interpretation not isolated by the current experiment.
- **Recommendation**: a proposed harness or experiment change.

## Method

This was a read-only audit of the campaign plan, report, ledger, decision artifact, quality fixtures, retained allocation bundles, profiler-derived analyses, and relevant scripts. Measurements were accepted only when their local artifact and scope could be identified; arithmetic was relabeled derived; causal explanations not isolated by a matched control were relabeled inferred. Primary papers and official project, vendor, or standards documentation were used only to identify missing measurements and experimental patterns. No provider resource was created, changed, or deleted for this review.

The opportunity register uses `research/sol/experiments/glm47flash/campaign_100` as its artifact-path base. Its selected candidate is a recommendation, not a campaign result.

## Scorecard

| Capability | Score | Evidence-based assessment |
|---|---:|---|
| Experimental integrity | 4.5/5 | Preregistrations bind model, runtime, workload, gates, budget, timeout, artifacts, and cleanup. Negative and invalid results are retained without being promoted. |
| Request/SLO measurement | 3.5/5 | Exact token geometry, request rows, TTFT, TPOT, throughput, queue totals, failures, and cache deltas are captured. Arrival-rate surfaces and scheduler-iteration state are missing. |
| Bottleneck localization | 2/5 | PyTorch traces identify kernel families and launch resources, but the decisive vLLM trace is a single c1 mixed prefill/decode request and lacks a reliable c8 wall-time attribution. |
| Intervention selection | 2.5/5 | V21 follows measured queueing and V22 follows a trace-selected resource-heavy kernel. No durable Phase-E ranking records removable fraction, risk, test cost, or expected information. |
| Search-space coverage | 2/5 | Representation and one serving knob have evidence. Architecture, prefix reuse, memory hierarchy, MoE routing, and provider matching remain largely unmeasured. |
| Iteration efficiency | 2.5/5 historical; 4/5 V19-V22 | Early allocations repeatedly discovered harness defects. The retained L40S session reused image, checkpoint, and GPU across four materially changed arms and is the correct operating pattern. |
| Business claim discipline | 4.5/5 | The decision correctly refuses general quality, provider, custom co-design, and fully loaded cost claims. |

Overall: approximately 3/5. The harness is not operating blindly, but it is better at evidence custody than at automatically finding the highest-value bottleneck.

## What the campaign learned systematically

### Runtime semantic disambiguation

**Measured:** V15's patched SGLang AWQ path loaded but produced nondeterministic gibberish. V18's stock vLLM path loaded the same checkpoint and produced the requested JSON deterministically.

**Inference:** the public checkpoint alone was not a sufficient explanation for V15. The custom SGLang loader or execution path was implicated, although no single patch component was isolated.

**Assessment:** strong causal use of a materially different stock control. This is the clearest example of an observation choosing the next experiment.

### Scheduler token budget

**Measured:** V19 c8 queue time averaged 0.5954 seconds with `max_num_batched_tokens=32768`. V21 raised only that budget to 65,536, reducing measured mean queue time to approximately 0.000013 seconds. C8 throughput improved from 344.211 to 355.772 output tok/s, or 3.36%, while the preregistered useful threshold was 5%.

**Inference:** the token budget caused queueing, but queue removal was not the dominant throughput constraint.

**Assessment:** good observation-to-intervention logic and good falsification. The result should narrow future scheduler work to different workload regimes rather than trigger more nearby tuning on the same burst.

### Activation dtype

**Measured:** V20 changed only BF16 activations to FP16 after vLLM warned about BF16 Marlin on pre-SM90 hardware. C8 regressed 2.85%.

**Assessment:** a cheap retained-session falsifier, but selected from a runtime warning rather than a localized resource measurement. It is useful exploration, not proof that the search engine identified the dominant bottleneck.

### Grouped MLA kernel

**Measured:** V21's `_fwd_grouped_kernel_stage1` launch uses the exact absorbed GLM MLA geometry, 202 registers per thread, 89,088 bytes of shared memory, and a `(1,2,4)` grid in the captured c1 request. The V22 64-token/two-stage candidate required 159,744 bytes of shared memory against an L40S limit of 101,376. V22R1 reduced stages to one, became legal, used 255 registers per thread and 86,016 bytes of shared memory, but regressed c8 by 4.21%.

**Measured but unscoped diagnostic only:** the stock grouped stage accounts for approximately 37.38% of summed CUDA-kernel duration in V21's one-request 8K-prefill/128-decode trace. This is not c8, not pure decode, and not an end-to-end wall-time fraction. CUDA graphs and overlapping GPU work make summed kernel durations non-additive. The 37% value must not be used as a c8 Amdahl coefficient or as evidence that a 10% component gain predicts a 5% serving gain.

**Assessment:** resource pressure and hardware legality make the standalone exact-shape autotune experiment evidence-led. Running V22 first through a full model server was inefficient; compile legality and numerical correctness should have been tested before model transfer and load.

## Where the harness fumbled

### Integration defects consumed scientific budget

The early Nebius lineage discovered CIDR parsing, frozen-bundle identity, tokenizer return-shape, hard-coded output path, OpenAI tool-envelope, SSE usage, token-observability, missing import, transfer-permission, package-metadata, and response-parser defects sequentially on paid GPUs. Some failures exposed genuine runtime-contract boundaries, but several were locally reproducible harness defects. The harness now has better tests and retained-allocation behavior; future work should add recorded API fixtures and a no-GPU end-to-end dry run before allocation.

### Exact identity did not guarantee checkpoint completeness

V7-V9 used the exact pinned revision and passed file identity checks, but a later audit found only 44 of 48 indexed weight shards. Their intended-model quality, throughput, trace, and cost results were invalidated. Future checkpoint admission must prove that every index reference exists and that the complete expected byte geometry is present before allocation.

### The quality gate is useful but not decision-grade

The development and holdout splits contain six cases each. The absolute NLL ceiling was uncalibrated for the synthetic sentence, and exact output scoring rejects some semantically correct fenced responses. The campaign correctly carries the absolute failure forward and uses AWQ results only as paired diagnostics. A future campaign needs a calibration split, disjoint holdout, more executable cases, and explicit normalization policy fixed before candidate observation.

### The representation result is factorially confounded

V13 versus V21 changes BF16 to public AWQ, H100 to L40S, and SGLang to vLLM. The result is a valuable whole-stack representation/hardware signal, but it cannot attribute the gain to quantization, runtime, or hardware separately. Same-runtime and same-hardware bridge controls are required before calling the effect model-specific co-design.

### Predictions are not being scored

The sealed Phase-A prediction expected roughly 660 BF16 H100 output tok/s and 250 AWQ L40S tok/s. The complete-model c8 measurements were approximately 305 and 344 respectively, under different realized geometry and pricing assumptions. These mismatches are not a predictor failure proof without a scope audit, but they must be formally scored rather than left as narrative. V20-V22 record thresholds and directions but no calibrated magnitude model or bottleneck-transition prediction.

## Instrumentation blind spots

The current harness captures useful request rows and one-second `nvidia-smi` telemetry. It does not yet capture:

- phase-scoped c8 critical-path attribution for prefill versus steady decode;
- CUDA-graph-aware per-node attribution;
- HBM and L2 bytes, hit rates, arithmetic intensity, or achieved bandwidth;
- achieved occupancy, issue stalls, local-memory spills, or launch-bound behavior for finalist kernels;
- per-iteration scheduler batch composition, prefill/decode token counts, KV occupancy, and preemption;
- CPU utilization, Python/runtime launch overhead, or network contribution;
- repeated alternating control/candidate samples with uncertainty.

NVIDIA's official Nsight Systems documentation describes NVTX ranges and node-level CUDA Graph tracing for scoped timelines. Nsight Compute documents occupancy, cache/data-transfer analysis, and hierarchical rooflines. These tools support the missing measurements, but their use must be bounded because profiler overhead can perturb serving.

## Prior-art implications

The prior art does not nominate a winning GLM intervention. It defines stronger experiment design:

- Triton's official autotune tutorial varies block shapes, stages, and warps over an input-shape key and validates against a reference. This supports bounded exact-shape autotuning after correctness and resource gates.
- PagedAttention explicitly couples KV block size, fragmentation, parallelism, scheduling, and variable sequence lengths, and its paper separates kernel overhead from end-to-end system benefit. This supports workload-specific cache/scheduler experiments rather than isolated peak-kernel claims.
- SGLang's RadixAttention result is about prefix reuse under structured workloads. It motivates a tuned prefix-cache control only on a workload with measured reusable prefixes; it does not justify enabling caching on the current fixed synthetic burst and claiming agent-serving benefit.
- DeepSeek-V2 identifies low-rank KV compression and MoE as architecture-level inference mechanisms. For GLM, that makes MLA and routing plausible search regions, not proven bottlenecks.
- MLPerf's official methodology uses scenario-specific load generation, scheduling, logging, latency tracking, accuracy validation, and final metric computation. The campaign should emulate those separation principles while keeping its own GLM workload and SLO.

## Required observation-to-candidate contract

Before a candidate is admitted, record:

1. Observation ID and evidence label.
2. Exact model, representation, runtime, hardware, workload, concurrency, phase, and trace identity.
3. Measured metric, uncertainty, and whether it is wall time, summed component work, utilization, or a proxy.
4. Competing explanations and missing controls.
5. Candidate mechanism and exact changed variable.
6. Stock control and unchanged variables.
7. Prospective component effect, end-to-end ceiling, and derivation; use `unknown` when phase attribution is absent.
8. Correctness, quality, SLO, and resource gates.
9. Falsifier, kill condition, spend cap, timeout, and artifact contract.
10. Expected decision resolution and information per dollar.
11. Required holdout and bottleneck-transition measurement.

The linked opportunity register implements these fields for the current search space.

## Prioritized harness improvements

### P0: before another full-server custom kernel

- Run the exact-shape standalone MLA correctness/resource/timing screen without weights.
- Keep the 37% mixed c1 share labeled diagnostic; do not derive c8 gain from it.
- Obtain a matched c8 phase trace before using an Amdahl promotion calculation.
- Interleave stock and candidate timing rounds and retain raw samples and confidence intervals.
- Promote only a legal, correctness-passing candidate; then run a same-session, matched, repeated full-server A/B.

### P1: strengthen bottleneck discovery

- Add NVTX-scoped prefill and steady-decode captures with CUDA Graph node tracing.
- Add bounded Nsight Compute sections for memory workload, occupancy, and roofline on finalist kernels.
- Persist scheduler iteration, batch composition, KV allocation, prefix reuse, and preemption counters.
- Automate the opportunity register update after each result, including prediction error and bottleneck transition.

### P1: strengthen serving and business evidence

- Measure concurrency and arrival-rate frontiers rather than only simultaneous c1/c8 bursts.
- Restore distinct `agent_append` and `agent_prefix` workloads with observable SLO metrics.
- Add same-runtime/same-hardware bridge controls to separate AWQ, runtime, and GPU effects.
- Calibrate a new quality development screen before freezing its disjoint holdout.
- Run a provider control only when the exact workload, quality, SLO, and price denominator can be matched.

## Next action and kill condition

Next action: execute the standalone exact-shape GLM MLA grouped-decode autotune already named by the campaign decision, but treat it as a component falsifier. First reproduce stock and the known V22R1 negative control. Reject illegal configurations before timing. Require correctness against a float32 oracle, raw interleaved timing samples, and resource metadata. Do not transfer weights unless a candidate has a conservative component improvement large enough to merit a matched c8 trace and full-server holdout.

Kill the custom MLA lineage if no legal correctness-passing candidate achieves a stable material component improvement, or if a matched c8 measurement cannot support at least a 5% end-to-end opportunity. Do not substitute the unscoped 37% diagnostic share for that missing c8 evidence.

## Sources

Retrieval date for all sources: 2026-07-14.

| ID | Title | Revision/publication | Evidence type | Relevance |
|---|---|---|---|---|
| S1 | [NVIDIA Nsight Compute Profiling Guide](https://docs.nvidia.com/nsight-compute/ProfilingGuide/index.html) | Nsight Compute 13.3 documentation, retrieved 2026-07-14 | Vendor official documentation | Memory workload analysis, cache/data transfers, occupancy, and roofline measurements. |
| S2 | [NVIDIA Nsight Systems User Guide](https://docs.nvidia.com/nsight-systems/UserGuide/index.html) | Current documentation, retrieved 2026-07-14 | Vendor official documentation | NVTX ranges, timeline scoping, and CUDA Graph tracing. |
| S3 | [Triton matrix multiplication tutorial](https://triton-lang.org/main/getting-started/tutorials/03-matrix-multiplication.html) | Triton main documentation, retrieved 2026-07-14 | Project official documentation | Correctness comparison and autotuning over block sizes, stages, warps, and shape keys. |
| S4 | [Efficient Memory Management for Large Language Model Serving with PagedAttention](https://arxiv.org/abs/2309.06180) | arXiv:2309.06180, 2023 | Primary paper | KV paging, block-size tradeoffs, scheduling, prefix sharing, and component-versus-system evaluation. |
| S5 | [SGLang: Efficient Execution of Structured Language Model Programs](https://arxiv.org/abs/2312.07104) | arXiv:2312.07104; NeurIPS 2024 | Primary paper | RadixAttention, structured workload reuse, and runtime/workload co-design. |
| S6 | [DeepSeek-V2: A Strong, Economical, and Efficient Mixture-of-Experts Language Model](https://arxiv.org/abs/2405.04434) | arXiv:2405.04434, 2024 | Primary paper | MLA low-rank KV compression and DeepSeekMoE as architecture-level mechanisms. |
| S7 | [MLPerf Inference submission guide](https://docs.mlcommons.org/inference/submission/) | Current MLCommons documentation, retrieved 2026-07-14 | Standards-body official documentation | Scenario-specific load generation, scheduling, logging, latency, accuracy, and metric computation. |

## Reproduction paths

Campaign evidence:

```text
research/sol/experiments/glm47flash/REPORT.md
research/sol/experiments/glm47flash/CAMPAIGN_100_PLAN.md
research/sol/experiments/glm47flash/campaign_100/CAMPAIGN_LEDGER.jsonl
research/sol/experiments/glm47flash/campaign_100/DECISION_CONTINUE_NARROWLY_2026-07-14.json
research/sol/experiments/glm47flash/campaign_100/analysis/TRACE_BOTTLENECK_V13.json
research/sol/experiments/glm47flash/campaign_100/allocations/nebius_l40s_vllm_awq_batch_v19/
research/sol/experiments/glm47flash/campaign_100/allocations/nebius_l40s_vllm_awq_fp16_v20/
research/sol/experiments/glm47flash/campaign_100/allocations/nebius_l40s_vllm_awq_prefill65k_v21/
research/sol/experiments/glm47flash/campaign_100/allocations/nebius_l40s_vllm_awq_mla_block64_v22/
research/sol/experiments/glm47flash/campaign_100/allocations/nebius_l40s_vllm_awq_mla_block64_stage1_v22r1/
```

No provider resources were allocated for this review.
