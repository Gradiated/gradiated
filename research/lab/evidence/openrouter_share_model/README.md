# OpenRouter provider-share evidence collector

This directory contains the evidence and validation layer for a GLM-5.2
provider-share model. Price and uptime are treated as a pre-launch prior;
current request telemetry is a separate post-launch nowcast. The latter is much
more accurate in held-out tests but is not mislabeled as a causal price model.

## What it records

Every collection run stores:

- three independent samples of OpenRouter's mutable effective-pricing/provider-token-share summary;
- endpoint price, capability, health, request-count, latency, and throughput state;
- model activity;
- the public three-day hourly throughput, latency, end-to-end latency, tool-error,
  structured-output-error, and cache-hit charts;
- recent uptime and benchmark scores;
- compressed, checksummed raw JSON for replay when the public schema changes.

Displayed endpoint prices are stored as displayed. The API's `pricing.*` fields
already include any active discount; the collector does not discount them a
second time. Provider variants such as `Wafer` and `Wafer Fast` remain separate
even when they share a base provider slug.

The runtime database is deliberately outside version control:

```text
.agents/runtime/openrouter-provider-share/glm52.sqlite3
```

## Run and inspect

One collection:

```bash
python3 research/lab/evidence/openrouter_share_model/collector.py once
```

Continuous collection, every 15 minutes:

```bash
python3 research/lab/evidence/openrouter_share_model/collector.py loop \
  --interval-seconds 900 --effective-samples 3
```

Collect a timestamped 30-model panel every six hours:

```bash
python3 research/lab/evidence/openrouter_share_model/panel_collector.py loop \
  --interval-seconds 21600
```

Validate the panel with leave-one-model-out, GLM-5.2 holdout, and unseen-provider
tests:

```bash
python3 research/lab/evidence/openrouter_share_model/panel_model.py validate \
  --panel research/lab/evidence/openrouter_share_model/OPENROUTER_PROVIDER_PANEL_2026-07-16.json \
  --output research/lab/evidence/openrouter_share_model/OPENROUTER_PROVIDER_PANEL_VALIDATION_2026-07-16.json
```

Enrich a frozen panel with provider-level GPQA-Diamond and Tau-Bench scores
before validation:

```bash
python3 research/lab/evidence/openrouter_share_model/panel_model.py enrich-benchmarks \
  --panel research/lab/evidence/openrouter_share_model/OPENROUTER_PROVIDER_PANEL_2026-07-16.json \
  --output research/lab/evidence/openrouter_share_model/OPENROUTER_PROVIDER_PANEL_BENCHMARKS_2026-07-16.json
```

The benchmark candidate is evaluated separately from both the stock pre-launch
model and the request-count nowcast. It is not promoted merely because its
coefficients have the expected sign.

Once a funded OpenRouter key is available, controlled default-routing probes can
measure non-tool and tool cohorts. The explicit execution flag and spend cap are
required:

```bash
OPENROUTER_API_KEY=... python3 research/lab/evidence/openrouter_share_model/route_probe.py \
  --execute --cohort non_tool --samples 100 --max-spend-usd 2
```

The probe stores provider, cost, token counts, and latency only. It never stores
the key, prompt, or response content.

Generate an entry-price revenue curve from the latest seven complete days:

```bash
python3 research/lab/evidence/openrouter_share_model/entry_revenue_model.py \
  --price-ratios 0.75,1,1.25,1.5,2 --cogs-ratio 1.25
```

`--common-prices 0.30,0.40,0.50` accepts absolute common-workload blended
prices per million tokens instead. The schedule is proportional to the current
cheapest endpoint's input, cache-read, and output prices. The model conditions
its provider-fitness scenarios on the public three-day `>=99%` uptime cohort. It
reports an optimistic all-price-weighted result, a cohort-aware known-good tool
tier, and an insufficient-data tool lower bound. The current tool-cohort proxy
comes from public tool-call events per request. P10/P25/P50/P75/P90 are empirical
scenario percentiles, not calibrated confidence intervals. Billings are gross
customer-facing endpoint billings before unknown OpenRouter/provider commercial
terms.

The server currently runs that command as the transient systemd service
`openrouter-glm52-share-collector.service`. Check it with:

```bash
systemctl status openrouter-glm52-share-collector.service
journalctl -u openrouter-glm52-share-collector.service -n 20 --no-pager
```

Transient services do not survive a host reboot. Restart the command above, or
recreate the service, after a reboot. Collection errors are logged and retried;
a missing secondary chart does not discard the required provider-share sample.

## Evidence limits

The provider-token-share total is a measured public OpenRouter statistic, but
its aggregation window is not specified in the response. Endpoint metrics are
measured public aggregates. Candidate eligibility, route decisions, capacity,
rate limits, sticky-cache state, and request characteristics are unobserved.
Any model fitted only to this database is therefore empirical and cannot be
called a faithful router replay.

The access and validation contract for an accurate model is in
`../../docs/OPENROUTER_PROVIDER_SHARE_MODEL_ACCESS_2026-07-16.md`.
The current validation decision is in
`../../docs/OPENROUTER_PROVIDER_SHARE_PANEL_MODEL_2026-07-16.md`.

## Verification

```bash
python3 -m unittest discover \
  -s research/lab/evidence/openrouter_share_model -p 'test_*.py' -v
```
