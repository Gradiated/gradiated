# Vera Rubin multi-model serving and startup ownership

Date: 2026-07-28

## Decision

A startup can purchase and own one Vera Rubin NVL72 and run several models on
it. The recommended first-rack arrangement is customer-owned equipment in a
specialist high-density colocation facility, with the OEM and colocation
operator contracted together before the purchase order. Do not build a private
data centre for one rack.

This conclusion is falsified if the selected OEM will not sell a single-rack
configuration, no target colocation facility will contract the required power
and heat-rejection envelope, or scope-matched benchmarks show that model
partitioning destroys the intended token-cost advantage.

## Multi-model serving

The rack is one 72-GPU NVLink domain, but serving software can allocate whole
GPU groups to independent model workers. NVIDIA Dynamo explicitly supports
multi-model serving, workers with configurable tensor/pipeline/data
parallelism, dynamic discovery, KV-aware routing, and independently scaled
prefill and decode pools.

A sensible physical allocation is therefore a set of topology-aware GPU
gangs, for example:

- one large model using 16 or 32 GPUs;
- a second model using 8 or 16 GPUs;
- several smaller 4- or 8-GPU replicas;
- unallocated GPUs retained for burst capacity, maintenance, or model
  transition.

This is illustrative, not a recommended K3 mapping. Each model needs an
exact-shape throughput and topology sweep.

Capacity can shift in two ways:

1. Traffic can move immediately among already-resident replicas.
2. GPUs can be drained, reassigned, and loaded with another model. This is
   elastic but not instantaneous: model loading, engine construction, CUDA
   graph capture, and cache warming remain on the transition path.

NVIDIA ModelExpress and ModelStreamer can distribute or stream model weights
to workers, reducing cold-start cost. For predictable production operation,
keep the highest-volume models resident and use a smaller elastic pool for
reallocation. Do not rely on frequent whole-rack model swaps as the primary
load-balancing mechanism.

The rack has 20.7 TB of HBM4 and 54 TB of CPU memory, so memory capacity makes
multi-model residency plausible. Performance is constrained by each model's
parallelism, active parameters, communication, KV/cache geometry, and SLO—not
only by whether its weight bytes fit.

## Ownership and facility requirement

Vera Rubin NVL72 is a purchasable OEM system, not cloud-only hardware. NVIDIA
lists Dell, HPE, Lenovo, Supermicro, and other system builders in the production
ecosystem. NVIDIA says production shipments begin in fall 2026; HPE states its
NVL72 system will be available in December 2026.

Ownership does not remove the data-centre requirement. Supermicro describes:

- a liquid-to-air option rated for one 200 kW rack;
- four 110 kW rack power shelves with redundant power supplies;
- 48U and 52U enclosures designed for high-density direct liquid cooling.

The power-shelf number is installed/redundant capacity, not a claim that the
rack continuously draws 440 kW. The precise contracted power, coolant,
pressure, temperature, flow, redundancy, floor loading, network, and fire
requirements must come from the selected OEM's site survey.

A normal office or ordinary low-density retail colocation cage is unsuitable.
A specialist AI/HPC colocation provider can host customer-owned equipment and
provide the utility power, heat rejection, liquid loop/CDU, physical security,
remote hands, carrier connectivity, and redundant facility infrastructure.

## Recommended procurement path

1. Run Rubin in cloud or managed bare metal during software bring-up.
2. Obtain competing single-rack proposals from at least two OEMs, including
   warranty, spares, installation, and delivery date.
3. In parallel, reserve a 200 kW-class specialist colocation deployment with a
   written OEM compatibility/site survey.
4. Buy one rack only after a measured workload plan can keep it economically
   occupied across several models.
5. Use customer-owned colo for the first one to four racks. Consider dedicated
   halls or owned facilities only once the plan reaches multi-megawatt scale.

With several hundred million dollars of capital, affordability is not the
binding issue. Allocation, delivery timing, facility readiness, operational
staffing, model demand, and software efficiency are.

The full NVIDIA platform can include separate Vera CPU, Groq 3 LPX, storage,
and Spectrum-6 networking racks. One NVL72 compute rack remains independently
useful, but do not transfer performance claims that explicitly rely on LPX or
the full five-rack platform to a stand-alone NVL72 purchase.

## Evidence classes and sources

| Claim | Evidence class | Source | Retrieved |
|---|---|---|---|
| 72 GPUs, 20.7 TB HBM4, 54 TB CPU memory, NVLink 6 | Vendor-reported, preliminary | [NVIDIA NVL72 specifications](https://www.nvidia.com/en-us/data-center/vera-rubin-nvl72/) | 2026-07-28 |
| Multi-model frontend and dynamic workers | Vendor documentation | [NVIDIA Dynamo Frontend](https://docs.nvidia.com/dynamo/dev/knowledge-base/modular-components/frontend/overview) | 2026-07-28 |
| P2P and streamed model loading | Vendor documentation | [NVIDIA Dynamo ModelExpress](https://docs.nvidia.com/dynamo/dev/kubernetes-deployment/model-loading/model-express) | 2026-07-28 |
| OEM ecosystem and fall production shipments | Vendor-reported | [NVIDIA production announcement](https://nvidianews.nvidia.com/news/vera-rubin-full-production-agentic-ai-factory) | 2026-07-28 |
| Single-rack 200 kW liquid-to-air option and power shelves | OEM-reported | [Supermicro DCBBS announcement](https://ir.supermicro.com/news/news-details/2026/Supermicro-Introduces-DCBBS-Blueprints-for-NVIDIA-Vera-Rubin-NVL72-and-NVIDIA-HGX-Rubin-NVL8-Built-to-Scale-from-5MW-to-1GW-as-an-End-to-End-Total-Solution/default.aspx) | 2026-07-28 |
| HPE product availability in December 2026 | OEM-reported | [HPE AI Factory announcement](https://www.hpe.com/fr/fr/collaterals/collateral.a50015156frfr.html) | 2026-07-28 |
| Example model allocation and ownership recommendation | Inferred | Derived from the sources and operating requirements above | 2026-07-28 |

## Missing evidence

- A firm single-rack OEM quote, delivery allocation, and exact bill of
  materials.
- A signed colocation proposal and completed OEM site survey.
- K3 and portfolio-model throughput by GPU-group size.
- Model transition time from local storage and from an already-resident peer.
- Operational staffing, support SLA, insurance, and spare-parts terms.
