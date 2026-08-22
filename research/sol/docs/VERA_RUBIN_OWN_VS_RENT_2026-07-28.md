# Vera Rubin NVL72: own-and-colocate versus long-term rental

Date: 2026-07-28

## Decision

Customer-owned equipment in a third-party data centre is a standard colocation
arrangement. For one Vera Rubin NVL72, ownership is likely economically
preferable to rental only when all three conditions hold:

1. useful utilization can remain above roughly 65%-70%;
2. the rack will remain cost-competitive for at least three years or has a
   credible resale/redeployment path;
3. the best all-in committed rental quote is materially above approximately
   $4.2M/year.

Below $4M/year for an equivalent dedicated Rubin rack with support and a
hardware-refresh option, rent. Above $5M/year, ownership is probably attractive
if utilization is proven. Between those values, flexibility, delivery date,
firmware/root access, and refresh terms matter more than the point estimate.

This is a planning model, not an OEM quote, colocation proposal, financing
offer, tax analysis, or measured utilization result.

## Is this ownership structure normal?

Yes. The data-centre operator owns and operates the building, utility power,
cooling, security, and facility infrastructure; the tenant owns the GPUs,
servers, and networking equipment. JLL's 2026 outlook explicitly says GPUs,
CPUs, and networking infrastructure are typically tenant-owned and refreshed
on a faster schedule than the facility.

The physical asset remains on the startup's balance sheet and can be financed,
insured, relocated, resold, or redeployed, subject to the OEM and colocation
contracts.

## Expected colocation bill

CBRE reports Q1 2026 European asking rents of $165-$265 per kW per month for
250-500 kW requirements. Applied mechanically to 200 kW, this is
$396k-$636k/year. A one-rack Vera Rubin deployment is smaller and technically
harder than that wholesale reference: it needs unusually dense power and
liquid heat rejection. Budget:

| Cost | Planning range |
|---|---:|
| Reserved facility capacity, energy, and cooling | $0.50M-$0.90M/year |
| Network, cross-connects, remote hands, monitoring | $0.10M-$0.30M/year |
| OEM support, insurance, and spare-parts allowance | $0.15M-$0.40M/year |
| **Recurring cash operating cost** | **$0.75M-$1.60M/year** |
| Initial facility integration and installation | $0.20M-$0.80M one-time |

The actual tariff may reserve and charge the entire contracted power envelope
even when compute utilization is lower. A firm quote must state whether energy
is bundled or passed through, the PUE/cooling treatment, power redundancy,
minimum term, escalation, setup charge, and take-or-pay capacity.

## Three-year ownership cost

Base assumptions:

- $9.0M purchase and installation price;
- $1.1M/year recurring facility and rack operations;
- 25% hardware residual value after three years;
- 12% cost of capital;
- taxes and financing fees excluded.

Results:

| Measure | Base result |
|---|---:|
| Three-year cash cost net of residual | $10.05M |
| Cash cost per year | $3.35M |
| Annual economic cost including 12% capital charge | **$4.18M/year** |
| Economic cost per installed GPU-hour | $6.63 |
| Economic cost per useful GPU-hour at 70% utilization | $9.47 |

The uncertainty range is wide:

| Case | Purchase | Annual operations | Year-3 residual | Annual economic cost |
|---|---:|---:|---:|---:|
| Favorable | $8M | $0.8M | 30% | $3.42M |
| Base | $9M | $1.1M | 25% | $4.18M |
| Adverse | $11M | $1.6M | 15% | $5.69M |

## Rental comparison

There is no public committed Vera Rubin NVL72 rate yet; current providers
require sales contact. Therefore the clean decision is quote-relative rather
than based on an invented rental price.

Two public cross-checks establish scale:

- CoreWeave lists a four-GPU GB200 NVL72 instance at $42/hour on demand,
  equivalent to $6.62M/year for 72 GPUs if linearly scaled.
- A current market index reports a $5.54/GPU-hour median reserved B200 rate,
  equivalent to $3.49M/year for 72 GPUs. This is not a Rubin rack and excludes
  the distinct rack architecture and launch premium.

An equivalent Rubin provider must recover hardware, facility operations,
financing, support, stranded-capacity risk, and margin. A plausible committed
quote could therefore straddle the ownership base case rather than being
dramatically more expensive.

| Equivalent dedicated-rack rental | Own-versus-rent interpretation |
|---:|---|
| Less than $4.0M/year | Rent, especially with refresh rights |
| $4.0M-$5.0M/year | Negotiate based on flexibility and bare-metal control |
| More than $5.0M/year | Ownership probably wins at sustained high utilization |
| On-demand equivalent near $6.6M/year | Ownership could save roughly 35%-45% |

Compared with a competitive three-year dedicated contract, ownership may save
only 10%-30%. Compared with on-demand rental, ownership can be much cheaper.
The cloud premium purchases valuable options: delayed capital commitment,
rapid exit, scaling across racks, provider-operated failures, and migration to
the next GPU generation.

## Is it worth doing?

For an inference startup with several hundred million dollars of capital,
buying one rack is worth doing after the serving stack demonstrates:

- at least 65%-70% useful utilization on rented Rubin;
- a portfolio of models that can occupy spare GPU groups;
- scope-matched cost per token below the relevant providers;
- an OEM quote, colo quote, delivery allocation, warranty, and spares plan;
- a migration or resale plan if the next generation changes token economics.

Do not buy merely because the capital is available. NVIDIA is claiming
generation-scale cost reductions, so technological obsolescence can dominate
electricity and colo savings. The first owned rack is strategically valuable
for unrestricted profiling, model-specific kernels, custom runtimes, and
stable production capacity, but it should follow rather than precede a
measured utilization month.

The preferred sequence is:

1. Obtain comparable three-year rental, lease-to-own, and OEM purchase quotes.
2. Measure one month of useful utilization and realized token margin on rented
   Rubin.
3. Exercise the purchase if rental is above $5M/year or if bare-metal control
   has material research value that the provider will not grant.
4. Place the owned rack in specialist colocation; do not build a facility for
   one rack.

## Sources and evidence classes

| Evidence | Class | Source | Retrieved |
|---|---|---|---|
| Tenant ownership of GPUs and roughly five-year infrastructure refresh | Market research | [JLL 2026 Global Data Center Outlook](https://www.jll.com/content/dam/jllcom/en/global/documents/reports/research-reports/26-research-global-data-center-outlook-new.pdf) | 2026-07-28 |
| Europe $165-$265/kW/month at 250-500 kW | Market research | [CBRE Global Data Center Trends 2026](https://www.cbre.com/insights/reports/global-data-center-trends-2026) | 2026-07-28 |
| AI capacity carries advanced-cooling premiums | Market research | [CBRE European capacity pricing](https://www.cbre.co.uk/press-releases/data-centre-capacity-pricing-in-europe-set-for-double-digit-growth-amid-supply-constraints) | 2026-07-28 |
| One-rack 200 kW liquid-to-air option | OEM-reported | [Supermicro Vera Rubin infrastructure](https://ir.supermicro.com/news/news-details/2026/Supermicro-Introduces-DCBBS-Blueprints-for-NVIDIA-Vera-Rubin-NVL72-and-NVIDIA-HGX-Rubin-NVL8-Built-to-Scale-from-5MW-to-1GW-as-an-End-to-End-Total-Solution/default.aspx) | 2026-07-28 |
| Estimated $7.8M-$8.8M Rubin rack cost | Analyst estimate via secondary reporting | [Tom's Hardware](https://www.tomshardware.com/tech-industry/artificial-intelligence/price-of-nvidias-vera-rubin-nvl72-racks-skyrockets-to-as-much-as-usd8-8-million-apiece-but-server-makers-margins-will-be-tight-nvidia-is-moving-closer-to-shipping-entire-full-scale-systems) | 2026-07-28 |
| GB200 public on-demand cross-check | Provider list price | [CoreWeave pricing](https://www.coreweave.com/pricing) | 2026-07-28 |
| B200 reserved-price cross-check | Aggregated market index | [Cloud GPU Price Analytics](https://cloud-gpus.com/price-analytics/) | 2026-07-28 |
| Ownership model and thresholds | Derived/synthetic | Assumptions and formulas above | 2026-07-28 |

## Missing evidence

- A customer-level Rubin OEM price rather than an analyst estimate.
- A single-rack, exact-facility liquid-cooling colocation quote.
- Public equivalent-rack Rubin rental and refresh-option pricing.
- Tax treatment, financing structure, insurance, and model-license costs.
- Measured useful utilization and resale market depth.
