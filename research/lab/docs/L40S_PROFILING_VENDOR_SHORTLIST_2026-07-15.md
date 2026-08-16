# L40S performance-counter venue shortlist

**Retrieved:** 2026-07-15  
**Decision:** Select a small true-bare-metal L40S venue for Nsight Compute cache, occupancy, and stall profiling. Do not transfer a checkpoint until a tiny CUDA kernel emits a usable `.ncu-rep`.

**Availability update — 2026-07-16:** The user observed Scaleway's L40S Elastic Metal SKU out of stock. Gcore is now the highest-priority additional account to probe: its current catalog lists an `8x L40S` bare-metal cluster at `€8.72/hour`, and its authenticated flavor endpoint can return a per-region capacity count. This is a documented offering and probe path, not evidence that stock exists for a new account.

## Question and claim boundary

Which currently documented vendors provide enough physical-host control to make NVIDIA GPU hardware-counter profiling plausible for GLM-4.7 Flash on L40S?

The vendor documents below establish hardware form factor, tenancy/control, GPU inventory, and pricing. They do **not** explicitly guarantee that Nsight Compute performance counters are enabled. Only the acceptance probe below can establish that on a provisioned host. “GPU passthrough,” “dedicated GPU,” “root inside a VM,” and “container directly on bare metal” are insufficient because the host driver or another CUPTI/DCGM client can still own or restrict the counters.

## Recommendation

1. **Scaleway Elastic Metal `EM-T220E-L40S` — first choice.** It is a no-hypervisor Elastic Metal server with `2x L40S 48 GB`, host-level control, hourly billing, and a listed price of `€4.11/hour` for the node in Paris `fr-par-2`. The quota page says this SKU requires contacting Support. It is the smallest clearly documented true-bare-metal L40S host in this review and therefore the most economical likely profiling venue.
2. **OCI `BM.GPU.L40S.4` — strongest hyperscaler fallback.** It is a true bare-metal host with `4x L40S 48 GB`, no hypervisor or Oracle-installed host agents, and full stack control. The listed rate is `$3.50/GPU-hour`, hence approximately `$14/hour` for the mandatory four-GPU shape. Capacity/quota may require coordination.
3. **Vultr Bare Metal L40S — technically strong, currently capacity-constrained.** Vultr documents true bare metal and root SSH access. Its public API currently lists `8x L40S` plan `vbm-64c-2048gb-8-l40-gpu` at `$13.368/hour` or `$11.92/hour` preemptible, but reports no available locations and disables on-demand deployment. Recheck rather than assuming availability.
4. **OVHcloud `HGR-AI-2` — persistent lab host, not burst profiling.** This is a dedicated bare-metal server with `2x` or `4x L40S`. Current official material lists availability in France and Canada from about `€2,969.99/month`; the dedicated-server page also shows a setup fee. It is attractive if the lab wants a continuously available profiling machine, but inefficient for a one-hour probe.
5. **CoreWeave L40S CKS node — conditional only.** CoreWeave runs Kubernetes directly on dedicated bare-metal nodes, documents an `8x L40S` node in `US-EAST-04A`, and advertises low-level observability. However, the customer interface is managed Kubernetes rather than documented host-root/driver control. Obtain written confirmation that a privileged workload can access Nsight Compute counters and that CoreWeave can pause any DCGM/CUPTI counter client. Do not treat “bare-metal Kubernetes” alone as sufficient.

### Additional live-capacity route: Gcore

Gcore currently documents user-managed GPU bare-metal clusters for L40S, A100, H100, and H200. Its public catalog lists `8x L40S PCIe` at `€8.72/hour` (`€1.09/GPU-hour`). After account creation, the regional flavor API supports `include_capacity=true`, returning the capacity count, disabled state, and price for each flavor. A separate quota endpoint reports the L40S bare-metal server limit, request, and usage. Images support SSH keys and identify the installed NVIDIA driver; the API distinguishes clusters managed directly by the user from Kubernetes-managed clusters.

This is the best currently documented alternative for an immediate exact-L40S availability query, but the public pages do not expose today's stock to anonymous users. The minimum advertised bare-metal geometry is eight GPUs, and none of the reviewed Gcore documents explicitly promises control of the host NVIDIA module or Nsight performance counters. Query capacity before creation, create only a user-managed cluster, and run the five-minute counter acceptance contract before checkpoint transfer.

## OCI region and capacity status

OCI's immutable **home region controls IAM definitions, not the regions in which Compute may run**. An administrator can subscribe the same tenancy to additional infrastructure regions through the Console, CLI, or API; activation normally takes several minutes. Region subscriptions cannot later be removed.

The official OCI status inventory retrieved on 2026-07-15 reports `Oracle Cloud Infrastructure Compute GPU` present and healthy in these commercial regions: Melbourne (`ap-melbourne-1`), São Paulo (`sa-saopaulo-1`), Montreal (`ca-montreal-1`), Frankfurt (`eu-frankfurt-1`), Mumbai (`ap-mumbai-1`), Batam (`ap-batam-1`), Jerusalem (`il-jerusalem-1`), Osaka (`ap-osaka-1`), Tokyo (`ap-tokyo-1`), Singapore West (`ap-singapore-2`), Seoul (`ap-seoul-1`), Dubai (`me-dubai-1`), London (`uk-london-1`), Ashburn (`us-ashburn-1`), and San Jose (`us-sanjose-1`). It also lists the separate EU Sovereign Frankfurt realm, which is not a normal commercial-region subscription.

This is **generic GPU-service presence, not exact `BM.GPU.L40S.4` inventory or live spare-host capacity**. OCI does not expose either claim publicly. After account creation, subscribe the acceptable commercial regions, call `ListShapes` per availability domain, inspect the region-scoped L40S service limit, and request one four-GPU limit where necessary. Before launching or reserving anything, call the authenticated `CreateComputeCapacityReport` operation for `BM.GPU.L40S.4` in every availability domain. Its result distinguishes `AVAILABLE`, `OUT_OF_HOST_CAPACITY`, and `HARDWARE_NOT_SUPPORTED` and reports how many instances can currently be created. Treat it as a point-in-time placement signal, not a reservation; capacity can change before launch. A paid launch remains the final allocation proof and must stay behind campaign spend authority. Do not create a reservation merely to probe availability because unused reserved capacity can be billed. Oracle explicitly warns that L40S often requires a Compute reservation and can return `Out of host capacity` despite sufficient quota.

## Cross-GPU research-lab decision

If the goal is one provider account for profiling many chip families, prefer **OCI**, not Scaleway. OCI has the broadest currently documented combination of true bare metal, complete host-stack control, NVIDIA architectural coverage, and AMD coverage. Vultr is the best second account if it can provide actual capacity. Use Scaleway as an economical Ada/Hopper profiling venue, not as the complete hardware inventory.

| Vendor | Documented true-bare-metal GPU families relevant to the lab | Host-control confidence | Practical role |
|---|---|---:|---|
| **OCI** | NVIDIA A10, A100, L40S, H100, H200, B200, GH200, GB200; AMD MI300X | High: no hypervisor/Oracle host agents, full stack control | Primary multi-architecture profiling provider; large minimum node sizes and quota/capacity are the tradeoff |
| **Vultr** | NVIDIA A100 PCIe/SXM, L40S, H100, GH200, B200; AMD MI300X and MI355X | High for a provisioned Bare Metal product: physical host plus root SSH | Secondary broad provider and useful AMD/new-chip route; verify each plan's live region availability before integrating |
| **CoreWeave** | NVIDIA A100, L40/L40S, GH200, H100/H200, RTX Pro 6000 Blackwell, B200/B300, GB200/GB300 | Conditional: physical nodes are bare metal, but customer access is managed Kubernetes | Excellent NVIDIA breadth only if support guarantees host-counter access and profiler-service control |
| **Scaleway Elastic Metal** | NVIDIA L40S and H100 | High for Elastic Metal; ordinary GPU Instances are VMs | Cheap exact L40S/H100 profiling and redundancy, but insufficient architectural breadth |
| **OVHcloud dedicated** | Current dedicated pages center on NVIDIA L4 and L40S; older V100S capacity also exists | High for dedicated servers | Persistent European NVIDIA lab host; narrow catalog and monthly/setup economics |

AMD experiments require the same host-control acceptance principle but use ROCm's `rocprofv3`/ROCProfiler and Omniperf-compatible counters rather than Nsight Compute. Do not assume a provider that passes NVIDIA profiling also passes AMD counter collection; bind and probe each SKU/driver independently.

The recommended provider topology is therefore:

1. **OCI primary** for broad, exact-chip profiling and both CUDA and ROCm families.
2. **Scaleway Elastic Metal first probe** when the immediate need is economical L40S evidence.
3. **Vultr secondary** once a support contact confirms inventory for the desired plans.
4. **CoreWeave conditional NVIDIA scale venue** only after a successful counter report or contractual host-access confirmation.

## Not recommended without a successful counter probe

- **Nebius L40S:** measured failure in this campaign. CUDA worked, but Nsight Compute metric query and profiling failed with counter-library/driver resource errors.
- **Scaleway L40S GPU Instances:** these are explicitly virtual compute instances despite dedicated GPUs. Do not confuse them with the separate `EM-T220E-L40S` Elastic Metal product.
- **AWS G6e, Latitude `vm.l40s.small`, and DataCrunch L40S VDS:** documented L40S virtual machines or virtual dedicated servers, not host-controlled bare metal.
- **CoreWeave ordinary pods, Latitude Launchpad containers, and similar container products:** physical dedication does not imply control of the host NVIDIA module or competing profiler services.
- **Ionstream and smaller bare-metal vendors:** potentially useful, but the reviewed public material did not establish host-root and driver/module control strongly enough. Ask them to execute the acceptance contract before purchase.

## Five-minute acceptance contract

Run this before installing the model, creating a large disk, or transferring checkpoint bytes:

1. Confirm physical identity and host control: `nvidia-smi -q`, `lspci -nn`, `id`, `systemd-detect-virt`, and `/proc/driver/nvidia/params`.
2. Stop or isolate other performance-counter users, especially `dcgm-exporter`, `nv-hostengine`, Nsight tools, CUPTI profilers, and MPS. NVIDIA documents that concurrent counter clients can make the profiler resource unavailable.
3. Run as host root. If needed, set `NVreg_RestrictProfilingToAdminUsers=0`, reload the NVIDIA module or reboot, and recheck the live parameter. Root inside a container or VM does not satisfy this step unless it controls the host driver.
4. Compile and run a deterministic CUDA vector kernel without a profiler.
5. Require all of the following:
   - `ncu --query-metrics` succeeds;
   - `ncu --set basic --force-overwrite -o ncu-permission-probe ./probe` exits zero;
   - `ncu --section SpeedOfLight --section MemoryWorkloadAnalysis --section Occupancy --force-overwrite -o ncu-memory-probe ./probe` exits zero;
   - `ncu-memory-probe.ncu-rep` exists and exports non-`n/a` DRAM/L2 and occupancy metrics;
   - a second run succeeds after profiler cleanup.

**Kill condition:** if host root plus one attempt after stopping competing profiler services cannot emit the report, terminate the host and reject that product/region. Do not debug model code or transfer the checkpoint.

## What this enables

Once the acceptance probe passes, use the same host to profile exact GLM ranges and kernels with NVTX plus Nsight Compute. Retain raw reports and export per-range/kernel summaries for shared-memory allocation/conflicts, L1 requests/hit rate, L2 sectors/hit rate/read-write traffic, DRAM bytes/bandwidth, registers, achieved occupancy, eligible warps, stall classes, tensor-pipe utilization, and exact tensor/kernel shapes. Treat replay timing as diagnostic, not endpoint throughput; run an unprofiled adjacent control for wall time.

## Sources

| Source | Revision/publication | Evidence type | Supports |
|---|---:|---|---|
| [NVIDIA Nsight Compute Profiling Guide](https://docs.nvidia.com/nsight-compute/ProfilingGuide/index.html) | current docs, retrieved 2026-07-15 | authoritative technical documentation | Counter permission requirements, metric querying, and concurrent profiler-resource constraints |
| [Scaleway Elastic Metal overview](https://www.scaleway.com/en/elastic-metal/) | retrieved 2026-07-15 | vendor-reported | No hypervisor and full control |
| [Scaleway Elastic Metal Titanium](https://www.scaleway.com/en/elastic-metal/titanium/) | retrieved 2026-07-15 | vendor-reported | `EM-T220E-L40S`, 2x L40S, `€4.11/hour`, Paris |
| [Scaleway organization quotas](https://www.scaleway.com/en/docs/organizations-and-projects/additional-content/organization-quotas/) | current docs, retrieved 2026-07-15 | vendor-reported | Support contact required for T220E-L40S quota |
| [OCI L40S bare-metal announcement](https://blogs.oracle.com/cloud-infrastructure/oci-ai-infra-bm-compute-nvidia-l40s-vms-h100-a100) | 2024-07-31 | vendor-reported | Four-L40S bare-metal shape and `$3.50/GPU-hour` launch rate |
| [OCI bare-metal product](https://www.oracle.com/cloud/compute/bare-metal/) | retrieved 2026-07-15 | vendor-reported | No hypervisor/agents and full stack control |
| [OCI GPU portfolio](https://www.oracle.com/cloud/compute/gpu/) | retrieved 2026-07-15 | vendor-reported | Current NVIDIA and AMD GPU families and bare-metal positioning |
| [OCI region management](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managingregions.htm) | retrieved 2026-07-15 | authoritative technical documentation | Home-region scope and subscribing a tenancy to additional compute regions |
| [OCI public status inventory](https://ocistatus.oraclecloud.com/api/v2/components_v2.json) | API updated 2026-07-09, queried 2026-07-15 | measured public API | Regions currently exposing the generic Compute GPU service and service health |
| [OCI GPU capacity troubleshooting](https://docs.oracle.com/en-us/iaas/Content/data-science/using/tshoot-gpu.htm) | updated 2025-04-30, retrieved 2026-07-15 | authoritative technical documentation | Quota is region-specific; L40S often requires reservation; quota does not prove host capacity |
| [OCI Compute Capacity Report](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/compute/compute-capacity-report/create.html) | CLI 3.89.2, retrieved 2026-07-16 | authoritative API/CLI documentation | Authenticated point-in-time host-capacity report for an exact shape and availability domain |
| [Gcore GPU pricing](https://gcore.com/pricing/ai) | retrieved 2026-07-16 | vendor-reported | Bare-metal L40S catalog geometry and hourly price |
| [Gcore bare-metal GPU flavor API](https://gcore.com/docs/api-reference/cloud/gpu-bare-metal/list-gpu-flavors) | retrieved 2026-07-16 | authoritative vendor API documentation | Per-region flavor availability, capacity count, disabled state, and pricing query |
| [Gcore bare-metal GPU quota API](https://gcore.com/docs/api-reference/cloud/gpu-bare-metal/check-bare-metal-gpu-cluster-quota) | retrieved 2026-07-16 | authoritative vendor API documentation | L40S-specific server quota limit/request/usage |
| [Gcore bare-metal GPU cluster API](https://gcore.com/docs/api-reference/cloud/gpu-bare-metal/list-bare-metal-gpu-clusters) | retrieved 2026-07-16 | authoritative vendor API documentation | User-managed versus Kubernetes-managed clusters and SSH-key binding |
| [Vultr bare-metal GPU variants](https://docs.vultr.com/products/compute/instances/bare-metal/explore-gpu-variants) | 2026-05-26 | vendor-reported | L40S bare-metal offering |
| [Vultr root SSH guidance](https://docs.vultr.com/public/doc-assets/pdfs/article/how-to-migrate-workloads-from-equinix-metal-to-vultr-bare-metal.pdf) | retrieved 2026-07-15 | vendor-reported | Root access to bare-metal host |
| [Vultr public plans API](https://api.vultr.com/v2/plans-metal?per_page=500) | queried 2026-07-15 | measured public API | Current 8x L40S plan identity/rates and no listed locations |
| [OVHcloud L40S bare-metal announcement](https://corporate.ovhcloud.com/en-sg/newsroom/news/adopt-ai/) | 2024 | vendor-reported | HGR-AI-2 dedicated bare metal, 2–4 L40S |
| [OVHcloud GPU dedicated server](https://www.ovhcloud.com/en-gb/bare-metal/gpu-dedicated-server/) | retrieved 2026-07-15 | vendor-reported | Current dedicated configuration and monthly/setup pricing |
| [CoreWeave bare-metal product](https://www.coreweave.com/products/bare-metal) | retrieved 2026-07-15 | vendor-reported | Bare-metal Kubernetes and low-level observability claim |
| [CoreWeave L40S instance](https://docs.coreweave.com/platform/instances/gpu/gd-8xl40s-i128) | modified 2026-04-17 | vendor-reported | 8x L40S node and region |
| [CoreWeave instance availability matrix](https://docs.coreweave.com/platform/instances/availability-matrix) | 2026, retrieved 2026-07-15 | vendor-reported | Current NVIDIA architecture breadth and regions |
| [Scaleway GPU Instance quickstart](https://www.scaleway.com/en/docs/gpu/quickstart/) | reviewed 2026-01-29 | vendor-reported negative evidence | Ordinary L40S GPU Instances are virtual compute instances |

## Uncertainty and falsification

No reviewed vendor page explicitly promises `ncu` hardware-counter success. Even bare metal can fail if firmware, the driver module, a security policy, or a concurrent DCGM/CUPTI client reserves the counters. This shortlist is falsified for any SKU/region that fails the acceptance contract under host root. The first successful raw `.ncu-rep` is the promotion evidence, not the phrase “bare metal.”
