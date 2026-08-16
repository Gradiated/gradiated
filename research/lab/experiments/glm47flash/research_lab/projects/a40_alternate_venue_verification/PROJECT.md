# A40-class alternate venue verification

## Question

Is an A40 or RTX A6000-class 48 GiB GPU actually orderable now from a non-RunPod provider at an all-in rate that preserves a conservative path to the campaign's 5% and $0.60/M cost gates?

## Why it matters

The A40 remains the strongest hardware-economic prior: at the catalog-only $0.44/hour rate it needs 192.022 output tok/s for the 5% gate and 203.704 for $0.60/M, while the analytical bandwidth proxy is 286.7 tok/s. The RunPod control plane was inaccessible, which closes that provider path but not the hardware mechanism. A targeted live-availability search can establish whether a different experimental or production venue exists before the lab abandons the candidate.

## Relevant evidence

- `lower_cost_hardware_screen/SCREEN_2026-07-15.json`: 46,068 MiB historical device residence, A40/A6000 break-even calculations, and claim limits.
- `lower_cost_hardware_screen/PROVIDER_READONLY_DIAGNOSTIC_2026-07-15.json`: RunPod REST catalog paths unsupported and GraphQL denied; no capacity conclusion.
- Current AWQ bytes total 20.17 GB, but exact 48 GiB residence and throughput still require a matched load/measurement.
- Measurement venue and production placement must be evaluated separately.

## Scope

Use one zero-cost researcher turn to check at most three non-RunPod provider paths through current official public catalogs, documented availability APIs, status/capacity pages, or reproducible marketplace listings. Target only NVIDIA A40 or RTX A6000 48 GiB-class SKUs. For each path, bind provider, exact SKU, memory, region, purchase model, current orderable/stock signal, retrieval time, base hourly rate, minimum rental, storage, transfer/network, interruption/recovery terms, and orchestration assumptions. Do not treat an undated marketing page or price table alone as availability.

Normalize each credible path with a conservative lifecycle allowance and calculate the required sustained output tok/s for <=$0.6365/M and <=$0.60/M. Separately name (1) a safe measurement venue with readable capacity and (2) a plausible production placement/rate; they may differ. State the exact authority and provider adapter needed for a future create. If public evidence cannot establish orderability, retain the typed/access limitation and close that provider path rather than inferring capacity.

Do not use credentials, create/reserve hardware, contact sales, retry RunPod, benchmark, transfer model bytes, or broaden into a generic catalog. Budget is $0 with no provider ownership.

## Available resources

Use official provider sources and APIs, shared evidence tools, current hardware-screen artifacts, NVIDIA specifications, `campaign_100`, and current campaign economic formulas.

## Portfolio-changing result

One actually orderable <=$0.50/hour 48 GiB path with a conservative <=266.829 tok/s 5%-gate requirement earns a later exact-load/c8 measurement after provider-adapter admission. A higher rate, unreadable capacity, absent orderability, or excessive all-in overhead closes that provider path. No qualifying venue closes placement discovery for this campaign while leaving A40 performance itself unmeasured.
