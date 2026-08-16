# Research log

## 2026-07-17 — exact market normalization and typed fallback

Question: what current exact-model component target and safe venue fallback should the portfolio use while the Nebius L40S correction runs?

Action: captured the exact OpenRouter endpoint feed and Artificial Analysis provider page; normalized current prices to 4,214 prompt / 358 output tokens with 12.7% prompt cache reads; performed one read-only RunPod control-plane check. No provider was created, reserved, polled for readiness, or mutated.

Measured evidence: OpenRouter exposes 15 exact-model endpoints. WandB is $0.12/$0.09/$0.35 per million fresh/cache/output and normalizes to $0.000614925/request ($0.134498/M total tokens). DeepInfra FP8 normalizes to $0.000614287/request ($0.134358/M) while its cache component is missing and conservatively charged at fresh input. Artificial Analysis lists eight providers, a $0.14/M lowest 7:2:1 blend, 10K single-stream methodology, and Parasail as cheapest; its rendered capture does not expose component prices. RunPod returned HTTP 200 with zero pods; the attempted `/v1/gpus` read returned HTTP 400 invalid path, so no stock claim is made.

Interpretation: the current retail hurdle is about $0.134–$0.136/M campaign-mix tokens, consistent with AA’s $0.14/M methodology view. It does not change the active L40S paid decision. No venue is immediately executable because RunPod creation remains inadmissible and this project has $0 mutation authority.

Next move: director should consume `DECISION.md`; keep the fallback closed unless the specified Nebius failure trigger and fresh RunPod admissibility evidence both occur.

## 2026-07-25 — exact-model market refresh

Question: did the public exact-model frontier move, and how should it alter the continuous/discrete H100 interpretation?

Action: mechanically verified `DIRECTOR_REFRESH_20260725.json` against the bound SHA-256; captured fresh raw OpenRouter JSON and Artificial Analysis HTML under `artifacts/market-refresh-20260725/`; hashed both; did no provider/GPU action and did not overwrite July 17 evidence.

Measured public evidence: OpenRouter returned exact identity `google/gemma-4-31b-it`, 18 endpoints, and new nominal CoreWeave/OpenInference rows at $0.10/$0.10/$0.34–$0.35 per million fresh/cache/output tokens. CoreWeave normalizes to $0.118793/M total campaign tokens and OpenInference to $0.119576/M. Venice is the lowest fully cache-specified status-0 row at $0.135281/M. Artificial Analysis reports Parasail $0.138/M at 7:2:1, 10K-input single stream, past-72-hour medians; Parasail is 38.325 output tok/s and 2.7075 s TTFT. AA exposes Parasail components $0.10/$0.14/$0.40 but leaves several other cache fields missing.

Derived interpretation: the continuous pooled H100 model is $0.133700/M at 0.707334 s/request, near AA and below Venice but 12.5% above CoreWeave. The discrete exact-trace fleet model is $0.236335/M, 71.3% above AA and 98.9% above CoreWeave because the one-replica 90%-headroom ceiling is 0.624546 s/request. These remain analytical; H100 throughput/endpoint behavior is not inferred from the market refresh.

Result: current market evidence lowers the hurdle numerically but does not authorize or alter the live H100 owner. The dated synthesis and decision are `MARKET_TARGET_20260725.json` and `DECISION_20260725.md`.

## 2026-07-25 — frontier eligibility and failure sensitivity

Question: do the new nominal CoreWeave/OpenInference rows deserve one authoritative hurdle after missing-feature and retry/failure analysis?

Action: verified the director eligibility binding and all six bound dated-refresh/source hashes; reused only frozen captures; extracted a missing-aware matrix for CoreWeave, OpenInference, Venice, and the AA reference; computed independent and correlated deterministic overhead bounds. No price refresh, inference request, provider/GPU use, or live-owner inspection occurred.

Evidence: CoreWeave and OpenInference bind exact model ID, BF16, context, prices, status, uptime, and listed API parameters, but revision, quality, current throughput, latency, capacity, and request-level reliability are missing. Venice binds the same fields with a shorter 8,192-token max completion. AA binds a separate 10K single-stream, 7:2:1, 72-hour benchmark with Parasail 38.325 tok/s and 2.7075 s TTFT, not campaign-equivalent execution.

Derived result: CoreWeave tolerates 0.6548% independent failures or 0.6592% one-extra correlated episodes before crossing OpenInference’s nominal price; it tolerates 12.1882% / 13.8799% before Venice and 13.9184% / 16.1688% before AA. Continuous H100 has 3.1160% / 3.2162% tolerance against AA; discrete H100 is already above AA. These sensitivities are synthetic overhead models, not uptime claims.

Decision: retain tiered nominal `$0.119/M`, capability-listed `$0.135/M`, methodology-matched `$0.138/M`, continuous-H100, and discrete-H100 tiers. Persisted `FRONTIER_ELIGIBILITY_20260725.json` and `ELIGIBILITY_DECISION_20260725.md`.
