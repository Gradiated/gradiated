# Shared GPU price inventory refresh — 2026-07-22

## Decision

Keep the existing planning rates and evidence ranges for the five existing accelerator entries. Refresh the public source bindings and timestamps; retain the MI355X reserved-floor context as stale directional evidence rather than manufacture a committed-price claim.

## Scope and falsification

Scope is only the existing `research/factory/data/gpu_prices.json` rows: L40S, H100 SXM, H200 SXM, B200 SXM, and MI355X. The decision would be falsified by a changed current public rate or a current written 12–24 month, 8–64 GPU non-preemptible quote that matches an inventory row. No provider resource was created or claimed.

## Evidence

| Source | Retrieved (UTC) | Evidence type | Result |
| --- | --- | --- | --- |
| [Nebius AI Cloud pricing](https://nebius.com/prices) | 2026-07-22T21:42:00Z | vendor-reported | L40S AMD $0.74 preemptible / $1.55 on-demand; H100 $2.15 / $3.85; H200 $2.45 / $4.50; B200 $3.95 / $7.15 per GPU-hour. Advertises up to 35% off on-demand for large multi-month commitments. |
| [GPUs.io MI355X listing](https://gpus.io/en/gpus/mi355x) | 2026-07-22T21:42:00Z | independent-market-listing | One TensorWave on-demand offer at $2.95/GPU-hour; no committed-capacity rate. |
| [TensorWave MI355X access](https://go.tensorwave.com/) | 2026-07-22T21:42:00Z | vendor-reported | Request-based MI355X access; no public committed-capacity price. |
| [Prior Dell directional context](https://infohub.delltechnologies.com/en-sg/t/third-party-analysis-8/) | 2026-07-15T13:00:00Z | third-party-directional, stale | Current landing page no longer exposes the prior $2.29/GPU-hour reserved-floor claim. Retained only as explicitly stale context, never as the planning base case. |
| `glm47_l40s_measured` summary | 2026-07-15T13:00:00Z | measured | Historical actual L40S VM-plus-disk experimental rate remains $0.8581222/hour; retained as a measurement, not recast as current market pricing. |

## Method and result

Updated source IDs/timestamps in the shared inventory, retained each evidence type and the pre-existing separation of experimental rates from committed production planning, then ran:

```sh
PYTHONPATH=research/factory/src python3 -m grad_research gpu-prices --require-fresh
```

The command reports `fresh: true` with all five existing rows valid. Planning rates are unchanged because current public rate points are unchanged and neither vendor supplies a matching written quote.

## Uncertainty and next action

The committed production figures remain derived planning assumptions, not quotes. The MI355X lower directional floor is stale and excluded from the base-case calculation. Refresh within seven days, or immediately when an applicable written provider quote arrives.
