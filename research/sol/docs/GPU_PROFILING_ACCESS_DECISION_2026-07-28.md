# GPU profiling access decision — 2026-07-28

## No-contract amendment — 2026-07-28

The user does not want a negotiated contract or committed term. Price is secondary to
immediate availability. This supersedes the original access sequence wherever it
recommended a sales-led bare-metal contract.

### Revised decision

1. Keep Nebius as the primary NVIDIA experiment provider. Nebius does not currently
   offer AMD Instinct GPUs: its GPU catalog is NVIDIA B300, B200, H200, H100,
   RTX PRO 6000, and L40S. The `gpu-l40s-d` platform has an AMD EPYC host CPU and an
   NVIDIA L40S accelerator; it is not an AMD GPU product.
2. Do not make Shadeform part of the default lab path. It aggregates many providers,
   but its public surface does not establish live hourly AMD bare-metal stock clearly
   enough to justify another control plane. Prime Intellect is a credible alternative
   unified compute API across providers, but its public documentation does not
   establish AMD Instinct or physical-host inventory. Neither replaces a direct AMD
   provider for this lab.
3. Use the existing RunPod account as the default ordinary AMD experiment route. Its
   Pod API accepts `AMD Instinct MI300X OAM`; authenticated inventory measured a
   low-stock 1x secure MI300X offer at 14:28 UTC and no stock at 14:35 UTC. Query
   immediately before allocation and fall back when placement fails. RunPod is not a
   substitute for physical-host access.
4. Add DigitalOcean only if RunPod placement repeatedly fails or more predictable
   MI300X capacity is needed. AMD itself routes immediate pay-as-you-go AMD Developer
   Cloud access through DigitalOcean, and DigitalOcean currently offers 1x and 8x
   MI300X VMs at $1.99/GPU-hour with per-second billing and a five-minute minimum. It
   also lists MI325X and MI350X VM products, although those newer products are not
   currently listed as self-service on-demand plans.
5. For unrestricted AMD profiling, use Hot Aisle directly when an 8-GPU node is
   justified. It advertises no-contract, minute-billed MI300X VMs and 8x MI300X bare
   metal with root, console, BMC/iDRAC, and BIOS access. Treat those capabilities as
   vendor-reported until one bounded host probe verifies them.
6. Keep OCI as the established hyperscaler fallback for MI300X or MI355X bare metal.
   It is pay-as-you-go but costs a whole eight-GPU node and remains subject to tenancy,
   quota, region, and availability-domain capacity.
7. Do not prioritize Voltage Park now. Its public
   `GET https://cloud-api.voltagepark.com/api/v1/bare-metal/locations` response on
   2026-07-28 advertised an 8x H100 node geometry but reported zero Ethernet GPUs and
   zero InfiniBand GPUs.
8. Do not wait for MI355X. Public self-service MI355X access is still materially weaker
   than MI300X access; TensorWave and several other MI355X routes remain access-request
   or reservation led.
9. Treat every small-provider use of “bare metal” as unverified until the host passes
   virtualization, privilege, counter, clocks, topology, and cleanup probes. In
   particular, a dedicated GPU inside a VM is not host bare metal.

### Contract-free candidates

| Provider | Contract-free product | Evidence and current stock status | Use |
| --- | --- | --- | --- |
| Latitude.sh | Hourly on-demand physical servers, custom OS/IPMI, API lifecycle | Official docs establish true bare metal and no long-term commitment. Exact GPU stock requires an authenticated `/plans?filter[gpu]=true&filter[in_stock]=true` query. | High-confidence NVIDIA host-control candidate. |
| Huddle01 Cloud | Per-second H100/H200/A100/RTX 6000 deployments with root SSH | Vendor calls the product bare metal and exposes a real-time authenticated offers API. No unauthenticated stock result is available. Single-GPU geometries may still be partitioned hosts, so verify rather than trust the label. | Fast H200/H100 candidate if the profiling smoke passes. |
| GMI Cloud | Vendor-reported no-contract, on-demand H100/H200 bare metal | Vendor claims no queue, no quota approval, and bare-metal custom-model access. Public pages do not prove account-level stock or host privilege. | Candidate after an authenticated allocation and profiling smoke. |
| OCI | Pay-as-you-go 8x H100/H200/B200/B300/RTX PRO 6000 and MI300X/MI355X bare-metal shapes | Official product surface is strong; allocation remains tenancy-, quota-, region-, and availability-domain-specific. | Most established broad fallback; whole-node minimum. |
| Hot Aisle | 1x/2x/4x/8x MI300X VMs and on-demand 8x MI300X bare metal | Vendor reports no contracts, minute billing, instant provisioning, and direct BIOS access for its MI300X systems. Exact stock needs account verification. | First AMD account to add. |
| RunPod | On-demand MI300X Pod | Official catalog and a June 2026 first-party MI300X walkthrough establish active MI300X service. The controller's authenticated GraphQL stock request returned HTTP 403 on 2026-07-28, so current allocatable stock was not measured. | Existing general AMD execution route; not presumed bare metal. |
| DigitalOcean | On-demand 1x/8x MI300X GPU Droplets | Officially available in ATL1 after AMD enablement. Bare metal remains contract-led and is excluded by this amendment. | Established independent AMD VM route. |
| Crusoe | On-demand MI300X VMs | Official pricing lists MI300X under flexible no-minimum on-demand billing; access may still require account enablement. | Additional AMD capacity hedge. |

### Pool-provider decision

No single marketplace has yet been measured to provide every normal accelerator and
verified host-level NVIDIA and AMD bare metal under one credential. The smallest useful
account surface is nevertheless two pooled providers, not one account per cloud:

| Pool | What one credential buys | Bare-metal position | Decision |
| --- | --- | --- | --- |
| Shadeform | One API key, one bill, and Shade Cloud deployments through the marketplace's provider accounts. Shadeform advertises 30+ clouds; its API exposes a unified instance catalog and lifecycle. It has separate on-demand and reserved-commitment products: the public catalog and API quote `hourly_price` for on-demand instances, while the prominent reservation form is for discounted 1–12 month commitments. | Shadeform says it primarily provides VMs, but its current directory also labels Hot Aisle as both integrated and bare metal for MI300X, and Valdi as integrated bare metal. A directory feature is not proof that the bare-metal SKU is hourly-deployable: require an authenticated `/v1/instances/types` row with `available`, `deployment_type`, and `hourly_price` before treating it as on-demand, then run the profiling smoke. | Do not add now. The additional control plane is not justified by a clearly measurable missing capability. |
| Prime Intellect | One API key to query and provision GPU instances across providers, with provider, region, stock, security, and price in a common response. | Public docs establish a cross-provider compute API, not AMD Instinct inventory or physical-host control. | Best Shadeform alternative for ordinary pooled compute if a second aggregator becomes necessary; not the current AMD or bare-metal answer. |
| Huddle01 Cloud | One prepaid balance and API key for a real-time multi-region NVIDIA offer marketplace, including 1x H100 and larger H100/H200 geometries. | Huddle explicitly calls the product bare metal and provides root SSH. Its API also exposes upstream-provider failure semantics. The label still does not prove that every small geometry is a whole physical host. | Primary pooled NVIDIA profiling route, contingent on the host smoke. |
| SkyPilot or dstack alone | A common scheduler and failover layer over many clouds. | Neither creates pooled billing or removes underlying account credentials in normal BYOC use. SkyPilot can use Shadeform as one backend, which is useful after the Shadeform key exists. | Use as an optional scheduler, not as the account aggregator. |
| Vast.ai, RunPod, Clore.ai, decentralized pools | One marketplace credential and broad commodity capacity. | Usually VM/container or dedicated-device access; host provenance, counters, firmware, clocks, topology, and isolation are not reliable enough to presume bare metal. | Keep for ordinary experiments and price discovery, not authoritative host-sensitive profiling. |

This reduces the intended setup to:

1. **Nebius** for normal NVIDIA experiments.
2. **RunPod** as the first ordinary AMD route and for opportunistic NVIDIA capacity.
3. **DigitalOcean** only as the reliable self-service AMD fallback.
4. **One host-level exception only when required**: Hot Aisle for no-contract MI300X
   bare metal, OCI for a hyperscaler-grade MI300X/MI355X physical node, or Latitude
   for a one-card NVIDIA PCIe physical host.

For cheap interruptible execution, retain the lab's existing **Nebius** and **RunPod**
accounts rather than opening further providers. Nebius supports preemptible VMs on all
of its NVIDIA GPU platforms and exposes capacity advice by region; RunPod exposes interruptible
Pods and separate secure/community spot prices through its API. Shadeform and Huddle
should currently be treated as broad on-demand pools, not assumed spot markets. The
resulting default is three routine credentials—Nebius, RunPod, and DigitalOcean—with
a fourth host provider added only for a specific profiling project. More accounts
should be added only when measured unavailability is materially delaying experiments.

The lab must retain the actual upstream provider, server geometry, virtualization
result, GPU PCI identity, driver, firmware, and topology in every experiment artifact.
Pooling billing does not make results transferable across different physical systems.

### Immediate access order

1. Use the existing RunPod API to query and attempt a bounded 1x MI300X Pod.
2. Create DigitalOcean/AMD Developer Cloud access for reliable 1x MI300X VM work and
   run the ROCprofiler capability probe.
3. Continue all NVIDIA work on Nebius.
4. When a project actually requires host counters, clocks, firmware, or topology,
   provision one Hot Aisle 8x MI300X bare-metal node and run the host-profiling smoke
   before moving model weights.
5. Use OCI instead of Hot Aisle if hyperscaler controls or MI355X are required and
   account-visible capacity is available.

Once credentials exist, the lab should run read-only stock discovery across both pools
and create only one bounded profiling smoke. The smoke must establish
`systemd-detect-virt`, DMI/PCI identity, root or required capabilities, Nsight
Compute/ROCProfiler hardware counters, clocks/power controls, topology, absence of
co-tenant GPU processes, and API deletion. A failed smoke demotes the venue to ordinary
VM experiments rather than blocking research.

### One-GPU bare-metal geometry

One-GPU physical servers exist, but accelerator packaging determines which models can
be offered that way:

| Provider/product | Physical GPU count | Confidence | Limitation |
| --- | ---: | --- | --- |
| Latitude.sh `g3.h100.small` | 1x H100 80 GB | High: Latitude explicitly describes it as a bare-metal server and separates it from its single-GPU VM product. | Exact live stock requires an authenticated plans query. A single-card H100 is a PCIe geometry, not an eight-way HGX H100 SXM system. |
| Huddle01 `1H100...` offer | 1x H100 | Medium: vendor calls it bare metal and provides root SSH, but its 30-vCPU/120-GB host geometry does not independently prove that the customer owns the whole physical server. | Require the virtualization and DMI/IPMI profiling gate before treating results as bare metal. |
| Cherry Servers configurable GPU server | Up to 1 GPU on selected physical servers | High for physical-server identity; current public accelerator list emphasizes A100/A40/A10 and older PCIe cards rather than H100/H200. | Useful for older PCIe architecture work, not an exact Hopper/Blackwell target. |
| Scaleway `H100-1-80G` / `L40S-1-48G` | 1 allocated GPU | Not bare-metal evidence: these are Scaleway GPU Instances. | Scaleway's genuine Elastic Metal GPU servers currently start at 2x L40S or 2x H100. |

Packaging explains the boundary. PCIe accelerators such as H100 PCIe, A100 PCIe,
L40S, RTX PRO 6000, and older cards can be installed one per conventional server.
H100/H200 SXM, B200/B300 SXM, and AMD MI300X/MI355X OAM accelerators are normally
delivered as integrated HGX/UBB platforms. Contract-free cloud access to those exact
platforms is therefore generally sold as a complete 8-GPU node.

For the lab, a 1x Latitude H100 bare-metal host is sufficient to prove unrestricted
Nsight Compute counters, inspect Hopper kernels, develop profiling automation, and
study PCIe H100 behavior. It is not scope-matched evidence for H200 HBM3e bandwidth,
HGX/NVSwitch collectives, SXM power behavior, B200 dual-die behavior, or AMD CDNA.
Those claims require the corresponding full platform.

## Question and decision

Which providers should the lab add for low-level NVIDIA and AMD profiling, and which experiments actually require bare-metal hardware?

Decision:

1. Add a self-service DigitalOcean AMD MI300X GPU Droplet first. It is the fastest credible route to general AMD execution and costs $1.99/GPU-hour for one 192 GB GPU. Treat hardware-counter access as an immediate measured capability gate, not as guaranteed by the VM product.
2. Pursue one true bare-metal profiling relationship. The best immediate leads are:
   - GMI Cloud for on-demand NVIDIA H100/H200 with vendor-reported full root access;
   - Latitude.sh for low-cost RTX PRO 6000 Blackwell bare metal, subject to an authenticated live-stock query;
   - DigitalOcean or OCI when an 8-GPU bare-metal contract is acceptable.
3. Apply in parallel to AMD's Instinct Evaluation Program or AMD Accelerator Cloud for MI325X/MI355X access. This is the highest-value route for CDNA4 kernel work, although approval, scheduling, and privilege constraints make it unsuitable as the only AMD provider.
4. Do not wait for bare metal before continuing research. Run most correctness, kernel timing, runtime integration, throughput, and candidate-screening experiments on full-device passthrough VMs. Use bare metal selectively for counters, topology, driver/kernel control, absolute production validation, and host-sensitive mechanisms.

## Claim scope and falsification

This brief establishes vendor-reported products, current public catalog exposure, and authenticated Gcore capacity. It does not guarantee successful allocation, profiler permissions, stable clocks, or production economics.

The recommended provider is falsified for profiling if a fresh host cannot pass the lab probe for:

- full unpartitioned device identity;
- root or the required profiling capability;
- Nsight Compute or ROCprofiler hardware-counter collection;
- L2/HBM/SM or CU/LDS counter visibility;
- stable clocks and no co-tenant GPU process;
- exact provider lifecycle and cleanup.

Failure of the profiling gate does not make the provider unusable for ordinary inference experiments.

## Current provider surface

| Provider | Product and access | Current evidence | Decision |
| --- | --- | --- | --- |
| Nebius | NVIDIA B300, B200, H200, H100, RTX PRO 6000, and L40S VMs. | The current official platform catalog contains no AMD Instinct GPU. `gpu-l40s-d` is an NVIDIA L40S attached to an AMD EPYC host CPU. | Keep as the primary NVIDIA provider; do not expect ROCm/CDNA access from this account. |
| Prime Intellect | Unified availability and provisioning API across multiple upstream providers. | Official API docs expose provider, region, GPU type, stock, security, and price. No public evidence establishes AMD Instinct or bare-metal inventory. | Better general aggregator candidate than Shadeform if the lab later needs one; not an AMD access decision. |
| DigitalOcean | Virtual GPU Droplets: 1x/8x MI300X, plus MI325X, MI350X, H100, H200, B300, L40S and Ada. Bare metal: 8x MI300X, H100 or H200, contract-based. | Official availability page was verified 2026-07-21. MI300X VM is listed in ATL1 at $1.99/GPU-hour. Bare metal is listed in NYC3, AMS3 and ATL1, but requires sales. | Reliable AMD fallback if RunPod placement repeatedly fails. Request AMD enablement and run the profiling capability gate before relying on counters. |
| GMI Cloud | Bare-metal and container NVIDIA H100, H200, B200 and GB200; vendor says full root and on-demand provisioning. | Vendor labels H100/H200 available now, B200 limited, and advertises $2.00/$2.60/$4.00 per GPU-hour respectively. No authenticated account-level capacity has been measured. | Best immediate NVIDIA bare-metal lead; obtain written confirmation that `ncu` counters and host driver controls are enabled. |
| Latitude.sh | Dedicated bare metal, API/Terraform lifecycle; H100 and RTX PRO 6000. | Vendor announced deployable RTX PRO 6000 in Sydney and Tokyo at $1.63 and $1.30 per GPU-hour on 2026-02-28. Its authenticated plans API exposes live `in_stock` locations, but the lab has no token. | Strong low-cost Blackwell profiling candidate. Sign up, then query authenticated stock before funding. |
| OCI | True bare-metal H100, H200, B200, B300, RTX PRO 6000, MI300X and MI355X shapes. | Official shape catalog is current; capacity and quota are tenancy-, region- and availability-domain-specific. No OCI credential is configured in the lab. | Best breadth, but likely slower quota/onboarding and whole-node cost. Query all subscribed regions once credentials and limits exist. |
| AMD Developer Cloud | Pay-as-you-go 1x/8x MI300X VMs through DigitalOcean/Vultr. | AMD advertises immediate pay-as-you-go access and optional developer credits. | Use DigitalOcean directly for automation; AMD's program may provide credits. |
| AMD Instinct Evaluation / Accelerator Cloud | Approved access to MI325X and MI355X; Accelerator Cloud exposes production Slurm partitions and ROCm 7.2. | AMD says evaluation responses arrive within two weeks; access is approval-based. Root access is not established. | Apply for high-value CDNA4 research, but do not block the lab on approval. |
| Vultr | Bare-metal catalog includes H100, L40S, GH200, B200, MI325X and MI355X; API lifecycle exists. | Public API on 2026-07-28 exposed no locations for those plans. Only the 8x A100 SXM bare-metal plan exposed EWR/FRA locations. | Do not prioritize until an authenticated account query shows stock. |
| Gcore | Bare-metal H100, H200, L40S and A100 clusters. | Authenticated refresh at 2026-07-28T10:00Z returned zero capacity for every exposed GPU flavor and a zero one-server quota. | Not usable now. Retain as a periodic inventory source. |
| Cirrascale | Dedicated non-virtualized H200-class systems. | Vendor uses flat-rate rather than hourly service. | Poor fit for short profiling experiments unless a longer reservation becomes useful. |
| TensorWave | AMD MI355X cloud with ROCm expertise. | Vendor is accepting access requests and advertises MI355X, but no self-service capacity or price was verified. | Strong commercial AMD lead; useful if they confirm API lifecycle and counter access. |

### Public Vultr catalog check

Retrieved 2026-07-28:

```bash
curl -fsSL 'https://api.vultr.com/v2/plans-metal?per_page=500'
curl -fsSL 'https://api.vultr.com/v2/regions?per_page=500'
```

Relevant result: H100, L40S, GH200, B200, MI325X and MI355X bare-metal plans were present but had empty `locations`; the 8x A100 SXM plan listed `ewr` and `fra`. Plan exposure is not a reservation guarantee.

## When bare metal matters

### Full-device VMs are sufficient for most research

Use a VM with one whole physical GPU passed through—not MIG or a time-sliced vGPU—for:

- model and runtime correctness;
- exact-shape kernel development and relative A/B timing;
- quantization and representation experiments;
- endpoint integration;
- throughput/concurrency exploration;
- memory-capacity checks;
- most same-host matched performance comparisons.

Virtualization overhead in the GPU's own long-running kernels is usually not the dominant uncertainty. CPU scheduling, I/O, clocks and host noise can still affect short kernels and end-to-end tails, so comparisons should remain paired on the same host and report variance.

### Bare metal is required or strongly preferred for

- unrestricted Nsight Compute or ROCprofiler hardware counters;
- device-wide and NVLink/NVSwitch metrics;
- driver module parameters, custom drivers, firmware or GPU reset;
- power limits, application clocks and stable-clock experiments;
- CPU launch latency, NUMA, PCIe, pinned-memory and host scheduler studies;
- GPUDirect/RDMA, P2P and multi-GPU topology work;
- production-grade absolute throughput, tail latency and power validation;
- ruling out hypervisor or noisy-neighbor effects.

Nsight Systems tracing often works in VMs. Nsight Compute is supported in licensed NVIDIA vGPU environments but has restrictions: device-level metrics such as NVLink are unavailable, live-migrated VMs are unsupported, and performance-counter permissions must be enabled by the host or exposed through `CAP_SYS_ADMIN`/`CAP_PERFMON`. Fractional vGPU and MIG should not be used for architecture-level conclusions.

Hardware-counter profiling also perturbs execution and may replay or serialize kernels. It should be a targeted diagnostic rung, not enabled on every throughput run. The lab should profile small representative shapes, use the result to design an intervention, and then time that intervention without the profiler.

## Recommended access sequence

1. **RunPod MI300X Pod first**
   - Query `research/factory/tools/grad-profile providers --provider runpod`.
   - If 1x MI300X is stock-positive, use the existing controller and balance.
   - If placement fails or stock is absent, continue to DigitalOcean rather than
     repeatedly polling RunPod.
2. **GMI NVIDIA bare metal**
   - Ask for hourly H100 or H200, not a long reservation.
   - Require written confirmation of root, `ncu`, hardware counters, driver-module control and API create/delete.
   - Start with one node-hour capability check before moving weights.
3. **Latitude RTX PRO 6000**
   - Create an account and API key.
   - Query `GET /plans?filter[gpu]=true&filter[in_stock]=true`.
   - Use it for Blackwell FP4 and low-cost placement research if full-card stock and counters pass.
4. **AMD CDNA4 application**
   - Apply to the Instinct Evaluation Program / AMD Accelerator Cloud for MI355X, describing model-specific inference kernels, AITER/Composable Kernel work, MXFP4/MXFP6, LDS/L2/HBM analysis and reproducible open-source improvements.
5. **OCI as the broad fallback**
   - Configure API credentials and request limits for `BM.GPU.MI300X.8`, `BM.GPU.MI355X.8`, `BM.GPU.H200.8`, `BM.GPU.B200.8`, and `BM.GPU.RTXPRO.8`.
   - Query account-visible capacity across subscribed regions before making any reservation.

## Source table

Retrieved 2026-07-28 unless stated otherwise.

| Source | Revision/date | Evidence type | Used for |
| --- | --- | --- | --- |
| https://docs.nebius.com/compute/virtual-machines/types | Current | Official documentation | Nebius NVIDIA-only GPU catalog and AMD EPYC host distinction |
| https://www.amd.com/en/developer/resources/cloud-access/amd-developer-cloud.html | Current | Official program documentation | Immediate DigitalOcean/Vultr MI300X access, 1x/8x geometry, and AMD program credits |
| https://docs.primeintellect.ai/api-reference/introduction | Current | Official API documentation | Cross-provider compute API |
| https://docs.primeintellect.ai/api-reference/check-gpu-availability | Current | Official API documentation | Common provider, stock, security, region, and price response |
| https://docs.digitalocean.com/products/droplets/details/gpu-availability/ | Verified 2026-07-21 | Official documentation | VM GPU models and regions; bare-metal regions |
| https://www.digitalocean.com/pricing/gpu-droplets | Current | Official pricing | MI300X on-demand rate and geometry |
| https://docs.digitalocean.com/products/bare-metal-gpus/details/features/ | Verified 2026-07-13 | Official documentation | Bare-metal MI300X/H100/H200 hardware and custom drivers |
| https://docs.digitalocean.com/products/bare-metal-gpus/details/pricing/ | Verified 2026-07-13 | Official documentation | Contract-only bare-metal billing |
| https://www.gmicloud.ai/en/gpus | Current | Vendor-reported | GPU availability labels, prices, root and on-demand claims |
| https://www.latitude.sh/changelog/metal-gpu-now-available-in-sydney-and-tokyo | 2026-02-28 | Vendor-reported | RTX PRO 6000 bare-metal regions and rates |
| https://www.latitude.sh/docs/api-reference/get-plans | Current | Official API documentation | Authenticated stock query |
| https://www.oracle.com/cloud/compute/gpu/ | Current | Official product documentation | OCI bare-metal product surface |
| https://docs.oracle.com/en-us/iaas/Content/Compute/References/computeshapes.htm | Current | Official technical documentation | OCI MI355X and NVIDIA shape identities |
| https://www.amd.com/en/developer/resources/cloud-access.html | Current | Official program documentation | AMD access programs and approval timing |
| https://aac.amd.com/help/bare-metal/whats-new/releases/v2026.04/ | 2026-04-23 | Official service documentation | MI325X/MI355X production Slurm clusters |
| https://docs.vultr.com/products/compute/instances/bare-metal/explore-gpu-variants | Updated 2026-05-26 | Official documentation | Vultr bare-metal catalog |
| https://api.vultr.com/v2/plans-metal?per_page=500 | Live 2026-07-28 | Official public API | Region-enabled plan exposure |
| `/root/workspace/research/factory/docs/GCORE.md` | Authenticated 2026-07-28T10:00Z | Measured vendor API | Current Gcore capacity and quota |
| https://docs.nvidia.com/nsight-compute/ReleaseNotes/ | Current | Official technical documentation | vGPU profiling restrictions |
| https://developer.nvidia.com/nvidia-development-tools-solutions-ERR_NVGPUCTRPERM-permission-issue-performance-counters | Current | Official technical documentation | Linux and container counter permissions |
| https://rocm.docs.amd.com/projects/rocprofiler-sdk/en/develop/how-to/using-rocprofv3.html | Current | Official technical documentation | AMD kernel counter collection |
| https://www.latitude.sh/docs/servers/deploying-a-server | Current | Official documentation | Hourly on-demand physical server deployment |
| https://www.latitude.sh/docs/billing/on-demand-vs-reserved | Current | Official documentation | No-commitment hourly billing |
| https://huddle01.com/products/gpu | Current | Vendor-reported | Contract-free H100/H200 product and claimed bare-metal access |
| https://console.huddle01.com/docs/gpu-offers | Current | Official API documentation | Authenticated real-time offer discovery |
| https://www.gmicloud.ai/en/blog/where-to-rent-gpu-compute-to-run-ai-models-instantly | 2026-03-04 | Vendor-reported | Claimed no-contract bare-metal H100/H200 access |
| https://support.voltagepark.com/article/on-demand | Current | Official product documentation | Contract-free H100 bare-metal product |
| https://cloud-api.voltagepark.com/api/v1/bare-metal/locations | Live 2026-07-28 | Official public API | Zero currently reported public bare-metal GPU count |
| https://hotaisle.xyz/pricing/ | Current | Vendor-reported | MI300X VM and bare-metal geometries and no-contract access |
| https://www.runpod.io/blog/training-flux-mi300x | 2026-06-29 | Vendor-reported measured walkthrough | Active RunPod MI300X Pod service |
| https://www.crusoe.ai/cloud/pricing | Current | Official pricing | On-demand MI300X service and no-minimum billing |
| https://www.latitude.sh/blog/bare-metal-for-ai-workloads-supporting-llms-and-generative-ai | 2025-01-15 | Vendor-reported product documentation | Latitude `g3.h100.small` one-H100 bare-metal geometry |
| https://www.latitude.sh/changelog/introducing-gpu-accelerated-vms | 2025-02-21 | Vendor product documentation | Separate Latitude single-GPU VM product |
| https://www.cherryservers.com/dedicated-gpu-servers | Current | Official product documentation | Configurable one-GPU physical servers and current public accelerator family |
| https://www.scaleway.com/en/elastic-metal/titanium/ | Current | Official product documentation | Genuine Elastic Metal begins at 2x L40S/H100 |
| https://docs.shadeform.ai/getting-started/faq | Current | Official documentation | Shade Cloud provider accounts, consolidated billing, VM emphasis, and no additional launch fee |
| https://docs.shadeform.ai/api-reference/authentication | Current | Official API documentation | Single-key API lifecycle and unified instance catalog |
| https://shadeform.com/prices | Current | Official pricing | Separate hourly on-demand catalog and reserved-contract offer |
| https://docs.shadeform.ai/api-reference/instances/instances-types | Current | Official API documentation | Per-offer hourly price, availability, and deployment type |
| https://shadeform.com/directory/clouds/hotaisle | Current | Vendor marketplace directory | Integrated Hot Aisle MI300X bare-metal claim |
| https://shadeform.com/directory/clouds/valdi | Current | Vendor marketplace directory | Second integrated bare-metal marketplace route |
| https://console.huddle01.com/docs/gpu-overview | Current | Official API documentation | Single-key pooled NVIDIA offers, claimed bare metal, root SSH, billing threshold, and upstream-provider semantics |
| https://docs.skypilot.co/ | Current | Official documentation | BYOC credential model and Shadeform scheduler integration |
| https://docs.nebius.com/compute/virtual-machines/preemptible | Current | Official documentation | Preemptible GPU VM behavior and lifecycle |
| https://docs.nebius.com/compute/virtual-machines/capacity-advisor | Current | Official documentation | Region- and type-specific preemptible capacity discovery |
| https://docs.runpod.io/api-reference/pods/POST/pods | Current | Official API documentation | Interruptible Pod creation and spot-price fields |

## Uncertainty and next refresh

- Provider “available” pages are vendor-reported, not successful account-level allocations.
- DigitalOcean MI325X/MI350X, DigitalOcean bare metal, OCI, GMI and TensorWave may require sales approval or quota.
- VM hardware-counter exposure is provider configuration, not implied by root inside the guest.
- Authenticated stock must be checked immediately before allocation.
- Revisit provider/product coverage weekly, prices every three days, and capacity immediately before each experiment.
