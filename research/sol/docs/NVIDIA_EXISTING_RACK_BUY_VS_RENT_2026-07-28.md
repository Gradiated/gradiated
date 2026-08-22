# NVIDIA rack buy-versus-rent economics

Date: 2026-07-28
Decision: estimate the infrastructure-cost margin available from buying current NVIDIA HGX systems and colocating them instead of taking a 12-month fixed GPU rental commitment.
Scope: one dense rack containing four 8-GPU HGX systems (32 GPUs). USD, excluding tax.

## Conclusion

At continuous committed use, buying and colocating appears economically cheaper than current 12-month reserved rental rates:

| Rack | 12-month rent | Buy/colo economic cost, one-year buy/resell | Savings | Buy/colo annual economic cost, three-year hold | Savings |
|---|---:|---:|---:|---:|---:|
| 32x H100 SXM | $914k | $733k | $181k / 19.8% | $736k | $178k / 19.5% |
| 32x H200 SXM | $953k | $740k | $213k / 22.4% | $743k | $210k / 22.1% |
| 32x B200 SXM | $1.564m | $1.090m | $475k / 30.3% | $980k | $584k / 37.4% |

The decision is not “buying always wins.” It is:

- **Buy** when the capacity can remain useful for at least 24–36 months, deployment lead time is acceptable, and expected occupancy is high.
- **Rent** while demand, chip choice, or software architecture is still changing quickly; the cloud's option value can be worth more than the 20–37% steady-state saving.
- **B200 has the strongest apparent ownership spread**, but also the highest resale and obsolescence uncertainty. A real vendor quote and a real 60–70 kW colo quote are required before treating that row as bankable.

The percentages are infrastructure cost reductions, not gross-margin points. At unchanged revenue, gross-margin uplift in points is:

`annual infrastructure dollars saved / annual revenue`

For example, if rack revenue is exactly twice its rental cost (50% gross margin before other costs), the three-year ownership case lifts gross margin by about 9.8 points for H100, 11.0 points for H200, and 18.7 points for B200.

## Evidence and modeled inputs

### Physical rack

- **Vendor-reported:** NVIDIA recommends four DGX H100 systems per dense rack. Each system is 8U and 10.2 kW maximum, giving 32 GPUs and 40.8 kW maximum rack demand. [NVIDIA H100 data-center planning guide](https://docs.nvidia.com/dgx-superpod/design-guides/dgx-superpod-data-center-design-h100/latest/planning.html)
- **Vendor-reported:** Four air-cooled DGX B200 systems can occupy a specialized 52U high-density rack, drawing 57.2 kW peak. Depending on power distribution, NVIDIA shows 66–86 kW of provisioned rack capacity. [NVIDIA B200 data-center best practices](https://docs.nvidia.com/dgx-pdf/nvidia-dgx-superpod-data-center-best-practices-with-dgx-b200.pdf)
- **Assumed:** H200 uses the same 32-GPU / roughly 50 kW reserved rack envelope as H100 for this planning comparison.

### Hardware purchase

| Rack | Base modeled capex | Evidence and interpretation |
|---|---:|---|
| H100 | $1.360m | **Vendor-listed:** $309,999 per Lambda 8x HGX H100 server; plus **assumed** $120k/rack for switching, cabling, rack integration, shipping, and initial spares. [Lambda configuration](https://shop.lambda.ai/deep-learning/servers/hyperplane/customize?step=3) |
| H200 | $1.380m | **Vendor-reported MSRP:** $314k per 8x H200 HGX system; rounded to $315k and plus **assumed** $120k/rack integration. A recent GSA schedule lists a lower $259,244 configured system, so the base is deliberately conservative. [RCSI/Advanced Clustering presentation](https://www.advancedclustering.com/wp-content/uploads/2025/06/smaller-institutions.pdf), [GSA price list](https://www.gsaadvantage.gov/ref_text/47QTCA25D00CL/10JE5R.3W9R0F_47QTCA25D00CL_MASGSAPRICELISTSECURISEA07132025.PDF) |
| B200 | $1.840m | **Vendor-reported MSRP:** $423k per 8x B200 HGX system; plus **assumed** $148k/rack integration. A recent GSA schedule lists a lower $381,251 configured system. [RCSI/Advanced Clustering presentation](https://www.advancedclustering.com/wp-content/uploads/2025/06/smaller-institutions.pdf), [GSA price list](https://www.gsaadvantage.gov/ref_text/47QTCA25D00CL/10JE5R.3W9R0F_47QTCA25D00CL_MASGSAPRICELISTSECURISEA07132025.PDF) |

These are HGX-compatible planning prices, not signed startup quotes. Actual networking requirements depend on whether the workload needs only inference traffic, scale-out tensor/pipeline parallelism, or a full training-grade InfiniBand fabric.

### Rental

| GPU | Modeled fixed rate | Evidence |
|---|---:|---|
| H100 HGX | $3.26/GPU-hour | **Vendor-listed:** DigitalOcean 12-month reserved price. |
| H200 HGX | $3.40/GPU-hour | **Vendor-listed:** DigitalOcean 12-month reserved price. |
| B200 HGX | $5.58/GPU-hour | **Aggregated:** Bargo average reserved price across public listings; its stated reserved category covers 1–3-year terms, so this is a 12-month proxy rather than an exact provider quote. |

Sources: [DigitalOcean GPU pricing](https://www.digitalocean.com/pricing/gpu-droplets), [Bargo B200 price index](https://www.bargo.ai/gpu/b200).

Rental annual cost is `rate × 32 GPUs × 8,760 hours`. The comparison assumes the reserved rack is paid for continuously whether busy or idle.

### Colocation and operations

- **Market-reported:** CBRE gives $165–$265 per kW/month for European 250–500 kW colocation requirements in Q1 2026. A single rack can price above wholesale scale. [CBRE Global Data Center Trends 2026](https://www.cbre.com/insights/reports/global-data-center-trends-2026)
- **Derived facility cost:** reserving 50 kW for H100/H200 costs $99k–$159k/year at that range; reserving 70 kW for B200 costs $139k–$223k/year.
- **Assumed all-in annual rack operations:** $250k for H100/H200 and $350k for B200. This includes the base colo allocation plus connectivity, remote hands, vendor support, insurance, spare allowance, and operational overhead. It excludes the inference engineering team because that is required in both cases.

## Calculation method

### Direct one-year comparison

The one-year case assumes the rack is sold after 12 months:

- H100/H200 resale: 75% of installed capex
- B200 resale: 70% of installed capex
- Economic capital charge: 12% on average beginning/end book value
- One-year ownership cost: depreciation plus annual operations plus capital charge

This case is highly sensitive to resale liquidity. It should not be used to justify a purchase unless there is a credible secondary-market bid or buyback.

### Three-year ownership

The base ownership case assumes:

- three-year useful holding period;
- 12% annual cost of capital;
- end-of-year-three residual value of 20% for H100/H200 and 25% for B200;
- annual rack operations as above.

The annualized capital cost uses a three-year capital-recovery factor after discounting residual value. The resulting break-even all-in rental rates are:

| Rack | Ownership break-even rental rate |
|---|---:|
| H100 | $2.62/GPU-hour |
| H200 | $2.65/GPU-hour |
| B200 | $3.50/GPU-hour |

If a provider offers reliable fixed capacity below those rates, renting is economically preferable under the base assumptions.

## Sensitivity

The most decision-relevant uncertainties are purchase quote, all-in colo operations, financing cost, and resale value.

### Plausible three-year cost range

Using public purchase-price bounds and the following all-in rack-operations bounds:

- H100/H200: $220k–$300k/year
- B200: $300k–$400k/year
- B200 reserved rental: $4.65–$5.58/GPU-hour

the modeled ownership savings range is:

| Rack | Conservative savings | Favorable savings |
|---|---:|---:|
| H100 | 4.7% | 22.8% |
| H200 | 16.8% | 33.6% |
| B200 | 20.9% | 44.2% |

H100 is therefore not an automatic buy at any price: an expensive system quote plus costly colo can erase almost all of the spread.

### Cost of capital

Holding the base hardware, opex, and resale assumptions constant:

| Cost of capital | H100 saving | H200 saving | B200 saving |
|---:|---:|---:|---:|
| 8% | 24.1% | 26.5% | 41.0% |
| 12% | 19.5% | 22.1% | 37.4% |
| 20% | 10.2% | 13.0% | 29.9% |
| 30% | -1.8% | 1.3% | 20.2% |

This is why comparing cloud rent only to hardware depreciation overstates the value of buying for an early-stage company.

### Utilization

If both alternatives are fixed for the year, useful utilization does not change the percentage saving: it increases both costs per useful GPU-hour by the same factor. At 70% useful utilization, the base three-year economic costs become:

| Rack | Rent per useful GPU-hour | Owned per useful GPU-hour |
|---|---:|---:|
| H100 | $4.66 | $3.75 |
| H200 | $4.86 | $3.79 |
| B200 | $7.97 | $4.99 |

Utilization matters asymmetrically if rented capacity can be reduced, exchanged for another chip, or not renewed. That flexibility is the rental product's main economic advantage and is not captured in the fixed-versus-fixed table.

## Practical recommendation

For a new inference company:

1. Keep research, uncertain launches, and burst capacity rented.
2. Buy the first production rack only after a workload has demonstrated roughly 70%+ useful occupancy and has enough demand visibility to remain useful for two to three years.
3. Seek three matched quotes before deciding: delivered HGX systems with support, 50/70 kW high-density colo, and a 12-month fixed bare-metal rental for the identical topology.
4. Negotiate a vendor buyback, trade-in, or equipment-finance facility. Resale and capital cost are the two variables most capable of reversing the H100 result.
5. Retain cloud overflow even after buying. A mixed base-owned / burst-rented fleet captures most ownership savings without betting the company on one GPU generation.

## What is measured versus uncertain

- **Strong public evidence:** DigitalOcean H100/H200 12-month rates; NVIDIA rack power/density; GSA H200/B200 configured-system prices.
- **Moderate evidence:** Lambda H100 public configured price; B200 cross-provider reserved average; H200/B200 public MSRP presentation.
- **Modeled:** installed rack capex, all-in colo operations, financing, depreciation/residual value, and resulting savings.
- **Missing before procurement:** startup-specific purchase quotes, actual site-specific high-density colo quote, support SLA, lead time, financing terms, import/tax treatment, and guaranteed resale/buyback value.
