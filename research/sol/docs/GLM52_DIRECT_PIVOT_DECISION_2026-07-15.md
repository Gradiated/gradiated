# GLM-4.7-Flash graduation and GLM-5.2 pivot decision

Date: 2026-07-15

## Decision

Keep GLM-4.7-Flash as the research-lab integration target for one short, bounded graduation phase, then move the scientific campaign to GLM-5.2. GLM-4.7-Flash has already proven that the lab can launch a real model, run a GPU experiment, measure an intervention, retain telemetry, and clean up. It should now prove repeatability, quality eligibility, and external benchmark comparability—not become a long-running optimization target.

The graduation gates are:

1. one quality-eligible result;
2. one Artificial Analysis methodology-matched cost/performance report;
3. one retained allocation that executes several intervention arms with complete telemetry and cleanup.

Once these pass, GLM-4.7-Flash remains only as a cheap harness regression target. Model-specific opportunity research moves to GLM-5.2.

## Why not switch immediately?

The direct scientific value is now higher on GLM-5.2, but failed orchestration is much more expensive there. The exact checkpoints are roughly 465 GB for NVIDIA NVFP4 and 761 GB for official FP8, versus 20.17 GB for the current GLM-4.7-Flash AWQ checkpoint. Supported GLM-5.2 configurations generally occupy a multi-GPU node rather than one L40S. At current public rates, likely direct test geometries are roughly 14x to 67x the current experiment's hourly compute rate, depending on accelerator, count, and preemptible/on-demand placement. Artifact staging and cold-start time can dominate unless weights and images are cached provider-side.

This is not a reason to delay GLM-5.2 for weeks. It is a reason to close the three cheap graduation gates first and carry a proven resident-allocation loop upward.

## GPU pricing basis and commitment sensitivity

Headline production estimates use the shared [GPU price inventory](../../factory/data/gpu_prices.json), not on-demand or experimental rates. The base case represents a reasonable 12–24 month commitment for roughly 8–64 non-preemptible GPUs: attainable by a growing inference provider, but excluding promotional credits and rock-bottom hyperscale or 36–48 month floors.

| Accelerator | Production planning rate | Evidence range | Default-node planning rate |
| --- | ---: | ---: | ---: |
| L40S | `$1.10/GPU-hour` | `$1.00–$1.25` | `$1.10/hour` for 1× |
| H100 SXM | `$2.80/GPU-hour` | `$2.50–$3.10` | `$22.40/hour` for 8× |
| H200 SXM | `$3.25/GPU-hour` | `$2.925–$3.60` | `$26.00/hour` for 8× |
| B200 SXM | `$5.15/GPU-hour` | `$4.6475–$5.72` | `$41.20/hour` for 8× |
| MI355X | `$2.60/GPU-hour` | `$2.40–$2.75` | `$20.80/hour` for 8× |

The L40S `$0.8581222/hour`, Nebius preemptible rates, and TensorWave `$2.95` MI355X listing remain experiment or market references, not production base cases. A current written quote that matches accelerator, topology, term, scale, region, and included services supersedes the planning rate. Weekly refreshes update all researchers through the one shared inventory.

At Wafer's reported 2,626 output tokens/s on 8×MI355X, the `$20.80/hour` planning node rate implies approximately `$2.20/M` GPU-only output COGS. This replaces the `$2.50/M` estimate based on current on-demand pricing while deliberately remaining above the approximately `$1.94/M` result implied by the directional long-term floor.

## Current GLM-4.7-Flash market gap

The relevant comparator is Artificial Analysis's GLM-4.7-Flash **non-reasoning** page because the measured harness disables thinking. The full GLM-4.7 pages and the GLM-4.7-Flash reasoning page are separate variants.

Measured current-AWQ L40S c16 evidence:

- 8,192 native input tokens and 1,024 native output tokens per request;
- prefix cache disabled;
- 535.286 aggregate output tokens/s at c16;
- `$0.445308/M` output tokens on the actual experimental GPU-hour denominator;
- `$0.570827/M` output-equivalent after rebasing identical measured throughput to the shared `$1.10/hour` medium-term L40S production planning rate;
- c1 P50 TPOT 16.60 ms, approximately 60.2 native tokens/s after the first token;
- c16 P50 TTFT 9.43 seconds and P95 TTFT 10.06 seconds;
- inherited absolute-quality eligibility remains unresolved.

Artificial Analysis non-reasoning snapshot on 2026-07-15:

- Amazon and Novita: `$0.10/M` headline blended price;
- both: `$0.07/M` input and `$0.40/M` output;
- Amazon: about 206.4 output tokens/s;
- Novita: about 92.1 output tokens/s;
- default performance view: single request, about 10K input and at least 1,500 output, OpenAI-token speed, rolling P50.

For the campaign's measured 8:1 uncached input:output mix, the listed retail transaction costs `$0.96/M output-equivalent` (`8 × $0.07 + $0.40`). Rebasing the measured throughput to the shared medium-term committed L40S rate gives `$0.570827/M`, 40.5% below that retail amount, or 1.68× cheaper, before utilization and non-GPU lifecycle overhead. The actual experimental-rate result remains `$0.445308/M` but is not the production headline. This is encouraging but not a business win yet because quality, sustainable utilization, lifecycle cost, native-vs-OpenAI token accounting, and exact benchmark geometry are not closed.

The current single-request speed is only a rough comparison: about 60.2 native tokens/s locally versus 206.4 OpenAI tokens/s for Amazon and 92.1 for Novita. That is approximately 3.4x and 1.5x slower respectively, but the token accounting, prompts, input/output lengths, network path, and rolling window are unmatched. Aggregate c16 throughput must not be compared with Artificial Analysis's single-request speed.

## Minimal benchmark implementation

Add two profiles to the existing workload runner rather than another orchestration system:

- `aa_serverless`: diverse prompts; one request; approximately 10K input; at least 1,500 output; streaming; native and `o200k_base` token counts; TTFT, post-first-token speed, end-to-end time, and repeated-run medians.
- `aa_slt`: the public Artificial Analysis System Load Test geometry—1K input/1K output, streaming, three-minute concurrency phases through saturation—with aggregate and per-request results.

Every result should emit the exact model/revision, reasoning mode, representation, engine, hardware, provider/rate, prompt hashes, sampling settings, tokenizers/counts, component and blended price targets, all-in COGS assumptions, quality status, and raw request/GPU telemetry. Reuse retained allocations so setup is amortized over multiple scientific arms.

## GLM-5.2 stack coverage after graduation

The lab's conceptual search surface is broad enough, but executable GLM-5.2 coverage must include the interfaces Wafer's result showed are decisive:

- provider-side checkpoint cache, persistent volume, and prebuilt images;
- a common comparison path across vLLM, SGLang, and ATOM where supported;
- per-rank GPU/HBM/power plus NCCL/RCCL, expert-routing imbalance/locality, MTP acceptance by depth, DSA scan/gather/index reuse, KV/prefix cache, and scheduler telemetry;
- reproducible official FP8, NVIDIA NVFP4, and AMD Quark MXFP4 checkpoint/quality pipelines;
- TP/DP/EP topology and replica experiments, not only kernel tuning;
- exact-shape MoE/DSA profiling before custom kernels;
- cost models using Artificial Analysis 7:2:1 and the measured background-agent mix, including utilization, failures, and contracted/spot rates.

Keep these as shared adapters, profiles, and telemetry tools. Do not add more lab stages or deterministic process gates.

## Sources and evidence labels

- Measured: [current AWQ c16 research log](../experiments/glm47flash/research_lab/projects/nebius_current_awq_c16_direct/RESEARCH_LOG.md)
- Derived: [Artificial Analysis sustainable comparator](../experiments/glm47flash/research_lab/projects/artificial_analysis_sustainable_comparator/RESEARCH_LOG.md)
- External current: [GLM-4.7-Flash non-reasoning providers](https://artificialanalysis.ai/models/glm-4-7-flash-non-reasoning/providers)
- External current: [GLM-4.7-Flash reasoning providers](https://artificialanalysis.ai/models/glm-4-7-flash/providers)
- External methodology: [Language Model API Performance Benchmarking](https://artificialanalysis.ai/methodology/performance-benchmarking)
- External methodology: [System Load Test](https://artificialanalysis.ai/methodology/system-load-test)
- External primary technical recipe: [vLLM GLM-5.2 recipe](https://recipes.vllm.ai/zai-org/GLM-5.2)
- External current pricing: [Nebius GPU pricing](https://nebius.com/prices)
- External current market listing: [TensorWave MI355X on-demand price](https://gpus.io/en/gpus/mi355x)
- External vendor access terms: [TensorWave MI355X access request](https://go.tensorwave.com/)
- External directional reserved-market evidence: [Dell third-party MI355X cloud cost context](https://infohub.delltechnologies.com/en-sg/t/third-party-analysis-8/)
- Research prior: [Wafer AI full-stack deep dive](WAFER_AI_FULL_STACK_DEEP_DIVE_2026-07-15.md)
