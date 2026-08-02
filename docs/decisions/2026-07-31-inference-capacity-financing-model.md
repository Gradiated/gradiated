# Inference capacity and financing model

Date: 2026-07-31  
Issue: [#30](https://github.com/Gradiated/gradiated/issues/30)  
Workbook: [Google Sheet](https://docs.google.com/spreadsheets/d/1Ix7kRD90UAdT9nWU_ykPr3KXe9SpW1Yak0SOzBumtOg/edit)

## Decision and current status

Use a rent-first operating posture until four inputs are measured for the exact
top-ten model set: quarterly OpenRouter tokens, provider capture, total
tokens/second/GPU, and current cheapest blended customer price. The workbook now
contains a measured 12-month OpenRouter ranking import (2025-07-01 through
2026-06-30) aggregated to 120 monthly rows and normalized to model families so
dated aliases do not create false growth. The revenue values are still a
planning proxy: current `/models` prices are applied retrospectively with a 75%
prompt / 25% completion mix, and the open-weight classification is a publisher
family heuristic pending license review. Forecast QoQ growth is visibly capped
at 25% in the base control surface; uncapped historical growth remains visible
for review.

The base scenario currently reports approximately `$5.33B` of indicative equity
need, `$2.67B` of hardware capex, and `$1.49B` of operating subsidy through
2029-Q4. These are scenario outputs driven mainly by the synthetic 500 total
tokens/second/GPU throughput assumption, 10% provider capture, 25% quarterly
growth, 60% owned-capacity share, and 3% undercut. They are not a hardware
recommendation or fundraising advice until throughput, price, topology, and
commercial quotes are measured.

## Question, hypothesis, and falsification

Question: how much OpenRouter inference could the company capture through 2029,
what NVIDIA or AMD systems and racks would serve it, when is buying cheaper than
renting or signing a long-term contract, what price subsidy makes the company
cheapest, and what cash must be raised?

Hypothesis: a quarterly, model-specific demand-to-capacity bridge can expose the
few inputs that dominate the answer and keep business, infrastructure, and
financing assumptions internally consistent.

Falsification conditions:

- the model cannot reconcile market tokens to provider tokens and required GPU
  capacity;
- a change in capture, growth, utilization, hardware, or undercut does not flow
  through to rack, subsidy, and capital outputs;
- source-specific throughput is presented as measured without a matching
  serving benchmark;
- the workbook produces formula errors or a numeric demand result while history
  is absent.

## Scope

Included:

- four historical quarters and quarterly forecast through 2029-Q4;
- top ten open-source models ranked by loaded historical gross inference spend;
- model-specific growth, capture, GPU, throughput, and price inputs;
- L4, RTX PRO 6000 Blackwell, L40S, A100 PCIe/SXM, H100 PCIe/SXM, H200 SXM,
  B200 SXM, B300 SXM, GB200 NVL72, and GB300 NVL72 planning alternatives;
- AMD MI300X, MI325X, MI350X, and MI355X planning alternatives, including a
  visible long-term rental discount, contract term, and owning-advantage spread;
- whole-system purchases, rack equivalents, power, rent cost, owned operating
  cost, capex, customer revenue, operating subsidy, and cash requirement;
- rent-first, base, and aggressive scenarios.

Not included:

- a causal guarantee that lower price produces provider share;
- signed cloud capacity, hardware, colocation, network, financing, or power
  terms;
- exact prefill/decode separation, latency SLOs, batching distributions, KV
  cache behavior, redundancy topology, deposits, tax, depreciation, or working
  capital beyond the simple reserve;
- AMD ROCm porting, kernel maturity, model-specific performance, and supply
  availability are not yet modeled as separate commercial risk adjustments;
- an investment recommendation, valuation, or fundraising advice.

## Workbook contract

The calculation chain is:

`History -> Model Drivers -> Demand Forecast -> Capacity Detail -> Capacity Plan -> Pricing & Subsidy -> Funding & Dashboard`

Key equations:

- `provider tokens = market tokens x capture %`
- `required GPUs = ceiling(provider tokens / quarter seconds / tokens per second per GPU / utilization)`
- `systems required = ceiling(owned GPU target / GPUs per system)`
- `target price = cheapest blended price x (1 - undercut %)`
- `operating subsidy = max(0, infrastructure cash cost - provider revenue)`
- `indicative raise = peak cumulative cash deficit + working-capital reserve + contingency - starting cash`

The `Scenarios` tab is the primary control surface. Light-cream cells with blue
text are editable inputs; formulas remain unfilled. The `Checks` tab is the stop
gate. `DATA REQUIRED` is replaced by `PASS` after the history import, while
license, price-proxy, and throughput review remain human actions.

## Evidence table

| Claim or input | Evidence | Label | Limitation |
|---|---|---|---|
| Daily rankings expose top models and token totals | [OpenRouter rankings-daily API](https://openrouter.ai/docs/api/api-reference/datasets/get-rankings-daily) | Official documentation | API key required; ranking dataset begins 2025-01-01; tokens are not provider revenue. |
| Current model metadata and prices are available | [OpenRouter models API](https://openrouter.ai/docs/api/api-reference/models/get-models) | Official documentation | Prices and availability are mutable. |
| OpenRouter passes through provider pricing and charges a credit-purchase fee | [OpenRouter FAQ](https://openrouter.ai/docs/faq) | Official documentation | The fee is not provider revenue; commercial terms may differ. |
| Price alone does not determine provider share | `research/sol/evidence/openrouter_share_model/OPENROUTER_PROVIDER_PANEL_BENCHMARK_VALIDATION_2026-07-16.json` | Measured public panel plus fitted model | Observational, not causal; provider fitness, request count, uptime, errors, cache, and age also matter. |
| H200 has 141 GB HBM3e and B200 has 180 GB HBM3e | `research/factory/data/accelerator_inventory.json` | Vendor-reported, curated | Hardware capacity is not workload throughput. |
| Planning rental rates are H200 `$3.25` and B200 `$5.15` per GPU-hour | `research/factory/data/gpu_prices.json` | Derived planning inventory | Refreshed 2026-07-28; not a capacity guarantee or quote. |
| Public schedule prices are H200 `$259,244.01` and B200 `$381,251.25` per 8-GPU system | [US GSA price list](https://www.gsaadvantage.gov/ref_text/47QTCA25D00CL/10JE5R.3W9R0F_47QTCA25D00CL_MASGSAPRICELISTSECURISEA07132025.PDF) | Public contract schedule | Not a company-specific quote; support and configuration can differ. |
| DGX B200 uses eight B200 GPUs and 1,440 GB total GPU memory | [NVIDIA DGX B200 guide](https://docs.nvidia.com/dgx/dgxb200-user-guide/introduction-to-dgxb200.html) | Vendor-reported | DGX and OEM HGX configurations can differ. |
| A DGX B200 planning example uses 14.3 kW peak/system and up to four systems/rack | [NVIDIA facility guide](https://docs.nvidia.com/dgx-pdf/nvidia-dgx-superpod-data-center-best-practices-with-dgx-b200.pdf) | Official documentation | Requires a matching high-power facility design. |
| A GB200 NVL72 rack full-load example is about 120 kW | [NVIDIA Mission Control FAQ](https://docs.nvidia.com/mission-control/docs/systems-administration-guide/2.1.0/prs/faq.html) | Official documentation | Example, not a guaranteed site draw. |
| GB200 NVL72 purchase price midpoint is `$3.1M` | [Tom's Hardware report](https://www.tomshardware.com/tech-industry/artificial-intelligence/price-of-nvidias-vera-rubin-nvl72-racks-skyrockets-to-as-much-as-usd8-8-million-apiece-but-server-makers-margins-will-be-tight-nvidia-is-moving-closer-to-shipping-entire-full-scale-systems) | Secondary reported estimate | Replace with a written quote; source range was `$2.8M-$3.4M`. |
| AMD MI300X is 192 GB HBM3 at 750 W | [AMD MI300X specifications](https://www.amd.com/en/products/accelerators/instinct/mi300/mi300x.html) | Vendor-reported | 8-GPU system power and purchase price are planning estimates. |
| AMD MI325X is 256 GB HBM3E at 1,000 W | [AMD MI325X platform datasheet](https://www.amd.com/content/dam/amd/en/documents/instinct-tech-docs/product-briefs/instinct-mi325x-platform-datasheet.pdf) | Vendor-reported | 8-GPU system power and purchase price are planning estimates. |
| AMD MI350X is 288 GB HBM3E at 1,000 W | [AMD MI350X specifications](https://www.amd.com/en/products/accelerators/instinct/mi350/mi350x.html) | Vendor-reported | Air-cooled platform topology and purchase price need quotes. |
| AMD MI355X is 288 GB HBM3E at 1,400 W | [AMD MI355X specifications](https://www.amd.com/en/products/accelerators/instinct/mi350/mi355x.html) | Vendor-reported | Liquid-cooled/rack-scale topology and purchase price need quotes. |
| AMD MI300X 8-GPU server range is `$240k-$300k` | [GPU server pricing guide](https://www.gpu.fm/blog/gpu-server-pricing-guide-2026) | Secondary market range | `$270k` midpoint used; replace with an OEM quote. |
| Long-term AMD rental references exist below on-demand rates | [MI325X listings](https://gpu-hunt.com/gpu/AMD%20Instinct%20MI325X), [MI355X contract reference](https://infohub.delltechnologies.com/zh-cn/p/multi-agent-risk-analysis-compliance-monitoring/) | Market observations | Provider, term, geography, availability, and support differ; not quotes. |
| Default model throughput is 500 total tokens/s/GPU | Workbook `Model Drivers` | Synthetic | Placeholder only; never transfer across model, quantization, context, or SLO. |

## Interpretation

The workbook deliberately keeps provider capture independent from price. The
repository's observed OpenRouter provider panel has negative price coefficients,
but request telemetry and service-quality variables explain routing too; being
the cheapest is therefore neither necessary nor sufficient to win the modeled
capture share. The undercut input answers the cash-cost question, not the causal
share question.

At the current planning inputs, owned effective GPU-hour cost is approximately
`$2.06` for H200 and `$3.15` for B200 at 65% utilization, versus planning rental
rates of `$3.25` and `$5.15`. This analytical comparison favors ownership only
after utilization is sustained and the exact workload fits the platform. Whole
system rounding, new-provider ramp, lead time, redundancy, and financing can
reverse that result at low scale.

The AMD rows use a 20% base-case discount to the on-demand proxy and a 36-month
term input. At the selected 65% utilization, the resulting owned versus term
rental spreads are approximately: MI300X `$2.18` owned versus `$2.00` term,
MI325X `$2.86` versus `$2.20`, MI350X `$3.25` versus `$2.20`, and MI355X `$4.04`
versus `$2.40` per GPU-hour. The negative owning-advantage values mean the
illustrative term contract is cheaper under the current assumptions; these are
not quotes and should be replaced per platform with signed offers.

## Verification

Measured on 2026-08-02 after the history import and formatting pass:

- fourteen workbook tabs present;
- 18,564 daily ranking rows fetched and 120 monthly history rows loaded;
- ten open-weight candidate models selected for the model driver table;
- sixteen NVIDIA/AMD platform rows available for buy/rent and rack sensitivity;
- long-term rental discount, contract term, and owning-advantage columns are
  visible in `Hardware Economics`;
- all extended structural checks pass;
- formula-error scan across the new tabs: `0` errors;
- history-dependent check: `PASS`;
- representative editable ranges have light-cream fill and blue text;
- dates, percentages, token counts, GPU counts, power, prices, and cash outputs
  use explicit finance formats with dash-for-zero and red-parentheses negatives;
- browser visual inspection was attempted, but no connected browser was
  available; formatting and values were verified through the Sheets API/MCP.

Repository checks to run before handoff:

```bash
python3 tools/devex/check.py
git diff --check
```

## Next action

1. Rotate the OpenRouter key disclosed in chat.
2. Set the replacement only in a local secret environment as
   `OPENROUTER_API_KEY`; do not paste it into chat or commit it. The current
   1Password desktop bridge must be restarted before a fresh import can run.
3. Import four complete quarters of daily rankings and current model prices.
4. Confirm open-source license classification for the top ten rows.
5. Benchmark each selected model on its exact quantization, context mix,
   batching policy, latency SLO, and GPU topology; replace the synthetic
   throughput values.
6. Obtain written rental, server, colocation, network, power, support, lead-time,
   deposit, and equipment-finance quotes before choosing the buy scenario or
   using the funding output.
