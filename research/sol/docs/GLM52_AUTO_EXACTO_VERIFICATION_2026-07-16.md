# GLM-5.2 Auto Exacto verification brief

Date: 2026-07-16

## Question and decision

Can we predict whether a future GLM-5.2 endpoint will be classified as Auto
Exacto good, insufficient-data, or deprioritized, and are the GPQA-Diamond and
Tau-Bench Verified Airline scores on OpenRouter's model page relevant to token
share?

Decision: yes, they are directly relevant and should be added to the provider
share model. We can preflight the endpoint against the same public benchmark
implementations, but exact tier verification requires OpenRouter's run
configuration or provider dashboard plus production tool-call telemetry.

## Scope and falsifier

Scope: standard GLM-5.2 (`z-ai/glm-5.2-20260616`) endpoints on OpenRouter as
retrieved at 2026-07-16T13:31:24Z. This does not establish the endpoint's future
tier, because our endpoint and its serving configuration do not yet exist.

Hypothesis: endpoint-specific benchmark results explain material provider-share
variation left unexplained by price and uptime. This is weakened if low benchmark
outliers receive tool traffic comparable to matched-price, matched-health good
providers, or if our controlled reproduction does not predict OpenRouter's
provider-dashboard scores.

## How Auto Exacto currently works

For requests containing tools, OpenRouter recomputes provider classification
roughly every five minutes from three signal classes:

1. throughput;
2. production tool-call correctness (valid JSON, supplied tool name, schema);
3. recurring GPQA-Diamond and Tau-Bench Verified Airline evaluations.

Signals are compared within the providers serving that model using median and
median absolute deviation. Documented deprioritization sensitivities are one
standard deviation for benchmark accuracy, 1.5 for throughput, and two for
tool-call success. Providers are ordered good, insufficient data, then
deprioritized; price ordering remains within a tier. New endpoints require at
least 100 general requests in 30 minutes and 200 tool requests in two hours to
leave the insufficient-data state.

## Current GLM-5.2 benchmark evidence

The public benchmark endpoint reports a 32-day lookback. Excluding the
`auto-routing` aggregate, the current distributions are:

| Signal | Providers | Median | MAD | Robust-sigma approximation | Approx. median - 1 sigma |
|---|---:|---:|---:|---:|---:|
| GPQA-Diamond | 26 | 87.01% | 2.34 pp | 3.46 pp | 83.55% |
| Tau-Bench Verified Airline | 25 | 72.59% | 1.77 pp | 2.63 pp | 69.96% |

The exact conversion OpenRouter uses between MAD and the documented “standard
deviation” threshold is not exposed. The final column uses the conventional
`1.4826 × MAD` robust-sigma conversion and is analytical, not an OpenRouter
published threshold. A safe preflight target is therefore at or above the peer
median, not merely above this estimated cutoff.

Selected endpoint-level results and contemporaneous public token shares:

| Provider | GPQA | Tau Airline | Token share | Interpretation |
|---|---:|---:|---:|---|
| Alibaba | 89.86% | 71.00% | 29.92% | Above estimated cutoffs |
| StreamLake | 89.68% | 73.67% | 27.41% | Above both medians/cutoffs |
| Novita | 89.41% | 74.21% | 10.86% | Above both medians/cutoffs |
| Z.AI | 88.55% | 74.94% | 9.94% | Above both medians/cutoffs |
| SiliconFlow | 86.47% | 72.81% | 7.98% | Above estimated cutoffs |
| Fireworks | 88.00% | 68.88% | 3.44% | Tau result near/below estimated cutoff |
| Wafer | 71.72% | 66.72% | 0.34% | Severe GPQA outlier; Tau also low |
| DeepInfra | 77.38% | 59.80% | 0.003% | Severe outlier on both |
| Cloudflare | 67.81% | 50.09% | 0.185% | Severe outlier on both |

This is observational rather than causal: price, tier, request constraints,
capacity, and endpoint age also differ. However, the direction is consistent
with benchmark tiering being a major omitted variable. The benchmark scores
cannot explain non-tool traffic, which remains price-weighted.

## What each benchmark verifies

- **Tau-Bench Verified Airline is the more direct tool-routing test.** It exercises
  multi-turn tool selection, argument/schema correctness, policy following, and
  end-to-end agent behavior. It is highly sensitive to chat-template and tool
  parser defects—the failure mode OpenRouter says is more common than
  quantization itself.
- **GPQA-Diamond is a serving-fidelity and reasoning canary.** It can detect a
  provider whose quantization, model modification, reasoning configuration,
  tokenizer, chat template, sampling, or engine behavior has damaged the model.
  It is not itself a tool-use benchmark, but OpenRouter uses it as a second
  provider-variance axis and documents benchmark outliers as deprioritization
  inputs.
- **Neither replaces production tool-call telemetry.** Auto Exacto separately
  measures valid JSON, valid supplied tool names, and schema compliance on real
  traffic. We must test those at the API serialization/parser boundary.

## Verification plan for our endpoint

1. Freeze the exact checkpoint/model modification, serving engine, tool parser,
   chat template, tokenizer, reasoning defaults, sampling parameters, and API
   request/response transformations.
2. Run GPQA-Diamond through Groq OpenBench against the exact production endpoint.
3. Run the public AWS-AGI Tau2-Bench-Verified Airline dataset against the same
   endpoint, preserving the user simulator and task split once OpenRouter gives
   us its exact configuration.
4. Run a parser conformance corpus that verifies JSON, supplied tool name,
   schema, parallel calls, escaping, streaming boundaries, and malformed-input
   behavior.
5. Gate launch on GPQA >=87%, Tau Airline >=73%, near-100% parser
   conformance, and approximately >=45 output tokens/second under OpenRouter's
   measurement geometry. The throughput target is the current 28-endpoint
   public median (44.59 tok/s), not a user latency SLO. These are conservative
   current-peer targets, not guarantees of good-tier admission.
6. On onboarding, obtain provider-dashboard access and the exact benchmark
   configuration. Compare our local scores to OpenRouter's scores before relying
   on the local preflight.
7. After 100 general and 200 tool requests, record actual tier, benchmark scores,
   throughput, tool-call success, and routed share. Refresh the revenue model
   immediately; do not wait for a daily aggregate.

## Sources

| Source | Revision/date | Retrieved | Evidence type |
|---|---|---|---|
| [OpenRouter Auto Exacto announcement](https://openrouter.ai/blog/announcements/auto-exacto/) | 2026-03-12 | 2026-07-16 | Vendor-reported algorithm and benchmark method |
| [OpenRouter provider integration](https://openrouter.ai/docs/guides/community/for-providers) | live | 2026-07-16 | Official current thresholds and admission windows |
| [GLM-5.2 benchmark scores API](https://openrouter.ai/api/frontend/v1/stats/benchmark-scores?permaslug=z-ai%2Fglm-5.2-20260616&variant=standard&timeRange=3d) | 32-day payload | 2026-07-16 | Measured public provider results |
| [AWS-AGI Tau2-Bench-Verified](https://github.com/amazon-agi/tau2-bench-verified) | repository main | 2026-07-16 | Primary benchmark dataset/implementation |
| [Groq OpenBench](https://github.com/groq/openbench) | repository main | 2026-07-16 | Primary evaluation harness |

## Limitations and next action

OpenRouter does not expose the exact per-run prompts, seeds, sampling defaults,
reasoning effort, task subset, user-simulator configuration, robust-z conversion,
or current tier audit trail publicly. Public benchmark run counts are small
(typically one to nine), and the public score may aggregate provider variants.

Next action: add benchmark scores and inferred tier state as time-varying features
in the OpenRouter share panel, and package the two preflight evaluations once an
exact GLM-5.2 production endpoint is available. Kill the assumption that local
preflight predicts tier if it misses OpenRouter's provider-dashboard score by
more than two percentage points on either benchmark.

## Share-model validation result

The benchmark enrichment matched 231 of 314 endpoint rows (73.6%) across the
frozen 30-model panel, with no collection failures. The candidate uses
within-model robust GPQA and Tau shortfalls plus an explicit missing-data feature,
interacted with each model's public tool-traffic proxy.

| Holdout | Stock model TV | Benchmark model TV | Relative change |
|---|---:|---:|---:|
| Leave one model out, mean | 44.82% | 44.50% | 0.72% better |
| GLM-5.2 held out | 55.81% | 53.43% | 4.27% better |
| Unseen provider, mean | 42.43% | 40.88% | 3.64% better |

For GLM-5.2, provider rank correlation improves from 0.788 to 0.845 and mean
endpoint-share absolute error improves from 3.99 to 3.82 percentage points. The
candidate still predicts the largest provider incorrectly and remains far from
a precise pre-launch share forecast.

Adding the same benchmark features after current request counts are available
does not pass its gate: mean panel TV changes from 12.55% to 12.67% (0.94%
worse), although GLM TV changes slightly from 18.329% to 18.273%. Request counts
already encode most live tier effects. The production nowcast therefore retains
the simpler request-telemetry model; benchmark scores remain diagnostics and
pre-launch priors.
