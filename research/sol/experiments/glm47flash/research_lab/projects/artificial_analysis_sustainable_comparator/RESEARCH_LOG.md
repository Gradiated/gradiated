# Research log

Delegated 2026-07-15. No experiment has run yet.

## 2026-07-15 — Live exact-variant market reconciliation and lifecycle falsifier

**Question.** Does measured current-AWQ L40S c16 remain cheaper after sustainable lifecycle costs, using the exact non-reasoning Artificial Analysis page and preserving the earlier same-day comparator?

**Action.** Retrieved the distinct live non-reasoning page and ran the reproducible extractor/calculator in `compute_comparator.py`; no provider was invoked. The page identifies GLM-4.7-Flash (Non-reasoning), Amazon and Novita only, with input $0.07/M, output $0.40/M, reported 7:2:1 blended $0.103/M, and P50/72-hour output speeds 206.38 and 92.15 tok/s. Neither provider publishes a cache-hit price, so the 8:1 normalization charges cached input at the published input rate. The earlier reasoning page’s DeepInfra $0.01/$0.06/$0.40 components were retained as a separate historical variant, not silently merged.

**Evidence.** [COMPARATOR_ECONOMICS_2026-07-15.json](COMPARATOR_ECONOMICS_2026-07-15.json) contains the source URL, retrieval timestamp, HTML SHA-256 `fb015657e86a9819da65d99930bac859c02acfb09ba3a82c9782c91ef4b6da50`, extracted facts, cache-fraction sensitivity, measured c16 inputs, and break-even equations. The live non-reasoning strict hurdle is $0.960/M output at 8:1; the historical reasoning/DeepInfra hurdle is $0.568889/M at 7/9 cached input. c16 is $0.445308/M steady state at 535.286 tok/s. With `sustainable = 0.445308 * (1 + lifecycle_overhead) / productive_utilization`, c16 needs >=46.4% utilization with no overhead for the live hurdle and tolerates <=115.6% overhead at 100% utilization. Against the historical hurdle it needs >=78.3% utilization and tolerates <=27.8% overhead. The observed 1,412.452-second session versus a 61.216-second c16 productive batch implies 20 batches/session to beat the live hurdle and 84 to beat the historical hurdle (rounded up).

**Interpretation.** The live exact non-reasoning market comparison supports a conditional sustainable c16 economic lead under a plausible background utilization envelope, but the historical DeepInfra result is a materially stricter and variant-mismatched bound. At 10% lifecycle overhead c16 is $0.490/M, below both hurdles; the historical bound leaves only 17.5% headroom. Interruption, reload, retries, storage, network, and orchestration remain modeled as lifecycle overhead rather than measured provider costs. Absolute quality remains the campaign-wide blocker; no provider-matched or quality-adjusted claim is permitted.

**Next move.** Keep c16 as the quality-conditional economic leader under the live non-reasoning range, but require quality calibration and a measured lifecycle/utilization production envelope before a business claim. Do not spend another comparator turn unless the Artificial Analysis variant or cache-price state changes.
