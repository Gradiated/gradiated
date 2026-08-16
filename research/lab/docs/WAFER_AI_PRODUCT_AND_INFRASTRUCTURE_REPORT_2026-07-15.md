# Wafer AI product and inference-infrastructure report

Date: 2026-07-15  
Decision: what does Wafer's product and hosting strategy imply for launching our own optimized inference service after the research factory produces a winning result?

## Bottom line

Wafer is **not publicly disclosed as TensorWave-exclusive**. Wafer's own [Data Processing Addendum](https://www.wafer.ai/dpa), updated May 12, 2026, lists five infrastructure subprocessors used in connection with inference services:

- TensorWave;
- Vultr;
- Amazon Web Services;
- DigitalOcean; and
- Nebius.

For covered enterprise endpoints, Wafer says these suppliers provide compute and networking under contract and are configured in U.S. regions. It also mentions bare-metal arrangements. This is stronger evidence than a partner announcement: it is Wafer's customer-facing legal disclosure of companies that can process inference traffic.

TensorWave is clearly important to Wafer's AMD strategy. Wafer explicitly says its recent GLM-5.2 MI355X result used TensorWave capacity. But public evidence does not establish which live models run on which suppliers, the share of traffic on each, whether capacity is on-demand or committed, or whether any model-specific contract is exclusive.

The product lesson is equally important: Wafer has not launched as a raw GPU cloud or as a large undifferentiated model catalog. It packages research output into a small number of optimized endpoints, sells a standard and premium-speed tier, offers dedicated deployments, exposes familiar APIs and useful telemetry, and acquires traffic through OpenRouter and Vercel AI Gateway. That is the appropriate launch pattern for us.

Our likely path should be:

1. Rent, rather than buy, the production GPUs for the first model.
2. Launch the exact measured winning model/hardware/runtime combination on a dedicated node or small fixed pool.
3. Expose one OpenAI-compatible endpoint with streaming, tool use, correct metering, and strong observability.
4. List through an aggregator to obtain real traffic and public performance evidence, while also supporting direct customers.
5. Keep the control plane provider-neutral and source at least a primary and fallback capacity supplier; keep each optimized data plane model- and hardware-specific.
6. Add general serverless autoscaling, multiple regions, and a broad catalog only after traffic warrants them.

## What is confirmed and what is not

| Question | Finding | Confidence |
| --- | --- | --- |
| Is Wafer using TensorWave? | Yes. Wafer identifies TensorWave as an inference infrastructure subprocessor, and its GLM-5.2 MI355X announcement identifies TensorWave capacity. | High |
| Is TensorWave Wafer's exclusive GPU supplier? | No public evidence supports exclusivity; Wafer names four other inference infrastructure suppliers. | High that the disclosed supply footprint is multi-provider; unknown contract details |
| Does Wafer use Nebius only for experiments? | No such limitation is disclosed. Nebius appears in the inference-service subprocessor list, which permits production processing. The exact workloads are not public. | Medium-high |
| Does Wafer use DigitalOcean only for benchmarks? | DigitalOcean is both a co-author/benchmark partner and a disclosed inference infrastructure subprocessor. Exact production placement is not public. | Medium-high |
| Which provider hosts each live model? | Not disclosed publicly. | Unknown |
| Does Wafer own GPUs or data centers? | No public evidence found. Its DPA describes infrastructure providers and bare-metal arrangements, consistent with rented or contracted capacity. | Medium |
| Where is inference served? | Wafer's privacy policy says its inference is served from U.S. data centers. Its enterprise DPA also constrains covered processing to U.S. regions. | High for the cited policy scope; product configuration can change |
| What availability does it sell? | Its dedicated-inference SLA targets 99.9% monthly availability, with service credits. Third-party hosting failures are excluded from its definition of covered downtime. | High |

The absence of a public model-to-provider map is material. The named suppliers prove a diversified infrastructure posture, not simultaneous active capacity or failover for every model.

## Wafer's disclosed infrastructure portfolio

### TensorWave: latest AMD capacity and a strategic optimization partner

TensorWave is an AMD-only cloud offering MI300X, MI325X, MI355X, and newer AMD systems, bare metal, managed Kubernetes, high-speed storage, and cluster networking. Wafer's [GLM-5.2 announcement on LinkedIn](https://www.linkedin.com/company/wafer-ai) says the 2,626 output-token/s/node MI355X run used TensorWave capacity. TensorWave has also publicly featured Wafer's work and its CEO.

This makes TensorWave the clearest source for Wafer's latest AMD research and likely a meaningful production supplier. It does not prove that Wafer's GLM-5.2 serverless traffic is currently or exclusively hosted there.

TensorWave also offers physical GPU partitioning. That can matter for smaller models: [its inference page](https://tensorwave.com/solutions/gpu-workloads/ai-inference) advertises dividing a GPU into one, two, four, or eight logical devices to improve small-model utilization. For GLM-4.7 Flash, the economic question is whether such partitioning or multiple independent replicas can use an MI355X densely enough to overcome the cost of a large accelerator.

### DigitalOcean: AMD bare metal plus a co-development relationship

Wafer and DigitalOcean published a joint full-stack AMD study covering Kimi K2.5, DeepSeek V3.2, and GLM-5. DigitalOcean is also in Wafer's inference subprocessor list. [DigitalOcean's current platform documentation](https://docs.digitalocean.com/products/gradientai/) offers serverless and dedicated inference, GPU VMs, and eight-GPU bare-metal systems; AMD MI300X is explicitly available.

The relationship therefore goes beyond a one-off benchmark, but public sources do not identify which Wafer retail endpoints use DigitalOcean capacity.

### Vultr: heterogeneous NVIDIA and AMD bare metal

Vultr is in the inference subprocessor list. Its public documentation covers NVIDIA A100, L40S, H100, and GH200 plus AMD MI300X, and newer docs reference MI325X and MI355X bare metal. This makes it a plausible source for both NVIDIA and AMD optimized deployments and a useful hedge against a single cloud or accelerator ecosystem.

No public Wafer source found in this review maps a specific production model to Vultr.

### Nebius: NVIDIA research and production-capable supply

Nebius is in the inference subprocessor list. [Nebius's current compute catalog](https://docs.nebius.com/compute/virtual-machines/types) includes NVIDIA L40S, H100, H200, B200, B300, and RTX PRO 6000 systems, with availability varying by region and project.

This is directly relevant to us: our current Nebius use need not be treated as research-only infrastructure. If the winning GLM-4.7 configuration can be contracted at a competitive sustainable rate and meets operational requirements, Nebius can be considered for initial production. We must still verify the exact production rate, committed capacity, region, egress, support, and SLA rather than transfer an experimental hourly price.

### AWS: broad capacity and alternative silicon

AWS is in the inference subprocessor list. Wafer's technology page includes AWS Trainium in its hardware search surface, while AWS also offers NVIDIA H200, B200, and B300 instances. The public evidence does not reveal whether Wafer uses AWS for Trainium, NVIDIA GPUs, control-plane services, or some combination.

AWS provides capacity depth and enterprise procurement, but public on-demand economics may be unattractive for the first cost-leadership endpoint. It is more useful as a candidate to benchmark, a customer-required placement, or a resilience option than as an assumed default.

## The architecture implied by public product surfaces

Wafer's private topology is not published, but its APIs and disclosures support this conservative model:

```text
Direct customers       OpenRouter       Vercel AI Gateway
       \                   |                   /
        \-------- OpenAI/Anthropic-compatible edge --------/
                           |
                 auth, limits, metering,
                 routing, request IDs, ZDR
                           |
             model/tier/region-specific endpoint pool
                           |
          optimized engine + checkpoint + GPU deployment
                           |
   TensorWave | Vultr | AWS | DigitalOcean | Nebius
```

This diagram is an inference from public interfaces, not a claim about Wafer's internal implementation. What is directly visible:

- A shared serverless base URL at `https://pass.wafer.ai/v1`.
- OpenAI-compatible chat completions and an Anthropic-compatible messages endpoint.
- Dedicated inference hosts with separate endpoint-scoped authentication and telemetry.
- Model aliases and resolved model IDs, implying a routing layer.
- Per-request IDs and inspection records.
- Engine-level queue, KV-cache, and preemption telemetry surfaced through the metrics API.
- Direct distribution plus OpenRouter and Vercel AI Gateway integrations.
- Multiple infrastructure subprocessors behind Wafer-operated endpoints.

The important design split is a thin, portable control plane over specialized serving pools. Provider neutrality should not mean forcing one generic engine or artifact onto every GPU. It means retaining the ability to place each measured stack with a different supplier without changing the customer API.

## Wafer's product packaging

### 1. A narrow optimized serverless catalog

Wafer's [current direct model page](https://app.wafer.ai/models) lists five serverless models, while [OpenRouter currently exposes three Wafer-backed models](https://openrouter.ai/provider/wafer). This is a curated catalog, not a hundreds-model marketplace.

That is strategically sensible. Each endpoint is the deployment artifact of model-specific research. A large catalog would spread optimization and operational attention too thin and make the product indistinguishable from general inference providers.

### 2. Two economic/performance tiers for the same model

Wafer currently sells GLM-5.2 at `$1.20/M` input and `$4.10/M` output, and GLM-5.2 Fast at `$3.00/M` input and `$10.25/M` output. The premium tier promises higher per-stream throughput.

This monetizes the Pareto frontier rather than selecting one universal serving point. It is directly relevant to our background-agent objective: the first product can lead with the lowest-cost tier, then expose a faster tier from a different batching/topology configuration if demand exists.

### 3. Dedicated endpoints for enterprise/custom workloads

Wafer advertises custom dedicated endpoints configured around a customer's model, hardware, traffic, latency, and throughput needs. Its [dedicated endpoint documentation](https://docs.wafer.ai/dedicated-endpoints/overview) exposes endpoint-scoped APIs and hostnames, and its [SLA](https://www.wafer.ai/sla) promises 99.9% availability for dedicated inference.

Dedicated endpoints are a natural first revenue product for a small team because capacity and workload are known, utilization can be contracted, and model-specific optimization is easy to value. General serverless carries more demand uncertainty, abuse risk, routing complexity, and idle capacity.

### 4. Distribution before a large direct-sales funnel

Wafer is live through OpenRouter and Vercel AI Gateway in addition to its direct API. This gives it:

- immediate access to existing developers;
- public latency, throughput, uptime, and price comparisons;
- performance-based traffic allocation;
- standardized usage reconciliation and billing; and
- an independent launch story when a partner benchmarks it.

[OpenRouter's provider requirements](https://openrouter.ai/providers/apply) are a useful minimum launch contract: OpenAI-compatible streaming chat completions, accurate token usage, a `/models` endpoint, declared pricing/features/locations, published privacy/retention rules, reliable errors, and enough uptime to retain routing priority.

We should pursue an aggregator listing once one endpoint is stable, but not make the aggregator our only customer relationship. Direct endpoints retain margin, telemetry, enterprise control, and the ability to sell workload-specific optimization.

### 5. Customer-visible observability

Wafer's [dedicated metrics API](https://docs.wafer.ai/dedicated-endpoints/metrics-api) exposes request rate, TTFT and output-speed percentiles, end-to-end latency, cache-hit rate, token totals, status counts, queue depth, KV-cache usage, and preemptions. Its [request-inspection API](https://docs.wafer.ai/dedicated-endpoints/request-inspection) links a request ID to model resolution, token counts, cache reads, output speed, queue/transport clues, tool count, stream errors, and customer tags.

This is both a product feature and a research flywheel. Production traffic reveals the real workload distribution and bottlenecks, while customers can diagnose tail latency and cache misses without exposing internal worker routing. Our telemetry schema should be built once and feed:

- customer dashboards and incident debugging;
- billing and usage reconciliation;
- production SLO alerts; and
- the research factory's next optimization hypotheses.

### 6. Privacy, contracts, and model governance

Wafer publishes terms, a privacy policy, a DPA, an infrastructure subprocessor list, ZDR behavior, and a dedicated SLA. Its privacy policy says ordinary non-ZDR serverless content may be retained for up to 30 days and can be used to train internal speculative draft models; ZDR traffic is excluded. That distinction is explicit in the product.

Before launch, we similarly need to decide and document:

- whether prompt/completion bodies are stored;
- whether any traffic can improve draft models or serving systems;
- request-scoped or account-scoped ZDR;
- data regions and subprocessors;
- model licenses and acceptable use;
- retention of non-content operational metadata;
- security and incident response; and
- which failures count against an SLA.

This is not optional enterprise polish. Aggregators and serious customers require it to route real traffic.

## What we should build for the first launch

The first launch should prove that a research result can become a reliable, purchasable inference endpoint. It should not attempt to reproduce Wafer's whole current platform.

### Required before serving external traffic

- One pinned model/checkpoint/runtime/hardware deployment with a reproduced quality and cost claim.
- OpenAI-compatible `/v1/chat/completions`, streaming, cancellation, stable errors, and authoritative input/output/cache token counts.
- Tool-call and reasoning behavior required by the target agent workload.
- `/v1/models` with model identity, context/output limits, features, and pricing.
- API-key creation/revocation, per-key budgets, rate/concurrency limits, and abuse controls.
- Usage ledger and billing reconciliation derived from the same authoritative token events returned to clients.
- Request IDs and structured non-secret logs.
- Internal and customer-visible TTFT, output TPS, latency, error, queue, cache, utilization, and cost metrics.
- Continuous quality canaries and safe rollback to the last known-good serving image.
- Capacity health checks, draining, restart, model warmup, and node replacement.
- Terms, privacy/retention policy, model-license review, subprocessor disclosure, and a support/incident channel.

### Valuable immediately after the endpoint is stable

- OpenRouter integration for distribution and external performance monitoring.
- A direct usage/billing dashboard.
- A dedicated customer offering with contracted capacity and workload-specific optimization.
- A distinct low-cost background tier and fast interactive tier if measurements support both.
- A second capacity supplier or pre-qualified failover image.

### Defer until demand proves it is needed

- A broad model catalog.
- Multi-region active-active serving.
- Sophisticated general-purpose autoscaling across arbitrary GPU types.
- Owning GPUs or operating a data center.
- Kubernetes for a single-node or very small fixed deployment when a simpler supervisor and load balancer suffice.
- A custom general inference engine before model-specific evidence shows existing engines cannot reach the target.

## Recommended capacity strategy for us

### Separate experimental convenience from production economics

Continue using Nebius for fast, bounded experiments when it is the easiest safe venue. Select production placement only after measuring the exact winning artifact and obtaining a real capacity quote. A benchmark provider, a production supplier, and a failover supplier can be different.

The production comparison must include:

- committed or reserved GPU rate, not only transient on-demand price;
- minimum term and minimum GPU count;
- storage, egress, public IP, and load-balancer costs;
- support and replacement time;
- interruption and maintenance behavior;
- region and data-residency constraints;
- usable utilization after redundancy and headroom;
- checkpoint load and warmup time;
- network topology for multi-GPU models; and
- the right to deploy custom images, runtimes, kernels, and weights.

### Start with rented dedicated capacity

For the first endpoint, a dedicated bare-metal or fixed GPU node is preferable to an elaborate serverless fleet. It preserves the exact benchmarked stack, makes cost legible, and avoids cold-start/autoscaling work before there is traffic. Negotiate a short initial commitment or cancellable pilot, then reserve capacity when demand is proven.

Use one primary provider and one tested recovery path. True hot failover doubles idle capacity and may destroy the cost advantage; a warm or rapidly restorable fallback can be acceptable for an early background-agent product if the service envelope says so.

### Do not select AMD before measuring model density

Wafer's AMD results are a reason to test TensorWave, Vultr, and DigitalOcean—not a reason to commit to MI355X for GLM-4.7 Flash. Our current AWQ artifact is about 20.2 GB. A large-memory MI355X is attractive only if the runtime supports the exact model well and many replicas, partitions, or long-context KV workloads use its capacity efficiently.

For GLM-4.7 Flash, compare at least:

- the measured Nebius configuration that wins the research campaign;
- cheaper NVIDIA cards that fit the model and workload;
- dense multi-replica use of a large AMD GPU or node; and
- the effective contracted rate and available capacity for each.

The winning denominator is sustainable useful output tokens per dollar at the required quality—not per-GPU peak throughput.

### Keep a provider-neutral control plane and specialized data planes

Package each deployment as a content-addressed image/config/artifact with a common health, metrics, and inference contract. The edge can route among provider pools, but it should not hide hardware-specific engines, quantization, kernels, and topology inside a lowest-common-denominator serving layer.

A minimal provider adapter needs only:

- provision or attach capacity;
- deploy the pinned image and model artifact;
- expose health and metrics;
- drain and terminate safely; and
- report the full cost identity.

The research factory should be able to promote a measured experiment artifact into this deployment contract without manually reconstructing it.

## Suggested launch sequence

### Phase 0: prove the endpoint from the campaign result

- Finish a credible GLM-4.7 Flash quality and cost result.
- Keep the exact winning node running long enough for reliability, mixed-workload, and soak measurements.
- Produce one immutable serving image and deployment manifest.
- Price the endpoint from sustainable capacity and measured utilization, with margin.

### Phase 1: one-model private dedicated launch

- Serve one design partner or our own agent workload on fixed rented capacity.
- Offer a background-cost SLO rather than an unnecessarily strict interactive SLO.
- Validate billing, observability, quality canaries, recovery, and support with real requests.
- Use this traffic to continue model-specific optimization.

### Phase 2: public serverless and aggregator listing

- Add prepaid/direct billing and a small public capacity pool.
- Integrate with OpenRouter; pursue Vercel after public reliability and performance are credible.
- Publish reproducible benchmarks and obtain Artificial Analysis coverage.
- Expose a fast tier only if a separately measured operating point supports it.

### Phase 3: multi-provider capacity and GLM-5.2

- Qualify a second provider and automate image restoration/failover.
- Apply the research factory to GLM-5.2, using Wafer's TensorWave MI355X work as a direct competitor blueprint.
- Expand the catalog only when another model has a defensible quality/cost or speed wedge.

## Due-diligence questions to ask suppliers

Send the same workload and commercial request to TensorWave, Vultr, DigitalOcean, Nebius, and any other finalist:

1. Which exact GPU/node configurations and regions are available now, and in what quantity?
2. What are on-demand, one-month, three-month, and annual effective rates?
3. Is the hardware dedicated bare metal, VM, or partitioned? What isolation and performance variance apply?
4. Can we install custom ROCm/CUDA drivers, kernels, containers, OFED/network settings, and serving engines?
5. What are replacement, maintenance, and support response times?
6. What storage and checkpoint-load bandwidth are available, and what remains billed while compute is off?
7. What networking topology and measured collective performance apply within and between nodes?
8. What egress, IP, storage, control-plane, and support charges are additional?
9. What commitment, deposit, minimum fleet, and cancellation terms apply?
10. Can the provider support customer-data processing, ZDR, DPA, subprocessor disclosure, and required regions?
11. Can capacity expand without changing node identity or the contracted rate?
12. May we publish benchmark results and identify the provider?

The supplier decision should follow a matched benchmark and quote, not a generic GPU price table.

## Risks in copying Wafer too literally

- **Survivorship bias:** Wafer publishes strong results, not the full distribution of failed searches or infrastructure costs.
- **Vendor evidence:** AMD-cloud collaborations are useful but often co-authored and commercially aligned.
- **Unknown margins:** Public endpoint prices do not reveal underlying rates, reservation terms, or utilization.
- **Unknown routing:** The subprocessor list does not show which models or requests use each provider.
- **Small-company SLA limitations:** Wafer's dedicated SLA excludes failures of third-party hosting providers from covered downtime. We should decide whether that is acceptable to our customers rather than copy it automatically.
- **Catalog drift:** Wafer's direct and aggregator model lists differ and are changing quickly; operational complexity rises with every model/tier/provider combination.
- **Hardware transfer risk:** Wafer's MI355X result on GLM-5.2 does not establish GLM-4.7 Flash economics.

## Decision for our lab and product

Adopt Wafer's overall launch shape, not its presumed supplier choice:

- research across the whole stack;
- promote only measured winners;
- rent heterogeneous capacity from multiple suppliers;
- launch a narrow optimized endpoint catalog;
- use familiar APIs and distribution partners;
- expose telemetry as both a customer feature and research input; and
- sell the workload-specific Pareto frontier through cost, fast, and dedicated configurations.

For now, do not sign an exclusive TensorWave strategy, buy GPUs, or build a general serverless control plane. First finish the GLM-4.7 result, request matched quotes from the plausible suppliers, and launch the exact winning stack on the simplest reliable rented capacity.

## Sources and evidence record

Retrieved 2026-07-15. Product features, suppliers, prices, regions, and model catalogs are time-sensitive.

| Source | Evidence used | Type |
| --- | --- | --- |
| [Wafer DPA](https://www.wafer.ai/dpa) | TensorWave, Vultr, AWS, DigitalOcean, and Nebius inference subprocessors; U.S. covered processing; bare-metal language | Primary legal disclosure |
| [Wafer privacy policy](https://www.wafer.ai/privacy-policy) | U.S. inference, retention, ZDR, draft-model training, operational telemetry | Primary legal disclosure |
| [Wafer SLA](https://www.wafer.ai/sla) | 99.9% dedicated target, credits, exclusions | Primary legal disclosure |
| [Wafer homepage](https://www.wafer.ai/) | Serverless, fast tier, dedicated product, pricing, positioning | Primary product page |
| [Wafer direct model catalog](https://app.wafer.ai/models) | Current direct models, prices, ZDR support, API example | Primary live product |
| [Wafer serverless docs](https://docs.wafer.ai/serverless) | OpenAI/Anthropic compatibility, base URLs, serverless catalog and APIs | Primary documentation |
| [Wafer dedicated endpoint docs](https://docs.wafer.ai/dedicated-endpoints/overview) | Endpoint-scoped auth, model routing, metrics, request inspection | Primary documentation |
| [Wafer metrics API](https://docs.wafer.ai/dedicated-endpoints/metrics-api) | Customer-visible and engine telemetry | Primary documentation |
| [Wafer request inspection](https://docs.wafer.ai/dedicated-endpoints/request-inspection) | Request IDs, tail/cache/error debugging, tags | Primary documentation |
| [Wafer LinkedIn](https://www.linkedin.com/company/wafer-ai) | TensorWave supplied MI355X capacity for GLM-5.2 | First-party announcement |
| [TensorWave inference](https://tensorwave.com/solutions/gpu-workloads/ai-inference) | AMD products, partitioning, bare metal/Kubernetes/network capabilities | Supplier product page |
| [DigitalOcean AI-Native Cloud](https://docs.digitalocean.com/products/gradientai/) | Current GPU and inference product surface | Supplier documentation |
| [Vultr AMD hardware requirements](https://docs.vultr.com/inference-cookbook/rocm/getting-started/hardware-requirements) | MI300X/MI325X support | Supplier documentation |
| [Vultr GPU variants](https://docs.vultr.com/public/doc-assets/pdfs/collection_item/products-compute-bare-metal-explore-gpu-variants.pdf) | Heterogeneous NVIDIA and AMD bare-metal catalog | Supplier documentation |
| [Nebius GPU types](https://docs.nebius.com/compute/virtual-machines/types) | Current NVIDIA GPU portfolio and regional caveat | Supplier documentation |
| [AWS accelerated instance types](https://docs.aws.amazon.com/ec2/latest/instancetypes/ac.html) | NVIDIA and AWS accelerator portfolio | Supplier documentation |
| [OpenRouter Wafer provider page](https://openrouter.ai/provider/wafer) | Current aggregator model catalog | Independent live marketplace |
| [OpenRouter provider requirements](https://openrouter.ai/providers/apply) | API, metering, routing, privacy, and uptime launch contract | Marketplace documentation |
| [Vercel GLM-5.2 Fast launch](https://vercel.com/changelog/glm-5-2-fast-via-wafer-now-available-on-ai-gateway) | Partner distribution and benchmark | Partner-reported measurement |
