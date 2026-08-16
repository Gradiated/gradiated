# Research log

## 2026-07-15 — zero-cost placement screen

- Question: Can a currently catalog-listed, single-GPU 48+ GiB placement beat the V21 L40S control by 5% while requiring no more than 75% of its measured 355.772 output tok/s?
- Action: Read the project contract, campaign economics, retained V21 summary and runner constants; queried current official RunPod pricing/GPU catalog and NVIDIA hardware specifications. No provider mutation or paid call was made. Calculated exact break-even rates and memory headroom.
- Evidence: The current RunPod catalog lists A40 ($0.44/h), RTX A6000 ($0.49/h), RTX 6000 Ada ($0.77/h), L40 ($0.82/h), L40S ($0.99/h), A100 PCIe ($1.39/h), and A100 SXM ($1.49/h). At the $0.6365/M target, required output rates are respectively 192.022, 213.843, 336.039, 357.860, 432.050, 606.616, and 650.257 tok/s. Only A40 and RTX A6000 pass the <=266.829 tok/s preliminary screen; A40 is nominated because it leaves the largest all-in cost margin.
- Feasibility: V21 measured 46,068 MiB device residence (44.988 GiB), leaving about 3.012 GiB on a nominal 48-GiB device at the same residence. A40 has 48 GiB and 696 GB/s bandwidth versus L40S 864 GB/s. A simple bandwidth-bound extrapolation is about 286.7 tok/s, above A40's 192.022/203.704 thresholds; this is an analytical plausibility check, not a performance claim.
- Interpretation: A40 is a decision-relevant conditional lead, not an accessible placement result: capacity was not verified and catalog prices are vendor-reported. At 75% of V21, A40 tolerates $0.1714/h overhead for the 5% gate and $0.1363/h for the strong gate. Transfer, storage, retry, interruption, and orchestration could consume this margin.
- Next move: If provider ownership later confirms one A40 placement at the catalog rate, run exactly one matched V21 background workload with memory/load as the first gate, then quality/SLO and throughput. If A40 cannot be capacity-confirmed, close the alternate-hardware branch; do not infer a gain from the catalog.

See [SCREEN_2026-07-15.json](./SCREEN_2026-07-15.json) for the compact calculation and provenance record.

## 2026-07-15 — A40 capacity preflight closed

- Question: Can the nominated A40 be admitted to the one matched V21 measurement without making an unsupported capacity assumption?
- Action: Used the existing RunPod driver for a read-only `/v1/pods` inventory check and queried the documented GPU catalog surfaces. No create, reservation, or other mutation was issued.
- Evidence: `/v1/pods` returned HTTP 200 with zero pods. `/v1/gpu-types` and `/v1/billing` returned HTTP 400 because those paths do not exist in the current REST specification. The documented GraphQL `gpuTypes(input: {id: "NVIDIA A40"})` availability query returned HTTP 403 with `error code: 1010`.
- Interpretation: This is a typed provider control-plane/authorization failure, not evidence that A40 capacity is absent. It prevents exact capacity and provider-returned-rate preflight, so creating a pod would violate the project’s fail-closed contract. The A40 branch is closed at zero cost; the analytical lead remains unmeasured and must not be promoted.
- Next move: None within scope. Do not retry the same surfaces, create another SKU, or infer a result from the public catalog.

See [PROVIDER_READONLY_DIAGNOSTIC_2026-07-15.json](./PROVIDER_READONLY_DIAGNOSTIC_2026-07-15.json) for bounded redacted provider evidence.
