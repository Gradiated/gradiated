# Qwen3-8B vertical co-design study v0

Status: **analytical screening only; no production, provider-competition, or tapeout claim is permitted.**

This study asks whether model-specific changes to Qwen3-8B, followed by kernel specialization, serving simulation, hardware re-sizing, fleet sizing, and cost allocation, could lower the cost charged separately for input and output tokens on an agentic workload. The current answer is useful but deliberately narrow:

- The paired analytical candidate is projected to reduce input cost by 48.39%, output cost by 31.16%, and workload-weighted cost by 34.67% relative to the unchanged-model custom-sizing reference.
- Against the analytical four-H100 owned-TCO sensitivity, it is projected to be 16.16x cheaper on input tokens, 3.28x cheaper on output tokens, and 5.34x cheaper on the study's token mix.
- Group-aware quantized-weight storage accounting is complete for every factorial point. The paired W4 candidate uses group size 128 and 16-bit scales, so its effective storage is exactly 4.125 bits per quantized weight, not four bits.
- Both selected custom-hardware points are feasible under the declared analytical sizing constraints. The unchanged model's attempted 20,000-output-token/s point is rejected and excluded because it would require 26 devices against a limit of 16 and seven HBM stacks per device against a limit of four.
- Those ratios are **not measured speedups or validated provider savings**. Model quality is unmeasured, performance uses the Level 0 roofline oracle, the custom hardware has not been externally validated, and the H100 owned cost is an internal assumption.
- The sensitivity sweep rejects a robust output-cost claim: at 1,000 amortization units, every output-token scenario is more expensive than the assumed owned-H100 baseline.

The result supports continuing validation. It does not yet support the thesis that vertical co-design materially beats Fireworks, Baseten, vLLM, SGLang, or TensorRT-LLM.

## Frozen comparison contract

The target checkpoint fixture is `Qwen/Qwen3-8B` at declared revision `b968826d9c46dd6066d109eabc6255188de91218`: a 36-layer dense decoder with 8.2 billion declared parameters, hidden size 4,096, feed-forward width 12,288, 32 query heads, eight KV heads, head dimension 128, BF16 weights, FP16 KV, and a 32,768-token context. The architecture fixture comes from [the checked-in Qwen source record](../../configs/SOURCES.md); the revision identity does not substitute for a locally hashed Qwen3-8B checkpoint.

The synthetic `agentic-v1` trace has 512 requests arriving at 2 requests/s with seed `20260711`:

| Class | Share | Input tokens | Output tokens | Assumed prefix hit |
|---|---:|---:|---:|---:|
| Tool turn | 25% | 2,048 | 256 | 40% |
| Coding turn | 45% | 16,384 | 1,024 | 85% |
| Long agent turn | 30% | 28,672 | 2,048 | 92% |

The realized trace contains 8,585,216 input tokens and 591,872 output tokens. It is a privacy-safe hypothesis about agent usage, not a measurement of Claude Agent SDK, Fireworks, Baseten, or customer traffic. The workload-weighted metric is the total modeled cost divided by all realized input and output tokens; it is reported only as a diagnostic because the business prices input and output separately.

Class objectives are fixed by [`qwen3-agentic-slo-v2.json`](../../configs/workloads/qwen3-agentic-slo-v2.json):

| Class | p95 TTFT ceiling | p95 TPOT ceiling |
|---|---:|---:|
| Tool | 2,000 ms | 50 ms |
| Coding | 5,000 ms | 50 ms |
| Long agent | 10,000 ms | 70 ms |

The serving policy is held at batch size 64, 512-token prefill chunks, one prefill opportunity per eight decode steps, 32 concurrent requests on sized custom hardware, and 80% of HBM available to KV. Economics assume $0.12/kWh, 1.2 PUE, $0.25/provider-hour overhead, and a 50% target gross margin.

## Three baselines, not one

The baselines answer different questions and must not be conflated.

1. **Unchanged-model custom-sizing reference.** The unchanged Qwen model and baseline CUDA/paged/attention-and-MLP kernel are passed through the same analytical hardware sizer, serving simulator, capacity planner, and custom-silicon TCO model as the candidate. This is the baseline for the exact Shapley attribution and the 34.67% internal-methodology reduction. Its selected spec ID is `a4d77fdf0a6bdef2befb2c920c4425fd887e2c783d9d47ceada91b9b6626bc17`.
2. **Four-H100 owned-TCO sensitivity.** Two four-H100 tensor-parallel groups, eight H100s total, are selected by the analytical capacity planner. The assumed group cost is $10/hour plus $0.50 host/hour. This is an internal cost sensitivity, not a purchase quote, provider marginal cost, or measurement.
3. **Four-H100 public-rental sensitivity.** The same simulated timing is costed at $28/four-H100-hour plus $0.50 host/hour, derived from four times the checked-in $7/H100-hour public rental reference. It is a rental comparison, not a Fireworks per-token benchmark.

No tuned vLLM, SGLang, TensorRT-LLM, Fireworks endpoint, or Baseten endpoint has yet replayed this trace. Consequently, none is a valid competitive baseline in v0.

## Candidate and modeled mechanisms

The paired candidate composes five changes:

| Decision | Intended model-specific mechanism | Unvalidated risk |
|---|---|---|
| Rotation-assisted INT4 weights | Reduce resident dense weights and the weight stream read on every decode step | Quantization and rotation quality; executable kernel efficiency |
| FP8 KV cache | Halve KV capacity and traffic relative to FP16 for long agent contexts | Numerical and task-quality loss |
| Four KV heads | Halve KV state again and slightly shrink projection weights | Architecture change requires training or adaptation |
| Feed-forward width 10,240 | Reduce the repeated 36-layer MLP's parameters and arithmetic | Architecture change requires training or adaptation |
| Full-layer 128x128 fusion | Reduce launches and intermediate HBM materialization for repeated Qwen layer geometry | Fusion benefit, register/SRAM pressure, and generated-kernel correctness |

After the changes, the analytical model has 7,143,035,392 parameters, group-128 INT4 weights with 16-bit scales, FP8 KV, four KV heads, and a 10,240-wide feed-forward block. Full quantized coverage therefore stores `4 + 16/128 = 4.125` effective bits per weight, or exactly 3,683,127,624 weight bytes before other runtime allocations. The kernel is labeled Rust because Rust is the intended generation/runtime surface. The model assigns **no Rust-over-CUDA language speedup**.

Every factorial point is re-sized and re-mapped from its resulting tensor geometry, then independently capacity-planned against the same workload and SLO. This matters because cost changes are discontinuous when a design crosses an HBM-stack, device, or replica threshold.

## Analytical results

All latency, throughput, energy, and cost values in this section are simulator outputs, not measurements.

### Same-methodology comparison

| Metric | Unchanged-model custom reference | Paired model + kernel + re-sized hardware | Reduction |
|---|---:|---:|---:|
| Input cost / 1M tokens | $0.010987 | $0.005671 | 48.39% |
| Output cost / 1M tokens | $0.622804 | $0.428709 | 31.16% |
| Workload-weighted cost / 1M tokens | $0.050531 | $0.033013 | 34.67% |
| Minimum input price / 1M at 50% margin | $0.021975 | $0.011341 | 48.39% |
| Minimum output price / 1M at 50% margin | $1.245608 | $0.857419 | 31.16% |
| Required replicas | 3 | 1 | 66.67% fewer |
| Deployed logical accelerators | 21 | 7 | 66.67% fewer |
| Simulated p95 TTFT | 1,754.09 ms | 450.86 ms | 74.30% lower |
| Simulated p95 TPOT | 23.43 ms | 6.69 ms | 71.45% lower |
| Simulated trace energy / replica | 812.9 kJ | 263.8 kJ | 67.54% lower |

Both fleets deliver nearly the same simulated aggregate output goodput: 2,180.85 tokens/s for the reference and 2,189.00 tokens/s for the candidate. The paired candidate does so with one seven-device replica instead of three. Energy is normalized to one complete 512-request simulated trace per replica; multiplying both energy and tokens by the replica count leaves the per-token comparison unchanged. Candidate spec ID: `4115fa3ca56e3ac04b503459f8dd6d76d39df44bb1322c4d167d1ccbd631f073`.

### Model-specific hardware re-sizing

| Sizer output | Unchanged model | Paired candidate |
|---|---:|---:|
| Selected design target | 5,000 output tokens/s | 20,000 output tokens/s |
| Logical devices / replica | 7 | 7 |
| Required replicas | 3 | 1 |
| Deployed logical devices | 21 | 7 |
| Tensor arrays / device | 1 | 3 |
| HBM stacks / device | 4 | 4 |
| HBM capacity / replica | 672 GB | 672 GB |
| Fleet HBM capacity | 2,016 GB | 672 GB |
| Usable HBM bandwidth / replica | 17.92 TB/s | 17.92 TB/s |
| Effective compute / replica | 0.241 POP/s | 0.723 POP/s |
| Weight storage requirement | 16.400 GB | 3.683 GB |
| KV storage requirement | 154.619 GB | 38.655 GB |
| Total HBM requirement | 198.972 GB | 50.989 GB |
| Required HBM bandwidth | 16.028 TB/s | 15.897 TB/s |
| Estimated group active-hour cost | $0.914 | $0.918 |
| Selected-point sizing violations | None | None |
| Rejected higher target | 20,000 tokens/s: 26 devices required vs 16 allowed; 7 stacks/device required vs 4 allowed | None |

This is the clearest current example of the co-design hypothesis. The selected hardware group has the same seven devices and HBM footprint in both cases, but the candidate spends silicon on three tensor arrays per device instead of one. Lower weight and KV storage let one higher-throughput candidate replica replace three reference replicas at nearly the same modeled group-hour cost.

The design target is a hardware-sizing input, not achieved workload goodput. The study selects the lowest workload-weighted cost among SLO-passing, feasible hardware trials. The reference's feasible trials span 1,250 to 10,000 target output tokens/s; its 20,000 target is retained only in `rejected_hardware_trials` and never enters capacity planning or attribution. The candidate's lower target points miss the SLO or cost more, while its 20,000 target is feasible and selected.

The 672 GB reference group remains bandwidth-driven overprovisioning, not a claim that Qwen3-8B needs that much storage. Its analytical storage requirement is 198.97 GB and its declared bandwidth requirement is 16.03 TB/s at the selected 5,000-token/s design target. The candidate needs 50.99 GB and 15.90 TB/s at a four-times-higher design target. These requirements inherit an uncalibrated assumption of one sharded weight pass per decode batch plus full-context KV reads.

### H100 cost sensitivities

| Metric | Paired custom projection | Owned-H100 sensitivity | Public-H100 rental sensitivity |
|---|---:|---:|---:|
| Physical accelerators | 7 hypothetical devices | 8 H100s | 8 H100s |
| Input cost / 1M | $0.005671 | $0.091628 | $0.244678 |
| Output cost / 1M | $0.428709 | $1.406811 | $3.766468 |
| Minimum input price / 1M at 50% margin | $0.011341 | $0.183256 | $0.489356 |
| Minimum output price / 1M at 50% margin | $0.857419 | $2.813623 | $7.532935 |
| Simulated p95 TTFT | 450.86 ms | 3,753.57 ms | 3,753.57 ms |
| Simulated p95 TPOT | 6.69 ms | 33.94 ms | 33.94 ms |

Relative to the owned-H100 sensitivity, the nominal projection is 16.16x lower on input cost, 3.28x lower on output cost, and 5.34x lower on the realized token mix. This comparison is dominated by cross-hardware timing and TCO assumptions. It is a prioritization signal only.

### Simulated class SLOs

The paired candidate passes all 512 simulated requests and all three class objectives:

| Class | Requests | Simulated p95 TTFT | Simulated p95 TPOT | Pass |
|---|---:|---:|---:|---|
| Tool | 120 | 238.61 ms | 6.87 ms | Yes |
| Coding | 236 | 412.85 ms | 6.70 ms | Yes |
| Long agent | 156 | 520.96 ms | 6.62 ms | Yes |
| Aggregate | 512 | 450.86 ms | 6.69 ms | Yes |

Trace identity: `simulation-4115fa3ca56e3ac04b503459f8dd6d76d39df44bb1322c4d167d1ccbd631f073`.

## Exact factorial attribution

The 32-point factorial covers every subset of the five changes. Exact Shapley values therefore include topology and fleet-sizing interactions and reconcile to the full-stack delta. Positive percentages are savings as a fraction of the unchanged-model reference; negative percentages are regressions.

| Axis | Input standalone | Input Shapley | Output standalone | Output Shapley | Weighted standalone | Weighted Shapley |
|---|---:|---:|---:|---:|---:|---:|
| INT4 weights | -8.34% | +6.51% | +8.98% | -0.53% | +5.45% | +0.90% |
| FP8 KV | +6.96% | +23.70% | +33.12% | +12.42% | +27.80% | +14.72% |
| Four KV heads | +7.09% | +23.84% | +33.20% | +12.50% | +27.89% | +14.80% |
| FFN width 10,240 | -20.53% | -1.33% | +18.38% | +3.23% | +10.47% | +2.30% |
| Full-layer fusion | -19.80% | -4.32% | +12.66% | +3.55% | +6.06% | +1.95% |

Input, output, and weighted reconciliation errors are respectively `8.67e-19`, `5.55e-17`, and `0` dollars per million tokens. The sign differences between standalone and Shapley values are not evidence that isolated changes magically improve when combined. They show that feasible hardware re-sizing and capacity thresholds dominate the current analytical landscape. Any optimization ranking must be re-run after external calibration.

The most credible analytical mechanism is the KV path: the agentic trace has long cached contexts, so KV precision and KV-head count directly attack modeled HBM capacity and read bandwidth. It is also the highest-quality-risk path because both changes affect model numerics or architecture.

## Measured small-model INT4 evidence

The checked-in [`Qwen3-0.6B INT4 sweep`](../../validation/results/qwen3-0.6b-int4-sweep-v1.json) is the only measured model-side evidence in this study. It runs symmetric groupwise weight quantize-dequantize on CPU over 155 teacher-forced target tokens. It does not measure packed storage, a real INT4 kernel, throughput, latency, energy, cost, or task success, and it does not use the candidate's proposed rotation-assisted method.

None of group sizes 8, 16, 32, 64, or 128 passed every declared numerical gate. The group-128 point used by the analytical storage contract had 4.125 effective bits/weight and produced NLL delta `+0.2088`, perplexity ratio `1.2322`, logit RMSE `1.2728`, logit cosine `0.9259`, and top-1 agreement `0.7419`; it failed all five thresholds. Group size 8 was numerically closest but consumed six effective bits/weight and still failed RMSE and cosine.

This is negative evidence against naive INT4, not validation of W4. The analytical Qwen3-8B candidate remains quality-unvalidated because the measurement is on a different model scale, uses naive QDQ rather than rotation-assisted quantization, covers a small non-standard corpus rather than agent tasks, and says nothing about the candidate's simultaneous KV, KV-head, or FFN changes. Group-scale storage accounting is complete; model quality and executable packed-kernel evidence are not.

## Cost sensitivity and failure modes

The 243-scenario grid varies five independent axes at lower, nominal, and upper values:

| Assumption | Lower | Nominal | Upper | Provenance status |
|---|---:|---:|---:|---|
| NRE amortization units | 1,000 | 100,000 | 1,000,000 | Internal volume sensitivity; $300M total NRE |
| Utilization | 40% | 70% | 90% | Internal deployment sensitivity |
| HBM stack cost | $150 | $300 | $1,500 | Placeholder; vendor quote required |
| Wafer cost | $15,000 | $20,000 | $30,000 | Placeholder; foundry quote required |
| Effective silicon yield | 40% | 85.88% | 95% | Poisson die model × package yield |

Against the $0.091628/input-M and $1.406811/output-M owned-H100 assumptions:

- Projected input cost ranges from $0.004129 to $0.053344/M and is below the baseline in all 243 scenarios. The worst modeled advantage is 41.78%.
- Projected output cost ranges from $0.309889 to $4.102400/M and is below the baseline in 162 of 243 scenarios. In the worst case it is 191.61% more expensive, or 2.916x the baseline.
- At 1,000 amortization units, input costs range from $0.021689 to $0.053344/M, while output costs range from $1.663114 to $4.102400/M. All 81 input cases pass and all 81 output cases fail.
- At 100,000 units, output costs range from $0.322081 to $1.085075/M and all 81 output cases pass. At 1,000,000 units, they range from $0.309889 to $1.057644/M and all 81 pass.

The conclusion gate correctly returns `permitted: false` with blockers `quality_unmeasured`, `performance_fidelity_not_external`, and `hardware_sizing_not_validated`.

## Assumptions and omitted costs

The custom device is a logical analytical architecture, not a manufacturable chip. Current placeholders include 4 nm, 128x128 arrays, 24 GB/800 GB/s HBM stacks, 5 pJ/HBM byte, 50 ns memory-controller latency, a mesh NoC, 200 GB/s scale-up links, 100 ns link latency, and a Poisson yield model. Uniform tensor, memory, and request sharding ignores imbalance, pipeline bubbles, per-device tile timing, congestion, and contention.

The capital model includes analytical silicon, HBM, package/test, amortized NRE, and separate server TCO inputs. The hardware sizer explicitly excludes board and voltage regulation, host CPU/DRAM capital, rack network and cooling infrastructure, financing, operations, redundancy, and failures; the server TCO file adds coarse board, host, network, and rack allowances but does not turn the result into a vendor quote. HBM at the nominal $300/stack is particularly optimistic and is intentionally swept to $1,500.

The configuration source record links Qwen, NVIDIA H100, and public Fireworks pages. The Qwen3-8B fixture pins a revision identity but not a locally hashed Qwen3-8B weight file; it also does not pin downloaded source documents, access dates, or measured provider results. The small-model sweep separately records its exact Qwen3-0.6B weight SHA-256. All generated Qwen3-8B reports mark quality `unvalidated` and `production_claim_permitted: false`.

## Reproduction

Run from the repository root. Generated reports live under the gitignored `artifacts/` directory.

Validate the baseline fixture and reproduce the two H100 sensitivities:

```sh
cargo run -q -p foundry-cli -- validate configs/qwen3-8b-agentic-h100.json
cargo run -q -p foundry-cli -- capacity-plan configs/qwen3-8b-agentic-h100.json --oracle roofline --maximum-replicas 128 --hardware-group configs/hardware-groups/h100-sxm-4x-owned-tco-sensitivity.json --output artifacts/qwen3-8b/h100-owned.json
cargo run -q -p foundry-cli -- capacity-plan configs/qwen3-8b-agentic-h100.json --oracle roofline --maximum-replicas 128 --hardware-group configs/hardware-groups/h100-sxm-4x-public-rental.json --output artifacts/qwen3-8b/h100-public.json
```

Reproduce the unchanged-model reference and paired candidate:

```sh
cargo run -q -p foundry-cli -- codesign-study configs/qwen3-8b-agentic-h100.json --constraints configs/hardware-sizing-agentic-v0.json --server-tco configs/custom-server-tco-v0.json --oracle roofline --maximum-replicas 128 --output artifacts/qwen3-8b/factorial/baseline.json
cargo run -q -p foundry-cli -- codesign-study configs/qwen3-8b-agentic-h100.json --constraints configs/hardware-sizing-agentic-v0.json --model-variant configs/variants/qwen3-8b-paired-v0.json --kernel-spec configs/kernels/qwen3-full-layer-v0.json --server-tco configs/custom-server-tco-v0.json --oracle roofline --maximum-replicas 128 --output artifacts/qwen3-8b/factorial/full.json
```

Reproduce the complete factorial and attribution:

```sh
for mask in 0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do experiments/qwen3-8b/run_model_factorial_case.sh "$mask"; experiments/qwen3-8b/run_kernel_factorial_case.sh "$mask"; done
cargo run -q -p foundry-cli -- attribute-factorial experiments/qwen3-8b/factorial-full-stack.json --output artifacts/qwen3-8b/full-stack-attribution.json
```

Reproduce class SLO evaluation and the TCO sensitivity grid:

```sh
cargo run -q -p foundry-cli -- class-slo artifacts/qwen3-8b/factorial/full.json configs/workloads/qwen3-agentic-slo-v2.json --output artifacts/qwen3-8b/class-slo.json
cargo run -q -p foundry-cli -- sensitivity artifacts/qwen3-8b/factorial/full.json configs/sensitivity/qwen3-paired-v0-vs-owned-h100.json --output artifacts/qwen3-8b/sensitivity.json
```

The compact checked-in [`summary-v0.json`](summary-v0.json) records the exact headline values and evidence status. The full reports remain the authoritative machine output.

## Explicit no-go gates

Do not claim material inference-cost reduction, provider advantage, repeatable model-specific optimization, or tapeout readiness until all applicable gates pass:

1. **Analytical sizing feasibility, currently passed:** both selected points have zero sizing violations under the same search envelope. The hard exclusion of rejected points must remain in every study; this gate does not establish manufacturability.
2. **Model quality:** the unchanged checkpoint and every model change must pass the fixed agentic task-success non-inferiority threshold of 0.99, plus numerical and safety checks. The measured naive INT4 sweep failed, and KV-head and FFN changes require a real adapted or trained checkpoint.
3. **Kernel correctness and performance:** generated kernels must match reference numerics and be benchmarked on available hardware. Level 2 external simulators must calibrate compute, memory, network, area, energy, and candidate ordering before hardware conclusions.
4. **Serving baseline:** the identical checkpoint, precision, trace, prefix behavior, batch policy, and class SLOs must be measured on tuned current vLLM, SGLang, and TensorRT-LLM where supported. Provider endpoints must use the identical model and contract or be labeled non-comparable.
5. **Economic evidence:** replace HBM, wafer, yield, packaging, NRE, utilization, and server placeholders with quotes or independently reviewed estimates, including omitted operations, redundancy, financing, and incumbent improvement.
6. **Materiality:** achieve at least 1.5x measured cost reduction against the best tuned software baseline. A custom-hardware program additionally requires at least 4x launch-date advantage in the base case and 2x in a pessimistic joint scenario.
7. **Transfer:** retain at least 1.5x measured gain on a second model before calling this a platform. Nothing in this Qwen3-8B analytical study establishes transfer to a GLM-class model; that requires architecture-specific re-sizing, mapping, quality evidence, and calibration.

Until then, the defensible conclusion is: **the simulator has identified a plausible, KV-bandwidth-centered co-design hypothesis and quantified its economic dependence, but it has not established that the company can serve tokens materially cheaper than current providers.**
