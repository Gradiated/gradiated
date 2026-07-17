# H200 campaign economic-gate reconciliation

## Decision question

What completed-request throughput and measured cost thresholds must the active H200 SGLang-versus-vLLM experiment satisfy under the campaign's current request mix, `$3.25/GPU-hour` production planning rate, explicit utilization/headroom/non-GPU/reliability/storage factors, and `$0.000614-$0.000621` market frontier?

The active H200 brief inherited a `1.825` requests/s number derived for an H100-rate context. This project must distinguish a valid comparative `SGLang <= 0.90x vLLM` gate from the H200 market hurdle and prevent either from silently substituting for the other. It is independent `$0` analysis and must not delay, poll, or mutate the H200 owner.

## Authoritative evidence

- Campaign objective and market components: `../../CAMPAIGN.md`.
- Current market request costs and scenario factors: `../l40s_saturation_economic_gate/SATURATION_GATE.json` and `../exact_market_venue_decision_surface/MARKET_TARGET.json`.
- Fresh planning rates: `research/factory/data/gpu_prices.json` from the repository root.
- Active experiment and comparator: `../sglang_h200_matched_endpoint_falsifier/PROJECT.md`.
- Earlier H200/H100 rate-ratio bound: `../h200_bf16_bandwidth_economic_falsifier/H200_PACKET.json` and `BOTTLENECK_BOUND.json`.

Do not refresh prices while the shared inventory is fresh. Do not infer throughput from bandwidth or transfer H100/L40S measurements to H200.

## Required result

Emit `H200_ECONOMIC_GATE.json` and `DECISION.md` with:

- ideal, planning-base, and conservative required completed requests/s at the H200 planning rate and its production range;
- the formula and every all-in factor, plus the raw GPU-only threshold;
- separate campaign-mix and 10K single-stream interpretation;
- the actual-provider-rate accounting formula without treating experiment/preemptible price as production cost;
- the independent matched comparator gate (`candidate cost/request <= 0.90x control`) and a combined promotion rule;
- an explicit disposition of the inherited `1.825` requests/s value.

Return a typed correction or confirm the existing number. This analysis interprets later measured endpoint telemetry; it is not a launch gate and makes no performance, quality, or provider claim.

## Budgets

- Wall clock: 25 minutes.
- Compute: 0.5 local CPU-hour; no GPU.
- Storage: 256 MiB project-local; no shared `/tmp`.
- Spend: `$0`; provider mutation, checkpoint reads, image pulls, compilation, CUDA, endpoint, and quality execution are forbidden.
