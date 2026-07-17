# GLM-5.2 OpenRouter entry-price revenue model

- objective: produce an uncertainty-bounded GLM-5.2 provider-share and revenue model, then improve and validate its price/uptime response using a multi-model OpenRouter provider panel
- issue: https://github.com/joshsny/gradiated/issues/23
- owner: Codex current session
- scope: public OpenRouter rankings plus standard endpoint/activity/share/uptime/performance data across high-volume multi-provider models, with GLM-5.2 held out; analytical counterfactual only; no paid traffic or external mutation
- excluded: provider payout terms, guaranteed capacity, customer-level demand, claims of causal calibration, credentials
- hypothesis: a compositional panel model with within-model price and uptime effects plus observable provider-quality controls predicts held-out provider shares materially better than documented price-only and uptime-gated inverse-square baselines
- falsifier: leave-one-model-out and leave-one-provider-out performance does not materially beat both baselines, fitted price sign conflicts with the documented direction, or GLM-5.2 holdout error exceeds the preregistered decision gate
- controls: equal share, documented inverse-square price, uptime-gated inverse-square, and the prior single-model latent-fitness curve
- workload/data: top high-volume standard models from the public weekly rankings; repeated public provider-share samples; current endpoint prices, three-day uptime, activity mix, endpoint age/capabilities, throughput, cache and tool-error signals; GLM-5.2 is excluded from fitting and used as a primary holdout
- quality/SLO: endpoint assumed semantically correct and >=99% uptime; tool quality, capability parity, cache locality, and capacity remain scenario dimensions rather than silently assumed facts
- budget/timeout: $0 external spend; 90 minutes; public read-only requests only; rate-limited collection; no credential required
- artifacts: `research/sol/evidence/openrouter_share_model/entry_revenue_model.py`, panel collector/model, tests, panel snapshot, validation JSON and dated decision brief under `research/sol/docs/`
- acceptance: deterministic fixtures pass; panel has at least 20 models and 150 aligned endpoint rows; evaluation reports leave-one-model-out and leave-one-provider-out token-share MAE, total variation and rank correlation for every baseline and candidate; candidate may inform subsidy decisions only if it beats uptime-gated inverse-square by >=20% total-variation error and GLM-5.2 holdout TV is <=0.15
- next gate: replace the cross-sectional fitness prior with the entrant's own eligible-request and price-step telemetry after onboarding

## Result

- status: panel and post-launch nowcast implemented and validated; causal entrant price response remains an onboarding experiment
- measured panel: 30 models, 314 endpoint rows, 65 providers
- pre-launch finding: full public features improve mean TV from 48.5% to 44.8% but fail the 20% improvement and <=15% GLM holdout gates
- post-launch finding: request telemetry reduces mean TV to 12.5% and GLM holdout TV to 18.3%, passing its separately preregistered <=20% nowcast gate
- unseen-provider finding: provider-share MAE falls from 7.75 pp for uptime-gated inverse-square to 2.37 pp with post-launch telemetry across 204 provider-model observations
- interpretation: use price/uptime as a broad pre-launch prior; use routed requests and tokens/request as the launch anchor; estimate causal price elasticity from clean price steps rather than cross-sectional coefficients
- ongoing evidence: GLM snapshot collector runs every 15 minutes and the multi-model panel collector every six hours; controlled paid route probes are implemented but were not run because `OPENROUTER_API_KEY` is absent
- decision brief: `research/sol/docs/OPENROUTER_PROVIDER_SHARE_PANEL_MODEL_2026-07-16.md`

## Auto Exacto benchmark-feature experiment

- causal hypothesis: adding provider-relative GPQA-Diamond and Tau-Bench Verified Airline shortfall features will reduce held-out token-share error because Auto Exacto uses these scores to tier tool traffic
- stock control: current full observable model without benchmark features
- candidate: same compositional model plus within-model robust benchmark shortfall and missing-data features, interacted with the public tool-traffic proxy
- inputs: the same frozen 30-model/314-endpoint panel, enriched from each model's public `benchmark-scores` endpoint on 2026-07-16; GLM-5.2 remains leave-one-model-out
- software: `research/sol/evidence/openrouter_share_model/panel_model.py`; no GPU or hardware dependency
- quality gate: all existing fixtures plus benchmark matching/feature tests pass; enrichment preserves rows, shares, and original source fields
- decision gate: candidate must improve mean leave-one-model-out TV over `full_observable`, and must not worsen GLM-5.2 holdout TV by more than one percentage point; report unseen-provider MAE/TV separately
- budget/SLO: $0 external spend, public read-only requests, <=20 minutes wall time, no persistent external mutation or teardown required
- exact artifacts: enriched panel JSON, validation JSON, updated model/tests, and the dated Auto Exacto brief
- exact commands: `panel_model.py enrich-benchmarks`, then `panel_model.py validate`, then focused unit discovery
- opportunity: observed severe benchmark outliers have low token share; competing explanations are price, endpoint age, throughput, capacity, and non-tool traffic; falsifier is no held-out improvement; residual is hidden live tier state and production tool telemetry
- transfer limit: public scores are sparse 32-day aggregates and may combine provider variants; a cross-sectional improvement does not establish causal tier effects for our future endpoint
- measured result: 231/314 rows matched; benchmark candidate improves mean model-holdout TV 44.82% -> 44.50%, GLM holdout TV 55.81% -> 53.43%, and unseen-provider TV 42.43% -> 40.88%; it passes the directional gate but remains inaccurate in absolute terms
- online result: adding benchmarks to the request-count nowcast worsens mean panel TV 12.55% -> 12.67% while changing GLM TV 18.329% -> 18.273%; this gate fails, so retain the simpler request nowcast
