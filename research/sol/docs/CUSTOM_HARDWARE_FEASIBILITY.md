# Custom hardware feasibility audit

**Subject:** `glm-dsa-moe-custom-upper-bound` in [`configs/glm-5.2-ledger-roofline-v1.json`](../configs/glm-5.2-ledger-roofline-v1.json)  
**Evidence cutoff:** 2026-07-12  
**Checked snapshot:** [`validation/results/custom-hardware-feasibility-2026-07-12.json`](../validation/results/custom-hardware-feasibility-2026-07-12.json)

## Executive verdict

**Continue the model/software research; do not underwrite a tapeout from this profile.** The nominal 12 TB/s HBM path, 1.6 TB/s scale-up fabric, and 2 PFLOP/s compute engines are physically plausible. They are also at or below current or announced commodity accelerator peaks. NVIDIA specifies 22 TB/s HBM, 3.6 TB/s NVLink, and 4 dense BF16 PFLOP/s for Rubin, while AMD has announced 19.6 TB/s and 432 GB for MI450. A custom chip that merely realizes the profile's headline rates would arrive without a clear hardware advantage.

The profile's checked 5.38x relative ideal speedup is **not performance, energy, or cost evidence**. It is the output of a 19-action mechanism fixture with only 222,298,112 FLOPs. Most of its advantage comes from assumed fixed and coordination latencies, especially a 50 ns charge per expert-fabric message. Replacing only the fixture's throughput totals with the custom totals improves its serial diagnostic by just 1.054x. Replacing only fixed and coordination totals improves it by 4.079x.

Capacity is the harder constraint. The modeled GLM-5.2 residency is 1.97–2.07 TB at BF16, 1.10–1.20 TB at native FP8, and 770–868 GB with expert-selective NVFP4. Those variants require respectively 7–8, 4–5, and 3–4 devices at 288 GB each. A one-package NVFP4 target needs 17–19 future 48 GB HBM4E stacks. That is beyond TSMC's announced 2027 12-stack-plus package and only arithmetically fits its announced 2028 20-stack package; there is no supplier-backed power, yield, usable-capacity, or cost margin.

The investable hypothesis is therefore narrower and better:

> Model-specific changes can reduce active bytes, messages, and general-purpose control overhead enough to lower quality- and SLO-matched cost per token on commodity hardware first; custom silicon is justified only if a material residual advantage remains against the commodity hardware available at tapeout time.

The current result is a **conditional go for research and a no-go for silicon commitment**.

## Evidence discipline

This audit uses the following labels:

- **Shipped fact:** a currently available product specification from its vendor.
- **Production vendor claim:** a vendor says production has started, but the relevant product may not yet be broadly deployed; preliminary specifications remain provisional.
- **Announced roadmap:** a dated future product or packaging capability, not a shipped fact.
- **Derived bound:** arithmetic from cited facts, with no claim that the resulting design is buildable or economical.
- **Foundry assumption:** a range selected for underwriting or simulation, not a vendor prediction.
- **Unknown:** evidence requiring measurement, a supplier quote, or physical design.

Vendor peak rates are not directly interchangeable. Precision, sparsity, direction convention, topology, and measurement method differ. Every comparison below preserves those caveats.

## What the fixture actually establishes

The checked result in [`experiments/glm-5.2/decode-ledger-roofline-v1.json`](../experiments/glm-5.2/decode-ledger-roofline-v1.json) compares two modeled assumption vectors, not two systems.

| Diagnostic | Modeled H200-like | Custom profile | Ratio |
|---|---:|---:|---:|
| Optimistic critical path | 48.622 µs | 9.037 µs | 5.380x |
| Serial action sum | 57.134 µs | 11.065 µs | 5.164x |
| Optimistic committed tokens/s | 61,701 | 331,961 | 5.380x |

The custom serial sum decomposes as follows:

| Component | Time | Share |
|---|---:|---:|
| Fixed | 7.400 µs | 66.9% |
| Coordination | 3.082 µs | 27.9% |
| Throughput | 0.583 µs | 5.3% |

Two counterfactual substitutions expose the source of the apparent gain:

- Custom throughput totals with baseline fixed and coordination totals: **1.054x** serial improvement.
- Custom fixed and coordination totals with baseline throughput totals: **4.079x** serial improvement.

The fixture's MoE dispatch moves only 24,576 aggregate bytes in 56 messages. Under the custom profile it takes 3.015 µs: 0.015 µs serialization, 0.200 µs fixed cost, and 2.800 µs message cost. Message penalties are 92.9% of this modeled action, while serialization is 0.5%. Increasing fabric bandwidth cannot materially improve that action unless the model/runtime also reduces message count or removes protocol and scheduling latency.

The baseline is named `h200-like-modeled`, but its HBM path is 3.35 TB/s. A shipped H200 is specified at 4.8 TB/s. The fixture is therefore not a calibrated H200 benchmark, and the 5.38x ratio must not be presented as a speedup over H200, vLLM, Fireworks, Baseten, or any production serving system.

The fixture still has value: it identifies a hypothesis worth testing. For this sparse decode path, packetization, expert placement, persistent scheduling, and fusion may matter more than peak arithmetic or link bandwidth.

## Commodity baseline, 2026–2028

| Accelerator | Evidence | Memory | HBM peak | Scale-up peak | Relevant compute | Power evidence |
|---|---|---:|---:|---:|---:|---:|
| NVIDIA H200 SXM | Shipped fact | 141 GB | 4.8 TB/s | 0.9 TB/s NVLink | ≈0.990 dense BF16 PFLOP/s, derived as half the vendor's sparsity-marked figure | Up to 0.7 kW |
| NVIDIA B300 SXM | Shipped fact | 288 GB | 8.0 TB/s | 1.8 TB/s NVLink | Not used in this comparison | 1.4 kW GPU; 14.5 kW DGX B300 |
| AMD MI355X | Shipped fact | 288 GB | 8.0 TB/s | 1.0752 TB/s across seven advertised links | 2.5166 dense BF16 PFLOP/s | 1.4 kW board |
| NVIDIA Rubin GPU | Production vendor claim; specifications marked preliminary/up to | 288 GB | 22.0 TB/s | 3.6 TB/s NVLink | 4.0 dense BF16 PFLOP/s | Not stated on the cited product page |
| AMD MI450 series | Announced 2H 2026 roadmap | 432 GB | 19.6 TB/s | Not stated in the cited sources | Not used in this comparison | Not stated in the cited sources |

Sources: [NVIDIA H200](https://www.nvidia.com/en-us/data-center/h200/), [NVIDIA HGX B300](https://www.nvidia.com/en-us/data-center/hgx/), [NVIDIA DGX B300 guide](https://docs.nvidia.com/dgx/dgxb300-user-guide/introduction-to-dgxb300.html), [NVIDIA B300 power documentation](https://docs.nvidia.com/datacenter/dps/versions/latest/sdk/user/topology/index.html), [AMD MI355X](https://www.amd.com/en/products/accelerators/instinct/mi350/mi355x.html), [AMD CDNA 4 white paper](https://www.amd.com/content/dam/amd/en/documents/instinct-tech-docs/white-papers/amd-cdna-4-architecture-whitepaper.pdf), [NVIDIA Rubin](https://www.nvidia.com/en-us/data-center/vera-rubin-nvl72/), [NVIDIA Rubin production announcement](https://nvidianews.nvidia.com/news/vera-rubin-full-production-agentic-ai-factory), and [AMD Helios/MI450 roadmap](https://www.amd.com/en/blogs/2025/amd-helios-ai-rack-built-on-metas-2025-ocp-design.html).

The strategic comparison is not H200. A custom program started now would encounter Rubin-, MI450-, or later-generation products before production. Its economic baseline must move with the tapeout schedule. Against those baselines, 12 TB/s HBM, 1.6 TB/s fabric, and 2 PFLOP/s are requirements, not differentiation.

## Assumption-by-assumption audit

### 12 TB/s HBM path

**Verdict: plausible bandwidth, unspecified capacity and power.**

Micron's shipped HBM3E provides more than 1.2 TB/s per placement, so 12 TB/s requires ten placements at that generation. Current HBM4 changes the arithmetic: Micron states more than 2.8 TB/s for a 36 GB stack and Samsung states up to 3.3 TB/s for its 36 GB stack. Five Micron stacks or four Samsung stacks cross 12 TB/s, but provide only 180 GB or 144 GB of raw capacity. Samsung's sampled 48 GB HBM4E at up to 3.6 TB/s would cross the rate with four stacks and provide 192 GB. Sources: [Micron HBM3E](https://www.micron.com/products/memory/hbm/hbm3e), [Micron HBM4](https://www.micron.com/products/memory/hbm/hbm4), [Samsung HBM4](https://news.samsung.com/global/samsung-ships-industry-first-commercial-hbm4-with-ultimate-performance-for-ai-computing), and [Samsung HBM4E sample announcement](https://semiconductor.samsung.com/news-events/news/samsung-electronics-begins-shipment-of-industry-first-hbm4e-samples/).

| Memory path | Evidence | Peak per stack | Stacks to cross 12 TB/s | Raw capacity at minimum stack count |
|---|---|---:|---:|---:|
| Micron HBM3E | Shipped fact | >1.2 TB/s | 10 | 240–360 GB, depending on 24/36 GB stack |
| Micron HBM4 | Volume shipment vendor claim | >2.8 TB/s | 5 | 180 GB |
| Samsung HBM4 | Commercial shipment vendor claim | Up to 3.3 TB/s | 4 | 144 GB |
| Samsung HBM4E | Sampled, not mass-production evidence | Up to 3.6 TB/s | 4 | 192 GB |

This means the profile's HBM **bandwidth** is no longer aggressive. Its missing **capacity** field is decisive. A capacity-driven GLM package could contain far more theoretical bandwidth than the profile needs, but would pay for controllers, interposer perimeter, HBM power, thermals, and packaging yield. Sustained workload bandwidth and energy per delivered byte are unknown.

Evidence required before feasibility status can improve:

- Exact tensor placement and usable-capacity margin, including KV, allocator fragmentation, runtime, and redundancy.
- Number and width of HBM PHYs, controller area, traffic efficiency, and sustained model-trace bandwidth.
- Supplier-backed stack capacity, power, temperature, and qualification window.
- Post-layout or silicon energy per bit, not a peak-bandwidth data sheet.

### Full-model capacity and package aggregation

| Model representation | Modeled total residency | 288 GB devices | 432 GB devices | 960 GB devices |
|---|---:|---:|---:|---:|
| BF16 | 1.968–2.067 TB | 7–8 | 5 | 3 |
| Native FP8 | 1.104–1.203 TB | 4–5 | 3 | 2 |
| Expert-selective NVFP4 | 0.770–0.868 TB | 3–4 | 2–3 | 1 |

The 960 GB column is a package thought experiment, not a product baseline. At 48 GB per HBM4E stack, expert-selective NVFP4 needs 17–19 stacks before operational margin. TSMC announced a 9.5-reticle CoWoS capability with more than 12 HBM stacks for volume production in 2027, and later announced a 14-reticle, 20-HBM-stack capability planned for 2028. Sources: [TSMC 2025 packaging roadmap](https://pr.tsmc.com/english/news/3228) and [TSMC 2026 packaging roadmap](https://pr.tsmc.com/english/news/3302).

Therefore:

- BF16 and native FP8 require multi-package aggregation under every cited 2026 accelerator capacity.
- Expert-selective NVFP4 still requires 3–4 Rubin/B300/MI355X-class 288 GB devices or 2–3 announced 432 GB MI450-class devices.
- One-package NVFP4 is outside the announced 2027 package envelope and merely fits the announced 2028 stack-count envelope on arithmetic. It has no demonstrated usable-capacity margin, package power, thermal solution, assembly yield, or economic yield.

### 1.6 TB/s expert fabric

**Verdict: plausible nominal bandwidth; useful all-to-all performance unproven.**

The figure is below NVIDIA's 1.8 TB/s B300 and 3.6 TB/s Rubin NVLink headline rates, and above MI355X's 1.0752 TB/s sum of seven advertised links. It may be a reasonable per-device target, but the profile does not define whether it is one-way, bidirectional, injection, bisection, or aggregate bandwidth. Vendor figures also use different conventions.

UALink 1.0 specifies 200G lanes but leaves implementation latency to device and retimer vendors. Its round-trip section asks those vendors to publish their own acknowledgement, release, and retimer latencies; it uses a 1,000 ns link RTT as an explanatory sizing example, not a guaranteed limit. That does not invalidate a proprietary low-latency fabric, but it provides no support for the profile's 50 ns per-message charge. Source: [UALink 200G 1.0 specification](https://ualinkconsortium.org/wp-content/uploads/2025/04/UALink200_Specification_v1.0_Evaluation_Copy.pdf).

Evidence required:

- Topology, rank count, link direction convention, routing, and oversubscription.
- Trace-driven useful bandwidth for GLM expert all-to-all, including packet headers and small-message efficiency.
- p50/p95/p99 latency under simultaneous HBM, collective, and scheduler traffic.
- Switch, SerDes, retimer, and package-link energy per delivered payload bit.
- Failure containment and spare-link behavior, which affect sellable yield and availability.

### Compute engines

**Verdict: peak rate plausible; contract incomplete.**

The profile's 2 PFLOP/s matrix and attention targets are below shipped MI355X's 2.5166 dense BF16 PFLOP/s and below Rubin's preliminary 4 dense BF16 PFLOP/s. Peak rate alone is not differentiating. The profile omits datatype, sparsity, accumulation, numerical behavior, utilization, and quality. Its fixed charges of 1.0 µs for matrix, 0.8 µs for attention, and 0.5 µs for top-k matter more than their throughput terms in this fixture.

NVIDIA reports about 2.5 µs host launch overhead for repeated straight-line CUDA graphs on its test platform, while a ten-node graph of minimal kernels took about 7 µs of device runtime. Those numbers are not physical lower bounds, but they show that the profile's fixed charges require fusion, persistent device-side scheduling, or dedicated control rather than conventional host-launched kernels. Source: [NVIDIA CUDA graph launch study](https://developer.nvidia.com/blog/constant-time-launch-for-straight-line-cuda-graphs-and-other-performance-enhancements/).

Required evidence is a precision contract, quality delta, achieved utilization on real tensor shapes, compiler schedule, SRAM/HBM traffic, and post-layout area and power. A 2 PFLOP/s label without those fields is not a compute block specification.

### 150 TB/s on-chip cache

**Verdict: plausible only as aggregate bandwidth across a small, heavily banked local SRAM; capacity and energy are unknown.**

At an illustrative 2 GHz, 150 TB/s is 75,000 bytes per cycle, equivalent to 9,375 independent 64-bit banks returning one word each cycle. This is a distributed fabric/floorplan requirement, not a single cache port.

There is a specialized precedent. NVIDIA's Groq 3 LPX disclosure lists 40 PB/s across 256 LPUs and 128 GB of SRAM. Dividing those vendor totals gives 156.25 TB/s and 0.5 GB SRAM per LPU. That supports the order of magnitude for a small local working set, not for storing GLM weights or a large KV cache. Source: [NVIDIA Vera Rubin platform page, Groq 3 LPX section](https://www.nvidia.com/en-us/data-center/vera-rubin-nvl72/).

The design needs a measured hot-set distribution, target capacity, bank and port plan, NoC bisection, floorplan wire lengths, conflict rate, and energy per access. Until then, 150 TB/s is a throughput scalar without a realizable memory hierarchy.

### Fixed, message, synchronization, and scheduler latency

**Verdict: the highest-risk assumptions in the profile.**

The custom profile assumes:

- 50 ns per expert-fabric message plus 200 ns fixed network cost.
- 100 ns fixed barrier cost plus 10 ns per participant.
- 200 ns fixed scheduler cost plus 20 ns per request and 2 ns per token.
- 50–200 ns fixed memory/cache costs.

These values may be reachable for particular die-local circuits. They are not evidenced end-to-end values for a multi-package inference system. Clock-domain crossings, SerDes, switches, queues, coherency or ordering, scheduler decisions, and software visibility all consume the same budget. Since fixed and coordination terms account for 94.7% of the custom fixture's serial time, a modest miss changes the result materially.

The next simulator revision should replace each scalar with a latency distribution and provenance: die-local, package-local, link-local, host-visible, or collective. The acceptance gate should be p99 trace replay under contention, not a no-load average.

## Power, package, area, yield, and NRE

The profile has no fields for memory capacity, precision, die or package area, power, yield, or NRE. It is a timing vector rather than a buildable accelerator.

Two sensitivities show why the omissions matter. These are explicit assumptions, not measurements:

| Path | Energy assumption | Dynamic power at profile bandwidth |
|---|---:|---:|
| 12 TB/s HBM traffic | 2 / 3 / 5 pJ per bit | 192 / 288 / 480 W |
| 150 TB/s SRAM traffic | 0.1 / 0.25 / 0.5 pJ per bit | 120 / 300 / 600 W |

These two paths alone can span 312–1,080 W before tensor compute, control, NoC, SerDes, leakage, voltage conversion, and cooling overhead. They do not predict product power; they identify the supplier and physical-design evidence needed.

Current shipped systems illustrate the integration burden. AMD specifies MI355X at 1.4 kW, NVIDIA documents B300 at 1.4 kW, and DGX B300 at 14.5 kW for an eight-GPU system. NVIDIA's [GB300 NVL72 documentation](https://docs.nvidia.com/enterprise-reference-architectures/nvl72-ai-factory/latest/components.html) allows up to 142 kW at rack scale. A model-specific accelerator does not escape those facility costs merely by removing software abstractions.

Before any tapeout decision, the evidence pack must include:

| Gate | Minimum evidence |
|---|---|
| Model contract | Frozen tensor shapes, active parameters, precision by tensor, quality suite, KV policy, and worst-case residency |
| Architecture | Cycle model tied to the ledger, queue depths, topology, deadlock analysis, error handling, and utilization distributions |
| Physical design | Synthesized netlist, placed-and-routed representative blocks, SRAM compiler outputs, HBM/SerDes PHY plan, timing corners, and power maps |
| Package | Qualified HBM configuration, interposer/substrate dimensions, bump and routing plan, warpage, thermals, assembly flow, and test strategy |
| Yield | Logic die defect model, known-good-die rate, HBM and interposer yield, assembly yield, repair/redundancy, and sellable-bin distribution |
| Cost | Foundry, HBM, package, test, substrate, board, cooling, host, and facility quotes at realistic volumes |
| NRE | Masks, IP, EDA, verification, firmware, compiler, bring-up, characterization, staffing, and risk-adjusted respin reserve |
| Operations | Reliability target, spare policy, field replacement, software support horizon, security response, and contracted utilization |

No public primary source supplies the design-specific yield, quote, or NRE needed for this package. Roadmap stack count is not evidence of economical yield.

## Feasibility intervals for simulation

These intervals are underwriting inputs, not forecasts. Peak product specifications are discounted where noted; latency, cache, and power ranges are explicit assumptions to test.

| Interval | Sustained HBM | Useful scale-up | Compute action fixed | Fabric message | On-chip cache | Accelerator power |
|---|---:|---:|---:|---:|---:|---:|
| Conservative shipped 2026 | 4.4–5.6 TB/s | 0.484–1.17 TB/s | 2.0–5.0 µs | 0.25–1.0 µs | 50–100 TB/s | 1.0–1.4 kW |
| Base 2026–2027 | 9.8–15.4 TB/s | 0.9–2.52 TB/s | 0.8–2.5 µs | 0.10–0.50 µs | 100–175 TB/s | 1.2–1.8 kW |
| Aggressive custom 2027–2028 | 15.84–24.0 TB/s | 2.34–3.06 TB/s | 0.3–1.0 µs | 0.05–0.20 µs | 150–250 TB/s | 1.4–2.5 kW |

Derivation and interpretation:

- **Conservative shipped:** 55–70% of an 8 TB/s HBM peak; 45% of MI355X to 65% of B300 scale-up headline bandwidth. Fixed latency, cache, and power are bounded by current product behavior and explicit assumptions.
- **Base:** 50–70% of announced MI450/Rubin HBM peaks and 50–70% of B300/Rubin scale-up peaks. It mixes production and roadmap products and should never be labeled shipped evidence.
- **Aggressive custom:** assumes a multi-stack HBM4E package and 65–85% of Rubin's scale-up headline rate. Its latency and cache ranges are design targets without silicon evidence. The upper power range implies nonstandard package and facility planning.

Simulation should sweep the full Cartesian ranges and report sensitivity, not choose the profile's favorable corner. A result that only survives the aggressive interval is not a business case.

## Replacement profiles with deployment scope

The original profile should be retained only as an explicitly labeled upper bound. The following point profiles are better simulator defaults because each declares its model representation, rank count, capacity, and deployment power. They are not interchangeable accelerator specifications: peak compute comes from vendor evidence where available, while fixed latency, cache, useful-link utilization, and top-k rate remain foundry assumptions.

| Profile | Deployment scope | Model representation | Raw capacity and headroom | Per-rank sustained HBM | Per-rank useful fabric | Fixed compute / message | Power before hosts and switches | Status |
|---|---|---|---|---:|---:|---:|---:|---|
| `commodity_2026_nvfp4_four_rank` | 4 ranks × 288 GB | Expert-selective NVFP4 | 1,152 GB; 24.6% above modeled maximum | 5.0 TB/s | 0.75 TB/s | 2.5 / 0.50 µs | 5.6 kW | Capacity-feasible with shipped component classes; select one product and measure it |
| `hbm4_2026_2027_fp8_three_rank` | 3 ranks × 432 GB | Native FP8 | 1,296 GB; 7.2% above modeled maximum | 12.0 TB/s | 1.6 TB/s | 1.5 / 0.20 µs | 4.8 kW | Arithmetic fit against an announced 432 GB class; not shipped evidence |
| `hbm4_2026_2027_bf16_five_rank` | 5 ranks × 432 GB | BF16 | 2,160 GB; 4.3% above modeled maximum | 12.0 TB/s | 1.6 TB/s | 1.5 / 0.20 µs | 8.0 kW | Arithmetic fit with little raw margin; not shipped evidence |
| `custom_2028_nvfp4_twenty_stack_package` | 1 logical multi-chiplet package × 20 48 GB stacks | Expert-selective NVFP4 | 960 GB; 9.5% above modeled maximum | 18.0 TB/s package-local | 2.7 TB/s package-local | 0.7 / 0.10 µs | 2.2 kW assumption | Roadmap arithmetic only; not physically signed off |

The first three HBM figures are **per rank**, not shared aggregate rates. Summing them is valid only for perfectly balanced, rank-local traffic; remote expert or KV traffic consumes fabric and can destroy that scaling. The 2028 profile is one logical accelerator but almost certainly a multi-chiplet package. Its 20 stack count is capacity-driven, and its 18 TB/s simulator rate deliberately does not assume that every stack's sampled headline bandwidth can be sustained simultaneously within the power envelope.

Recommended point parameters are in the checked JSON snapshot. Their key timing changes relative to the original upper bound are:

- The shipped four-rank profile uses 1.0 µs HBM fixed cost, 0.75 µs fabric fixed cost, 0.50 µs per message, and 0.50 µs barrier fixed cost.
- The HBM4 three- and five-rank profiles use 0.5 µs HBM and fabric fixed costs, 0.20 µs per message, and 0.25 µs barrier fixed cost.
- The 2028 research profile uses 0.3 µs HBM and fabric fixed costs, 0.10 µs per message, and 0.15 µs barrier fixed cost. Even this is less favorable than the original 50 ns message and 100 ns barrier assumptions.

Only `commodity_2026_nvfp4_four_rank` is capacity-feasible from shipped component classes. It is still a synthetic envelope, not a claim that one shipped product achieves every point simultaneously. The two 432 GB profiles depend on announced MI450-class capacity. The 20-stack profile depends on both sampled HBM4E and TSMC's 2028 package roadmap and must remain disabled in business-case outputs until supplier and physical-design gates are met.

## Explicit kill criteria

1. **No tapeout without software proof.** A quality- and SLO-matched commodity implementation must first demonstrate at least 1.5x lower measured fully loaded cost per token on two models.
2. **Require a silicon residual.** Kill the custom-hardware thesis if, after Rubin/MI450-class baselines, persistent kernels, and model changes, the remaining gain attributable to silicon is below 30%.
3. **Validate sparse coordination.** Kill the current profile if end-to-end expert dispatch cannot sustain 60% of declared useful fabric bandwidth or p99 coordination exceeds the modeled value by more than 2x.
4. **Capacity must fit a qualified package.** Kill any one-package plan that needs more HBM stacks than a supplier-qualified package supports after usable-capacity, power, thermal, and yield margin.
5. **Fund the power envelope.** Kill the package if landed accelerator power exceeds 1.5 kW without a funded liquid-cooling path, or the serving rack exceeds 150 kW without facility and utilization economics.
6. **NRE must repay under price decline.** Kill the program if foundry, HBM, package, test, and risk-adjusted respin cost cannot be repaid within three years by contracted token volume under an explicit incumbent price-decline curve.
7. **Do not claim 5x from this fixture.** No 5x claim until the full active GLM ledger, contention, queueing, quality, measured timing, energy, and fully loaded dollars are all present.

These are initial governance thresholds. They should be tightened when supplier quotes and measured baselines exist, not relaxed to preserve the thesis.

## Business interpretation and next proof

The company should not compete on a promise that custom hardware can reach 12 TB/s or 2 PFLOP/s; commodity roadmaps have already passed those figures. It can compete if model-specific co-design removes work that commodity systems must still perform.

The most credible experiments from this audit are:

1. **Reduce expert messages, not just their serialization time.** Co-locate frequently co-activated experts, aggregate dispatches, and change routing only where quality holds. The fixture says message count is the leverage point.
2. **Prove the local hot set.** Measure whether DSA indices, routing metadata, and a small expert/KV working set have enough locality to justify a 150 TB/s SRAM tier. Reject the cache hypothesis if capacity or conflict energy erases the gain.
3. **Use precision to solve capacity before packaging.** Compare native FP8 and expert-selective NVFP4 with quality and retraining cost. Capacity reduction lowers both device count and fabric traffic; peak HBM bandwidth alone does neither.
4. **Eliminate host-visible launch paths.** Model and later measure persistent fused execution. The sub-microsecond profile cannot be tested with conventional per-action host launch.
5. **Benchmark the future incumbent.** Re-run economics against Rubin/MI450-class capacity, bandwidth, and power rather than treating the H200-like profile as the commercial baseline.

Because customers are billed separately for input and output tokens, the business model needs two measured cost curves. Prefill and decode exercise different compute, memory, batching, and latency regimes. The company is customizing per model rather than per workload, so it should test a fixed public grid of prompt length, output length, concurrency, and SLO instead of selecting a favorable agent trace.

The required business metric is:

> Fully loaded cost per delivered token = annualized hardware and NRE + power and cooling + host/network/storage + operations, divided by billable quality- and SLO-compliant tokens at measured utilization.

The current fixture supplies none of the dollar, energy, utilization, quality, or full-model terms in that equation. Its defensible contribution is to prioritize the next experiments: eliminate work and coordination on commodity hardware, then ask whether custom silicon adds enough residual value to repay its schedule and capital risk.

## Source register

- NVIDIA: [H200](https://www.nvidia.com/en-us/data-center/h200/), [HGX B300](https://www.nvidia.com/en-us/data-center/hgx/), [DGX B300](https://docs.nvidia.com/dgx/dgxb300-user-guide/introduction-to-dgxb300.html), [B300 power](https://docs.nvidia.com/datacenter/dps/versions/latest/sdk/user/topology/index.html), [GB300 rack power](https://docs.nvidia.com/enterprise-reference-architectures/nvl72-ai-factory/latest/components.html), [Rubin platform](https://www.nvidia.com/en-us/data-center/vera-rubin-nvl72/), [Rubin production announcement](https://nvidianews.nvidia.com/news/vera-rubin-full-production-agentic-ai-factory), and [CUDA graph launch measurements](https://developer.nvidia.com/blog/constant-time-launch-for-straight-line-cuda-graphs-and-other-performance-enhancements/).
- AMD: [MI355X](https://www.amd.com/en/products/accelerators/instinct/mi350/mi355x.html), [CDNA 4 white paper](https://www.amd.com/content/dam/amd/en/documents/instinct-tech-docs/white-papers/amd-cdna-4-architecture-whitepaper.pdf), [Helios/MI450 architecture announcement](https://www.amd.com/en/blogs/2025/amd-helios-ai-rack-built-on-metas-2025-ocp-design.html), and [MI450 timing announcement](https://www.amd.com/en/newsroom/press-releases/2026-5-20-amd-announces-more-than-10-billion-in-taiwan-ecos.html).
- Memory: [Micron HBM3E](https://www.micron.com/products/memory/hbm/hbm3e), [Micron HBM4](https://www.micron.com/products/memory/hbm/hbm4), [Samsung HBM4](https://news.samsung.com/global/samsung-ships-industry-first-commercial-hbm4-with-ultimate-performance-for-ai-computing), [Samsung HBM4E](https://semiconductor.samsung.com/news-events/news/samsung-electronics-begins-shipment-of-industry-first-hbm4e-samples/), and [SK hynix HBM4E](https://news.skhynix.com/12-layer-hbm4e-sample/).
- Packaging and fabric: [TSMC 2025 packaging roadmap](https://pr.tsmc.com/english/news/3228), [TSMC 2026 packaging roadmap](https://pr.tsmc.com/english/news/3302), and [UALink 200G 1.0 specification](https://ualinkconsortium.org/wp-content/uploads/2025/04/UALink200_Specification_v1.0_Evaluation_Copy.pdf).
