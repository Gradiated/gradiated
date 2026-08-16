# Gemma 4 31B OpenRouter cost position — 2026-07-18

## Question and decision

How far has the lab moved from its first valid exact-mix stock endpoint, and where does the current retained endpoint sit against the median and cheapest currently active paid OpenRouter provider for `google/gemma-4-31b-it`?

Decision use: quantify the remaining economic gap and avoid treating an invalid nearly-all-cache-hit run as the campaign baseline. This comparison is falsified by a newer scope-matched endpoint terminal, a changed committed H200 planning rate, or a refreshed OpenRouter endpoint set or price.

## Scope

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Workload: 4,214 prompt tokens and 358 output tokens per request, comprising 3,679 fresh prompt tokens and 535 cache-read tokens (12.6958% of prompt tokens).
- Local runtime/hardware: pinned SGLang v0.5.12, one H200, c32, BF16 weights, FP8-E5M2 KV.
- Production planning rate: `$3.25/H200-hour` from the campaign's committed-rate economic contract.
- Provider population: OpenRouter endpoints with `status == 0` at retrieval. Free and non-active endpoints are excluded. If an endpoint omits a cache-read price, cache-read tokens are charged at its ordinary prompt price.
- Non-scope: redundancy, idle capacity, storage, networking, orchestration, support, OpenRouter fees, provider margin, or quality equivalence. Local figures are saturated raw GPU compute floors, whereas OpenRouter prices are retail.

## Sources

| Source | Retrieved | Evidence type | Use |
|---|---:|---|---|
| `https://openrouter.ai/api/v1/models/google/gemma-4-31b-it/endpoints` | 2026-07-18T18:32Z | OpenRouter-reported live API | Active endpoint status and prompt/completion/cache pricing |
| `projects/gemma4_background_serving_frontier/artifacts/exact-mix-c32-20260718t1729z/TERMINAL.json` | local | Measured | First valid stock exact-mix c32 control; SHA-256 `6508e309d09a1ab04daa50c33243062843836bb5259ce107f387603008f65d0f` |
| `projects/gemma4_h200_fused_qk_norm_rope_endpoint/artifacts/fused-qk-norm-rope-c32-canonical-20260718t1817z/TERMINAL.json` | local | Measured | Current retained dynamic-chunking plus fused-QK/RoPE c32 endpoint; SHA-256 `1a7e778eff080bf2eec27da939ea85a894ea9884036bdebd562af371405e78c3` |
| `CAMPAIGN.md` | local | Analytical contract | Workload and committed H200 planning rate |

## Method

For each provider, request retail cost is:

`3,679 × fresh-input price + 535 × cache-read price + 358 × output price`.

The provider median is the ordinary median across the ten endpoints reporting `status == 0` at retrieval, after sorting by request retail cost. The local saturated compute floor is:

`service seconds/request × $3.25 / 3,600`.

Blended dollars per million total tokens divide request cost by 4,572 total tokens and multiply by one million. This total-token blend is used only to make the mixed workload compact; component prices remain the underlying comparison.

## Result

| Position | Seconds/request | Dollars/request | Blended dollars/M total tokens | Versus active median | Versus active cheapest |
|---|---:|---:|---:|---:|---:|
| First valid stock c32 | 0.969888 | $0.000875594 | $0.191512 | 19.43% higher | 42.39% higher |
| Current retained c32 | 0.919457 | $0.000830066 | $0.181554 | 13.22% higher | 34.99% higher |
| OpenRouter active median | n/a | $0.000733160 | $0.160359 | baseline | 19.23% above cheapest |
| OpenRouter active cheapest: WandB BF16 | n/a | $0.000614930 | $0.134499 | 16.13% below median | baseline |

WandB's listed component prices are `$0.12/M` fresh input, `$0.09/M` cache read, and `$0.35/M` output. The active median request cost is the common Novita/Friendli point at `$0.14/M` input and `$0.40/M` output with no lower cache-read rate listed.

The retained changes improve scope-matched service time and saturated raw compute cost by 5.1997%. They have closed 31.96% of the original raw-compute gap to the active median and 17.47% of the gap to the active cheapest endpoint.

The earlier `0.363303 s/request` result is excluded: subsequent telemetry showed only one uncached prompt token per request, making it a nearly fully cache-read lower bound rather than the intended workload.

## Uncertainty and limitations

- The local number is more favorable than a deployable production cost because it assumes saturated useful H200 time and excludes all non-GPU overhead and margin. Therefore the true launch gap is larger unless a cheaper placement or additional throughput gain offsets those costs.
- OpenRouter endpoint status and price are live and can change within minutes. OpenInference advertised a lower `$0.10/M` input price but had non-active status `-2` at the calculation timestamp, so it was excluded from the active-provider comparison.
- Providers use different representations, context limits, feature support, reliability, and quality. The local endpoint has not yet passed GPQA-Diamond and TauBench in its exact production representation.
- The currently running Torch-compile arm is not included until it emits a valid exact-mix terminal.

## Next action

Continue stacking simple valid endpoint gains, but prioritize mechanisms or hardware placement capable of removing at least the remaining 13.22% raw-compute gap to median plus production overhead. Refresh the OpenRouter API before each market claim and recalculate after the Torch-compile terminal.
