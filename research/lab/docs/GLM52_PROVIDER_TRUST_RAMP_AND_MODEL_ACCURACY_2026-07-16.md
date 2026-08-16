# GLM-5.2 provider trust ramp and model accuracy — 2026-07-16

## Decision

The current model is **not accurate enough for a large precommitted subsidy**.
It is useful as an order-of-magnitude scenario model and for designing a launch
experiment. It has no historical entrant backtest, no observed eligible-request
denominator, and no public first-week provider trajectory.

The earlier all-traffic price curve was too elastic. OpenRouter documents that
Auto Exacto reorders every request containing tools using throughput, tool-call
success, and benchmark signals rather than ordinary price-weighted routing.
Across the latest seven complete GLM-5.2 days, public activity records 41.332M
tool-call events on 69.991M requests, or 59.05 events per 100 requests. The
public request-level tool-error volume independently matches that count. We use
59.05% as a tool-cohort proxy; the true fraction of requests *containing* tools
can be higher because requests that emit no tool call are not counted.

At the assumed `1.25×`-cheapest COGS/list price, a provider matching the public
three-day `>=99%` uptime cohort has this known-good steady-state prior:

| 99%+ incumbent fitness | Share | Gross billings/month | Interpretation |
|---|---:|---:|---|
| P10 | 0.41% | $25k | lower observed-fit scenario |
| P25 | 0.50% | **$31k** | conservative known-good planning case |
| P50 | 1.31% | **$81k** | median known-good scenario |
| P75 | 6.58% | $406k | strong provider; not underwriting |
| P90 | 15.25% | $940k | upside only |

The P25–P75 span is 13.4×. It is an empirical scenario range, not a confidence
interval. For financial underwriting before launch, use approximately **$10k–
$31k gross MRR during qualification** and do not capitalize the P50/P75 upside
until our own routing telemetry supports it.

## Accuracy assessment

| Component | Current confidence | Reason |
|---|---|---|
| Seven-day market volume | Medium | measured public aggregate; daily request CV is 16.8%, prompt-token CV 22.1%; monthly extrapolation assumes no demand regime change |
| Displayed prices and rank | High | live endpoint records; fields are already discounted |
| Normal-routing uptime rule | High | official 100-request and 95% thresholds |
| Non-tool relative price direction | Medium | official inverse-square policy, but exact lowest-cost candidate boundary and request-price scalar are unpublished |
| Tool-traffic fraction | Medium | 59.05% request-level tool-call-output proxy; requests containing tools but emitting none are missing |
| Absolute entrant share | Low | no eligible-request denominator, no entrant backtest, no tier history |
| Share response to subsidy | Low–medium after correction | only non-tool cohort is assumed price elastic; tool-tier and explicit routing remain unobserved |
| Time to known-good tier | Low | minimum sample windows are public; benchmark scheduling and tier-assignment latency are not |

The public effective-pricing API resolves to three repeatable current aggregates
whose total-token counts differ by 7.5%. Holding the `>=99%` cohort fixed, 24
rate-limited samples moved P25/P50 fitness by about 3.6%/4.1% and P75/P90 by
less than 0.6%. This API-replica noise is manageable. The large uncertainty is
which provider-fitness percentile our endpoint earns, not snapshot sampling.

No numerical point estimate should currently be described as expected revenue.
The model becomes decision-grade only after a chronological holdout or our own
live price steps achieve the preregistered prediction-error gate.

## What “trusted provider” means operationally

OpenRouter does not document a permanent trusted-provider state. The relevant
states are rolling:

1. A new model is automatically staged, baseline-tested, and unhidden after the
   baseline passes and pricing is configured. No public completion-time SLA is
   given.
2. Uptime starts being evaluated after at least 100 requests. At 95%+ the
   endpoint receives normal routing; 80–94% is degraded; below 80% is fallback.
3. Auto Exacto places endpoints into **Good**, **Insufficient data**, or
   **Deprioritized** tiers. Evaluation requires at least 100 general requests in
   a rolling 30-minute window and 200 tool-call requests in a rolling two-hour
   window.
4. Good requires sufficient data and no benchmark, throughput, or tool-success
   signal below the model-relative median/MAD thresholds. Because these are
   rolling signals, trust can also be lost.

At current GLM-5.2 traffic, the two sample thresholds require only approximately:

- **0.048%** of market request attempts to reach 100 requests per 30 minutes;
- **0.041%** of the observed tool-call event stream to reach 200 per two hours.

Therefore, if OpenRouter gives a new endpoint at least about **0.05% exploration
share**, the mechanical sample gates can clear within two hours. That is not a
guarantee: OpenRouter does not publish a minimum exploration allocation, and an
endpoint can remain in an insufficient-data loop if it receives less traffic or
rate-limits heavily.

## Public ramp evidence

Endpoint `created_at` is public, but the provider performance APIs expose only
eight daily points. Every current GLM-5.2 endpoint is already 18.6–29.9 days old,
so the public window begins after every endpoint's first week. There is no
observable launch-to-trust curve to fit retrospectively.

The cross-section still falsifies “99% uptime plus elapsed time guarantees
traffic”:

| Provider variant | Endpoint age | Three-day uptime | Current token share observed |
|---|---:|---:|---:|
| Alibaba Cloud Int. | 20.8 days | 99.77% | about 30–33% |
| Fireworks Fast | 20.6 days | 99.80% | about 1–2% |
| Wafer Fast | 20.6 days | 99.90% | about 0.01–0.06% |
| Wafer | 28.3 days | 99.62% | about 0.2–0.5% |
| Baseten | 29.7 days | 99.85% | about 0.2–0.4% |

Alibaba demonstrates that a strong endpoint can become a traffic leader within
three weeks. Wafer Fast demonstrates that nearly 99.9% uptime for three weeks
does not itself produce meaningful share. Price, Auto Exacto quality tier,
capability coverage, cache affinity, capacity, and customer routing dominate the
calendar.

## Corrected subsidy economics

Anchor the provider-fitness scenarios at the `1.25×` COGS/list price. For the
59.05% tool proxy, hold known-good tool share constant when price changes and
apply inverse-square repricing only to the remaining 40.95% non-tool cohort.
For the insufficient-data lower bound, assume zero tool-cohort share until Good.

Known-good results:

| Price ratio | P25 gross MRR | P25 monthly subsidy | P50 gross MRR | P50 monthly subsidy | P75 gross MRR | P75 monthly subsidy |
|---:|---:|---:|---:|---:|---:|---:|
| 0.75× | $32k | $21k | $83k | $55k | $392k | $261k |
| 1.00× | $31k | $8k | $79k | $20k | $392k | $98k |
| **1.25×** | **$31k** | **$0** | **$81k** | **$0** | **$406k** | **$0** |

Within this model, a broad discount is economically poor once the endpoint is
known-good: it discounts the large tool cohort even though that cohort is not
primarily price-routed. At P50, moving from 1.25× to 0.75× raises gross MRR by
only about $2k while burning approximately $55k/month.

During insufficient-data status, the corresponding conservative gross MRR is
approximately $13k P25 / $33k P50 at 1.25×. At 0.75× it becomes about $21k /
$54k, but requires about $14k / $36k monthly subsidy at the modeled run rate.
That can be useful only as a short, capped experiment if the endpoint is not
receiving the ~0.05% exploration share needed to clear the sampling gates.

## Recommended launch clock

This is an operating recommendation, not an OpenRouter SLA:

- **Before launch:** baseline and tool-schema replay must pass; provision enough
  capacity for at least the P25 known-good case and enough burst headroom to
  avoid queueing. Supply `capacity_tpm` so OpenRouter can plan routing.
- **First 2 hours:** list at COGS, not subsidized. Measure whether attempts clear
  both documented sample thresholds. If they do, price is not the ramp blocker.
- **First 24 hours:** verify tier, tool-error rate, benchmark visibility,
  throughput, 429s, uptime, eligible attempts, fallbacks, and served traffic in
  the provider dashboard. Escalate missing benchmark/tier data to OpenRouter.
- **At 72 hours:** require >=99% three-day uptime and no persistent
  deprioritization. This is the first useful reliability checkpoint.
- **At 7 days:** use a complete public history window and our provider telemetry
  to replace the cross-sectional prior. Cache/session affinity has had time to
  begin accumulating.
- **Days 7–14:** if known-good and capacity-safe, run two bounded price steps,
  each long enough to span daily demand variation. Estimate tool and non-tool
  elasticity separately.

Do not authorize an open-ended subsidy. A sensible initial authority is a
**14-day experiment with a hard loss cap**, released in stages:

1. $0 subsidy while sample thresholds and Good-tier placement are attainable at
   COGS;
2. a small temporary discount only if measured attempts remain below 0.05% and
   OpenRouter confirms price is the limiting factor;
3. no six-figure monthly run rate until one held-out price step predicts share
   within 20% relative and provider-dashboard data confirms the eligible-request
   denominator.

## Model and evidence

The corrected executable model is
[`../evidence/openrouter_share_model/entry_revenue_model.py`](../evidence/openrouter_share_model/entry_revenue_model.py).
Its captured result includes endpoint ages, three-day uptime, current share,
qualification traffic thresholds, and known-good/insufficient-data cohort
projections:
[`../evidence/openrouter_share_model/GLM52_ENTRY_REVENUE_MODEL_2026-07-16.json`](../evidence/openrouter_share_model/GLM52_ENTRY_REVENUE_MODEL_2026-07-16.json).

## Sources

| Source | Retrieved | Evidence type | Use |
|---|---|---|---|
| [Provider integration](https://openrouter.ai/docs/guides/community/for-providers) | 2026-07-16 | vendor-documented | auto-stage behavior, uptime gates, sample windows, Auto Exacto tiers and thresholds |
| [Auto Exacto](https://openrouter.ai/docs/guides/routing/auto-exacto) | 2026-07-16 | vendor-documented | tool-request ranking and request-level tool-error definition |
| [Provider selection](https://openrouter.ai/docs/guides/routing/provider-selection) | 2026-07-16 | vendor-documented | non-tool inverse-square price routing and filters |
| [GLM-5.2 endpoint state](https://openrouter.ai/api/frontend/v1/stats/endpoint?permaslug=z-ai%2Fglm-5.2-20260616&variant=standard) | 2026-07-16 | measured mutable aggregate | endpoint creation, price, status, current request volume |
| [GLM-5.2 uptime](https://openrouter.ai/api/frontend/v1/stats/uptime-recent?permaslug=z-ai%2Fglm-5.2-20260616) | 2026-07-16 | measured mutable aggregate | three-day uptime condition |
| [GLM-5.2 provider totals](https://openrouter.ai/api/frontend/v1/stats/effective-pricing?permaslug=z-ai%2Fglm-5.2-20260616&variant=standard) | 2026-07-16 | measured mutable aggregate | provider token-share scenarios |
| [GLM-5.2 activity](https://openrouter.ai/api/frontend/v1/stats/model-activity?permaslug=z-ai%2Fglm-5.2-20260616&variant=standard) | 2026-07-16 | measured aggregate | market and tool-call volume |
| [Tool-call error history](https://openrouter.ai/api/frontend/v1/stats/tool-call-error-rate?permaslug=z-ai%2Fglm-5.2-20260616&timeRange=1w) | 2026-07-16 | measured aggregate | request-level tool-call volume cross-check |
