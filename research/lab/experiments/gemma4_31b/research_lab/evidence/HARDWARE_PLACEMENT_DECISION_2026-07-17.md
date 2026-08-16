# Gemma 4 31B hardware placement decision — 2026-07-17

## Question and decision

Should L40S remain the primary hardware target for `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4` under the campaign's prompt-heavy background workload?

**Decision:** no. Retain L40S as the mature SM89 W4/FP8 control, but make RTX PRO 6000 Blackwell the next immediate same-provider placement comparison. Keep H200 as the mature high-bandwidth control and MI355X as the highest-upside cross-stack candidate once an executable provider route exists. Do not infer a production winner from bandwidth alone.

## Scope and falsification

Scope: text-only, default non-reasoning Gemma 4 31B; approximately 4,214 prompt and 358 output tokens/request; background batching; reasonable 12–24 month production commitments. Multimodal qualification, thinking mode, multi-node scaling, and quality certification of quantized derivatives are outside this placement screen.

The RTX PRO decision is falsified if a matched complete-request run fails exact-model/runtime admission, or if its sustainable completed-request throughput is less than `1.182x` L40S at the planning rates below. H200 must exceed `2.955x` L40S throughput and MI355X `2.364x` to improve raw GPU cost/request. These are admission thresholds, not throughput predictions.

## Evidence

- **Measured:** the campaign has no valid full-model L40S endpoint result. A generic Ada FP8 component run produced 26 finite numerical/timing rows, but later source reconciliation found several shapes were not the actual fused Gemma dimensions; no endpoint transfer is allowed. Actual-vLLM FP8 and first W4 attempts produced zero timing rows due staged-program/runtime-identity failures.
- **Derived:** current FP8 accounting places the 10K single-request L40S envelope at about `40.504 GiB`; c4 fits, while c8 is representation/allocator-sensitive. L40S therefore forces representation work before an exact BF16 baseline.
- **Vendor/runtime reported:** the official vLLM Gemma 4 recipe lists 31B BF16 on one 80 GB NVIDIA GPU or one MI300X/MI325X/MI350X/MI355X. It also lists an official QAT W4A16 derivative at approximately `19.8 GB` versus `59.0 GB` BF16.
- **Vendor reported:** RTX PRO 6000 Blackwell has 96 GB and 1,597 GB/s and is currently self-service on Nebius in `us-central1`. L40S has 48 GB and 864 GB/s. RTX PRO therefore has twice the memory and `1.849x` peak bandwidth.
- **Derived market rate:** Nebius currently lists RTX PRO at `$0.95/h` preemptible and `$1.80/h` on-demand versus L40S from `$0.74/h` and `$1.55/h`. A provisional medium-commitment RTX PRO planning point of `$1.30/h` is used only for screening; obtain a written quote before a production claim.

## Screening table

Peak bandwidth per dollar is a memory-bound roofline screen, not measured application throughput.

| Accelerator | Memory | Peak bandwidth | Planning $/GPU-h | GB/s per $/h | vs L40S | BF16 placement |
|---|---:|---:|---:|---:|---:|---|
| L40S | 48 GB | 864 GB/s | $1.10 | 786 | 1.00x | No; quantized |
| RTX PRO 6000 Blackwell | 96 GB | 1,597 GB/s | $1.30 provisional | 1,228 | 1.56x | Likely; directly test |
| H100 SXM | 80 GB | 3,350 GB/s | $2.80 | 1,196 | 1.52x | Official minimum |
| H200 SXM | 141 GB | 4,800 GB/s | $3.25 | 1,477 | 1.88x | Yes |
| B200 SXM | 180 GB | 8,000 GB/s | $5.15 | 1,553 | 1.98x | Yes; node geometry matters |
| MI355X | 288 GB | 8,000 GB/s | $2.60 | 3,077 | 3.92x | Officially supported; software risk |

## Interpretation

1. **RTX PRO 6000 Blackwell is the best next experiment.** It removes the 48 GB representation constraint, has a low `1.182x` matched-throughput hurdle versus L40S, and is already listed by the current experimental provider. It is a cleaner way to establish a BF16 baseline than another H100 staging lineage. Its SM120 runtime must be pinned and tested because current vLLM issue history shows model-dependent FP4/FP8 support gaps.
2. **H200 is more plausible than H100 as the mature production high-bandwidth candidate.** At current planning rates H100 and RTX PRO have similar peak-bandwidth/$, while RTX PRO offers more memory at much lower absolute hourly cost. H200 has better bandwidth/$ and ample KV capacity; it deserves a matched run if it can deliver at least `2.5x` RTX PRO throughput or creates a useful concurrency/replica discontinuity.
3. **MI355X has the highest theoretical cost upside.** Its 288 GB/8 TB/s envelope and the official single-GPU Gemma recipe make it a serious candidate, not an AMD side project. The claim remains uncertain until exact Gemma 4 ROCm/AITER startup, kernel coverage, quality, and complete-request throughput are measured on an accessible single-GPU placement.
4. **L40S remains useful, not primary.** Its mature SM89 CUDA/Marlin path and low experiment price make it the right control for the official 19.8 GB W4 derivative and for 48 GB cost floors. It wins only if mature W4 kernels compensate for its lower bandwidth and if the derivative passes later quality/feature gates.
5. **B200 is a scale candidate, not the next prototype.** Its bandwidth/$ screen is strong, but HGX tenancy and a high absolute hourly/node commitment require enough traffic or multiple replicas. Test it after one single-GPU baseline makes the denominator reliable.

## Next matched experiment

On one RTX PRO 6000 Blackwell in `us-central1`, pin the exact installed CUDA/vLLM image first and run the exact BF16 target at the campaign workload plus the 10K single-stream view. If BF16 passes, retain the allocation for one official QAT W4A16 arm only when its checkpoint identity and raw-output quality boundary are explicit. Capture complete-request throughput, prompt/decode split, memory, power, setup/useful seconds, and actual cost. Compare directly against a corrected L40S W4 run; admit H200 next only if the observed phase mix suggests its `2.5x` RTX throughput hurdle is plausible.

## Sources

| Source | Date/revision | Retrieved | Evidence type |
|---|---|---|---|
| [vLLM Gemma 4 usage guide](https://docs.vllm.ai/projects/recipes/en/stable/Google/Gemma4.html) | stable page, 2026 | 2026-07-17 | official runtime report |
| [NVIDIA L40S specifications](https://www.nvidia.com/en-eu/data-center/l40s/) | current page | 2026-07-17 | vendor reported |
| [NVIDIA H200 specifications](https://www.nvidia.com/en-us/data-center/h200/) | current page | 2026-07-17 | vendor reported |
| [NVIDIA RTX PRO 6000 Blackwell specifications](https://www.nvidia.com/en-us/data-center/rtx-pro-6000-blackwell-server-edition/) | current page | 2026-07-17 | vendor reported |
| [AMD MI350 series specifications](https://www.amd.com/en/products/accelerators/instinct/mi350.html) | current page | 2026-07-17 | vendor reported |
| [Nebius GPU prices](https://nebius.com/prices) | current page | 2026-07-17 | vendor reported market price |
| [Nebius VM/GPU types](https://docs.nebius.com/compute/virtual-machines/types) | current docs | 2026-07-17 | vendor reported availability |
| `research/factory/data/gpu_prices.json` | refreshed 2026-07-15 | 2026-07-17 | derived committed-rate inventory |
| `research/factory/data/accelerator_inventory.json` | reviewed 2026-07-15 | 2026-07-17 | normalized vendor specifications |
| `projects/gemma_l40s_fp8_exact_shape_microbench/artifacts/gemma-l40s-fp8-corr-20260717t000000z/summary.json` | immutable run artifact | 2026-07-17 | measured component evidence |

## Uncertainty and competing explanations

Peak bandwidth can overpredict gain when Gemma is compute-, launch-, scheduler-, or output-head-bound at the chosen batch. RTX PRO's GDDR7 latency and SM120 kernel maturity may offset its roofline advantage; H200 may win through HBM and mature Hopper kernels; L40S W4 may win because mature compressed-weight execution reduces bytes enough to dominate both. Only the matched complete-request experiment resolves the ordering.
