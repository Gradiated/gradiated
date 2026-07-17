# Artificial Analysis and sustainable-cost reconciliation

## Question

Does the measured current-AWQ L40S c16 point remain cheaper than the live exact-model API market after converting both sides to the campaign's 8,192-input/1,024-output denominator and adding sustainable self-hosting utilization, interruption, reload, storage, retry, and orchestration costs?

## Why it matters

The c16 arm measured 535.286 output tok/s at a productive-hour rate of $0.445308/M output tokens, but that is not yet a sustainable all-in claim. The campaign snapshot retrieved earlier on 2026-07-15 names DeepInfra at $0.059/M blended and $0.59/M output-equivalent under Artificial Analysis's 7:2:1 cache-input-output mix. A later live exact non-reasoning page now lists only Amazon Bedrock and Novita at $0.10/M blended, with Amazon at 211.3 tok/s. Variant, provider-set, and recency drift must be resolved before setting the market hurdle.

## Scope

Run one $0 source-backed economic falsifier. Start from Artificial Analysis's exact GLM-4.7-Flash non-reasoning provider comparison and capture retrieval time, URL, model/variant identity, all listed providers, cache-hit/input/output component prices, default 7:2:1 blend, output speed, latency, workload token geometry, concurrency, and P50/72-hour representation. Preserve a bounded source snapshot or reproducible extraction with hashes. Reconcile why the campaign's earlier same-day reasoning/default page exposed DeepInfra while the live non-reasoning page exposes Amazon and Novita; do not silently replace the authoritative campaign snapshot.

Normalize each provider to both Artificial Analysis's 7:2:1 mix and the campaign's actual 8:1 input-output workload under explicit cache-hit fractions, including material cache-write/storage charges when published. Separately convert the measured c16 result to sustainable all-in $/M output with sensitivity over productive utilization, background queue fill, measured 1,412.452-second setup/session behavior, checkpoint reload frequency, preemption/interruption, retries, disk, public IPv4/egress, orchestration, and a reasonable production amortization horizon. Calculate the minimum productive utilization and maximum lifecycle overhead at which c16 still beats the strictest currently supported provider hurdle.

Do not invoke a provider, infer quality equivalence, compare Artificial Analysis single-request output speed to aggregate c16 throughput as if matched, or alter the campaign target. Label the current-AWQ result quality-conditional and separate measured, vendor-listed, Artificial Analysis-measured, derived, and assumed evidence.

## Available resources

- Artificial Analysis exact non-reasoning provider page and performance methodology.
- `CAMPAIGN.md` external-comparator snapshot.
- `nebius_current_awq_c16_direct` summary, telemetry, request rows, setup phases, and cost evidence.
- Historical allocation/reload/preemption evidence under `campaign_100` and shared factory tools.

Produce a machine-readable comparator/economic artifact, reproducible extraction/calculation code, and a concise research-log decision.

## Portfolio-changing result

If conservative sustainable c16 cost cannot beat the strictest live/snapshotted exact-model hurdle, the campaign needs another cost intervention despite its productive-hour win. If it clears with a defensible utilization/lifecycle envelope, retain c16 as the quality-conditional economic leader and make quality calibration the sole business-claim blocker. Any unresolved provider-variant conflict must yield a bounded range, not a chosen favorable comparator.
