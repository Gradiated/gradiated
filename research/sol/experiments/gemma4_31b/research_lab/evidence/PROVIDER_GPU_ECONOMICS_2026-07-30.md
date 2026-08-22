# Gemma 4 31B provider GPU economics — 2026-07-30

## Decision

At the current qualified H200 result (`0.625149101968745 s/request` for
4,214 prompt + 358 output tokens at 90% utilization), hardware procurement is
now at least as important as another small software gain.

Every `$1.00/GPU-hour` maps to approximately `$0.042202/M total tokens` on the
measured workload. With a 15% allowance for non-GPU serving overhead:

- an effective H200-equivalent rate below `$2.258/hour` beats the current
  cheapest OpenRouter listing (`$0.109576/M` on the measured token mix);
- a rate below `$1.806/hour` supports a 20% gross margin at that listing;
- the current `$3.25/hour` committed-capacity planning rate produces
  `$0.157730/M` all-in and ranks about ninth among the current OpenRouter
  endpoints;
- the current Nebius `$2.45/hour` preemptible reference produces
  `$0.118904/M` all-in and ranks about third;
- a provider-scale `$2.00/hour` rate produces `$0.097064/M` all-in and ranks
  first.

The campaign has not run Artificial Analysis's exact 10k-input, single-stream,
7:2:1 cache/input/output workload. The AA comparison below is therefore a
price sensitivity, not a scope-matched benchmark result.

## Measured and derived inputs

- Measured service time: `0.625149101968745 s/request`.
- Measured workload: 4,214 prompt and 358 output tokens per request.
- Measured cache-read share used for the OpenRouter blend: 12.7% of prompt.
- Capacity utilization: 90%.
- Cost factor:

  `1e6 / ((4572 / 0.625149101968745) * 3600 * 0.90)`
  `= $0.0422019365/M tokens per $1/GPU-hour`.

The 15% overhead case is a planning allowance for host CPU/RAM, storage,
networking, failed/retried work, and the control plane. Idle capacity is
already represented by the separate 90% utilization assumption. The allowance
excludes engineering payroll and OpenRouter's user credit-purchase fee.

## OpenRouter price ranking

OpenRouter says it passes provider inference prices through without markup.
The following blends use the campaign's 4,214/358 token geometry and 12.7%
prompt-cache share. If an endpoint supplies no cache-read price, cache reads
are conservatively charged at its normal input price.

| Rank | Endpoint | Representation | Retail blend, $/M total tokens |
|---:|---|---|---:|
| 1 | DeepInfra Turbo | FP4 | 0.109576 |
| 2 | CoreWeave | BF16 | 0.118793 |
| 3 | OpenInference | BF16 | 0.119576 |
| 4 | Chutes | FP4 | 0.132552 |
| 5 | Venice | BF16 | 0.135281 |
| 6 | DeepInfra | FP8 | 0.149576 |
| 7 | SiliconFlow | FP8 | 0.151142 |
| 8 | Morph | FP4 | 0.153335 |
| 9 | Parasail | FP8 | 0.159041 |
| 10–12 | Novita, Friendli, Crusoe | BF16/unknown | 0.160359 |

| Effective GPU rate | Our compute only, $/M | Raw rank | With 15% overhead, $/M | All-in rank |
|---:|---:|---:|---:|---:|
| 3.25 | 0.137156 | 6 | 0.157730 | 9 |
| 2.99 | 0.126184 | 4 | 0.145111 | 6 |
| 2.62 | 0.110569 | 2 | 0.127154 | 4 |
| 2.45 | 0.103395 | 1 | 0.118904 | 3 |
| 2.25 | 0.094954 | 1 | 0.109198 | 1 |
| 2.00 | 0.084404 | 1 | 0.097064 | 1 |
| 1.70 | 0.071743 | 1 | 0.082505 | 1 |

The cheapest OpenRouter row is FP4 while the campaign's current qualified
path is not a representation-matched FP4 result. CoreWeave and OpenInference
are the more informative BF16 retail comparators. Full GPQA-Diamond and
TauBench equivalence remains a separate deployment gate.

## Estimated provider GPU economics

Provider internal cost is not public. These are broad effective
H200-equivalent ranges, not claims about a provider's literal accelerator or
invoice. “Effective” intentionally combines the accelerator's hourly cost and
the throughput it can deliver relative to our H200 result.

| Provider class | Estimated effective $/H200-equivalent hour | Confidence | Public anchor / inference |
|---|---:|---|---|
| DeepInfra | 1.3–2.0 | Medium | Own inference-optimized infrastructure; advertises dedicated B300 at $1.98/GPU-hour on a five-year term. |
| CoreWeave | 1.8–2.6 | Medium-low | Public H200 spot is $20.93/hour per 8-GPU node, or $2.616/GPU-hour; its own fleet economics should be below customer spot pricing. |
| Novita | 1.5–2.4 | Medium | Public H100 bare metal is $1.70/GPU-hour and dedicated H200 endpoints are $2.99/GPU-hour. |
| Parasail | 1.5–2.4 | Low-medium | Dedicated multi-provider infrastructure, but no public matched rate. |
| OpenInference / Venice | 1.5–2.6 | Low | Hardware and procurement terms are undisclosed; range is anchored to current committed and bare-metal market rates. |
| Chutes | 0.9–1.8 | Low | Marketplace/distributed supply can be cheap, but the hardware and sustainable availability mix are unknown. |
| SiliconFlow | 0.8–1.8 | Low | Hardware may include region-specific NVIDIA or domestic accelerators; no public matched cost disclosure. |

At the midpoint of nearly every plausible provider-scale range, our current
software result would rank first on compute cost. This does **not** mean our
product would automatically rank first: competitors may have better throughput,
lower overhead, more aggressive quantization, higher cache reuse, or strategic
subsidies.

As a reverse check, if each provider had exactly our throughput, 15% non-GPU
overhead, and targeted a 20% gross margin, its maximum effective GPU rate would
be `$1.806/hour` for DeepInfra FP4, `$1.958/hour` for CoreWeave BF16, and
`$1.971/hour` for OpenInference BF16. Their actual rates could be higher if
their serving stack is faster than ours or lower if they carry more overhead
or margin.

## Artificial Analysis price sensitivity

Artificial Analysis currently ranks eight providers using a default 7:2:1
cache-hit/input/output price blend and reports 72-hour medians. Displayed
lowest blended prices are approximately:

| Rank | Provider | AA retail blend, $/M |
|---:|---|---:|
| 1 | Parasail | 0.14 |
| 2 | DeepInfra FP8 | 0.15 |
| 3 | SiliconFlow FP8 | 0.16 |
| 4–5 | FriendliAI, Novita | 0.17 |

Applying our existing workload's cost factor only as an unmatched sensitivity:

| Effective GPU rate | Compute only, $/M | Nominal AA rank | With 15% overhead, $/M | Nominal AA rank |
|---:|---:|---:|---:|---:|
| 3.25 | 0.137156 | 1 | 0.157730 | about 3–4 |
| 2.99 | 0.126184 | 1 | 0.145111 | about 2 |
| 2.45 | 0.103395 | 1 | 0.118904 | 1 |
| 2.00 | 0.084404 | 1 | 0.097064 | 1 |
| 1.70 | 0.071743 | 1 | 0.082505 | 1 |

Do not publish these as AA benchmark results. A valid AA ranking requires a
fresh 10k-input single-stream measurement with the AA cache/input/output mix
and token accounting.

## Sources

- OpenRouter endpoint API:
  https://openrouter.ai/api/v1/models/google/gemma-4-31b-it/endpoints
- OpenRouter provider page:
  https://openrouter.ai/google/gemma-4-31b-it/providers
- OpenRouter pricing FAQ:
  https://openrouter.ai/docs/faq
- Artificial Analysis provider page:
  https://artificialanalysis.ai/models/gemma-4-31b-non-reasoning/providers
- CoreWeave public pricing:
  https://www.coreweave.com/pricing
- DeepInfra infrastructure and dedicated B300 pricing:
  https://deepinfra.com/
- Novita bare-metal pricing:
  https://novita.ai/gpu-baremetal
- Novita dedicated endpoint pricing:
  https://novita.ai/es/dedicated-endpoint
- Local campaign contract: `research/sol/experiments/gemma4_31b/research_lab/CAMPAIGN.md`
- Shared GPU price inventory: `research/factory/data/gpu_prices.json`

## Uncertainty and falsification

- The named provider cost ranges are inferred and can be falsified by a
  scope-matched provider quote, hardware disclosure, or audited cost statement.
- Rank is highly sensitive to sustained utilization. At 75% rather than 90%,
  cost rises 20%.
- A different input/output/cache mix changes both the retail blend and serving
  throughput.
- A B200/B300 may have a higher literal hourly rate but a lower effective
  H200-equivalent rate.
- Subsidized retail prices cannot be used to infer sustainable GPU cost.
