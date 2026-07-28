# Frontier eligibility decision — 2026-07-25

The new CoreWeave and OpenInference rows justify a **nominal $0.119/M frontier**, not one authoritative production hurdle. Both rows bind the exact OpenRouter model ID, BF16 quantization, context, prices, status metadata, and listed API parameters. They do not bind the campaign checkpoint revision, quality, current throughput, latency, capacity, or request-level reliability. OpenInference also advertises only an 8,192-token maximum completion in the frozen row; CoreWeave advertises 262,144.

Venice remains the strongest capability-listed cache-specified comparison at **$0.135281/M**. Artificial Analysis remains a separate methodology-matched reference at **$0.138/M** using a 7:2:1 blend, 10K input, single stream, and 72-hour medians. Its Parasail components are exposed, but its benchmark is not the campaign workload and does not establish exact endpoint equivalence.

The retry/failure sensitivity is deterministic and tier-local. For independent per-attempt failures, expected cost scales as `1/(1-p)`; CoreWeave can tolerate 0.6548% independent failure probability before crossing OpenInference’s nominal price, 12.1882% before Venice, and 13.9184% before AA. For one-extra-attempt correlated episodes affecting fraction `q`, the corresponding bounds are 0.6592%, 13.8799%, and 16.1688%. These are synthetic overhead bounds, not uptime interpretations. H100 continuous economics has only 3.1160% independent or 3.2162% one-extra correlated tolerance against AA; discrete H100 is already above AA before overhead.

Tier decision:

- Nominal: CoreWeave and OpenInference are eligible as **nominal price observations**.
- Capability-listed: CoreWeave, OpenInference, and Venice are eligible as **listed-feature observations**, with missing revision/performance/quality/capacity fields.
- Methodology-matched: Artificial Analysis is eligible only as a **separate methodology reference**, not a campaign endpoint.
- Continuous H100: eligible only as an **analytical pooled-capacity bound**.
- Discrete H100: eligible only as an **analytical exact-trace fleet bound**, and it fails the current retail frontier economically.

The campaign should retain tiered hurdles: nominal `$0.119/M`, cache-specified capability `$0.135/M`, AA methodology `$0.138/M`, and the two separate H100 analytical values. No provider, GPU, or endpoint owner was touched.

Evidence and verification are in [FRONTIER_ELIGIBILITY_20260725.json](FRONTIER_ELIGIBILITY_20260725.json); all bound hashes and frozen raw captures are recorded there.
