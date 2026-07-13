# Multi-provider GPU fleet evidence brief

> Refinement: this brief established independent cells and rejected a global cluster. [ADR-0006](../../docs/decisions/0006-kubernetes-provider-abstraction.md) subsequently adopts Grad CRDs/controllers in the AWS management cluster as the common actuation/status interface. Native allocations still use their native APIs and do not become fake Nodes/Pods; the evidence conclusions below remain valid.

- date: 2026-07-13
- decision: how Grad should pool heterogeneous external GPU capacity for owned inference while AWS remains the control, data, gateway, and serving-edge home
- issue: https://github.com/joshsny/gradiated/issues/7
- evidence classes: vendor-reported unless explicitly marked analytical, inferred, or unmeasured
- scope: orchestration shape, representative provider control surfaces, spot/preemptible behavior, and KV-cache/runtime capabilities; not a provider purchase recommendation

## Decision and falsification contract

Choose independent provider/region **inference cells** behind an AWS-hosted inference edge. A slow-path fleet controller acquires capacity through curated provider adapters. Kubernetes is a cell implementation when the provider offers a credible managed cluster or raw-VM substrate; container/instance marketplaces use their native APIs. Do not build one stretched Kubernetes cluster, require Cluster API support from every provider, or put the fleet controller on the request path.

This decision is falsified if implementation spikes show any of the following:

1. two materially different provider classes cannot implement the same acquire/observe/drain/release lease contract without provider-specific behavior leaking into the gateway;
2. a stable AWS inference edge plus cell-local router adds more latency or failure than the approved Grad speed SLO permits;
3. exact-release and tenant-isolated cache-affinity routing cannot remain correct while cells disappear without notice;
4. effective cost per successful token, including idle warm capacity, failed starts, interruptions, transfer, and egress, does not beat the approved buy-versus-sell margin;
5. provider data-processing, network, isolation, or deletion terms cannot satisfy the selected customer data mode.

No source below proves production economics, security, capacity availability, or SLOs. Those remain measured qualification gates.

## What the current primary sources establish

### Multi-cluster control systems are useful but not the provider abstraction

- The Kubernetes [Cluster API](https://cluster-api.sigs.k8s.io/) defines declarative lifecycle management for multiple clusters through provider-specific infrastructure implementations. Its current provider model is explicitly extensible, but the infrastructure provider is responsible for networking, machines, load balancers, and lifecycle behavior.
- The current [Cluster API provider list](https://cluster-api.sigs.k8s.io/reference/providers) includes large clouds and several infrastructure platforms, but not the representative GPU marketplaces reviewed below. **Analytical conclusion:** adopting CAPI universally would require us to own and qualify missing infrastructure providers; use an existing provider where mature, but do not make CAPI the seed contract.
- [Karmada architecture](https://karmada.io/docs/v1.17/core-concepts/architecture/) adds its own API server, etcd, controller manager, scheduler, and execution controllers to propagate Kubernetes resources to member clusters. [Cluster failover](https://karmada.io/docs/v1.17/userguide/failover/cluster-failover) can evict and reschedule workloads, but the v1.17 failover feature is beta and disabled by default. **Analytical conclusion:** Karmada could later distribute stable deployments across several mature Kubernetes cells; it does not replace GPU offer discovery, bid/price policy, signed bootstrap, model warmup, cache-aware request routing, or provider-specific interruption handling.

### The GPU supply control surfaces are heterogeneous

| Provider surface | Current vendor-reported capability | Architectural implication | Status |
| --- | --- | --- | --- |
| Runpod Pods | The [Pod create API](https://docs.runpod.io/api-reference/pods/POST/pods) accepts container image/GPU configuration and reports cost and lifecycle state. Interruptible Pods may be stopped at any time; container disk is wiped on restart. | Native container allocation adapter; assume zero notice and disposable local state. Do not require the allocation to become a Kubernetes node. | candidate, unqualified |
| Vast.ai | The [instance API](https://docs.vast.ai/api-reference/instances/create-instance) accepts marketplace offers and container/VM configuration. Its [API workflow](https://docs.vast.ai/api-reference/creating-instances-with-api) supports bid-priced interruptible offers. | Offer-search plus bid/lease adapter with stronger host-quality and network qualification. Treat the marketplace host as a separate failure/security domain. | candidate, unqualified |
| Lambda Cloud | The [Cloud API](https://docs.lambda.ai/public-cloud/cloud-api/) launches, lists, restarts, and terminates instances, exposes capacity/quota errors, and includes a `preempted` status in the instance schema. Launch calls are rate-limited. [Instance management](https://docs.lambda.ai/public-cloud/on-demand/creating-managing-instances/) supports cloud-init and warns that billing continues until API termination. | Raw-VM bootstrap adapter; rate-aware reconciliation and explicit orphan cleanup are mandatory. Current reviewed docs establish on-demand lifecycle, not a seed spot discount. | candidate fallback, unqualified |
| CoreWeave CKS | [CKS](https://docs.coreweave.com/products/cks/clusters/introduction) is managed bare-metal Kubernetes. [NodePool resources](https://docs.coreweave.com/products/cks/nodes/create) expose GPU instance type, target/min/max nodes, labels/taints, and autoscaling. | Kubernetes-native cell; use provider NodePools rather than wrapping nodes in our own global cluster. | candidate, unqualified |
| Nebius Managed Kubernetes | [GPU node groups](https://docs.nebius.com/kubernetes/node-groups/manage) support managed Kubernetes, autoscaling, and preemptible nodes. [Preemptible VM docs](https://docs.nebius.com/compute/virtual-machines/preemptible) report a 60-second `SIGTERM` before forced shutdown, while warning that capacity is not guaranteed. | Kubernetes-native cell with a useful notice optimization, but correctness must still assume abrupt loss. | candidate, unqualified |

**Derived finding:** a common provider interface is feasible at the level of offers, allocations, observations, and termination. A common Kubernetes node interface is not demonstrated across the reviewed providers.

### Current runtimes support the cache and placement primitives we need

- vLLM [Automatic Prefix Caching](https://docs.vllm.ai/en/latest/features/automatic_prefix_caching/) reuses KV blocks across requests with shared prefixes. Its current [prefix-caching design](https://docs.vllm.ai/en/v0.21.0/design/prefix_caching/) supports a per-request `cache_salt` so reuse is confined to requests in the same trust group and timing-based cross-group inference is reduced.
- The vLLM [Production Stack](https://docs.vllm.ai/projects/production-stack/en/latest/) is Kubernetes-native and includes request routing, KV offload, prefix/KV-aware routing, disaggregated prefill, and KEDA examples. Its [prefix-aware routing](https://docs.vllm.ai/projects/production-stack/en/latest/use_cases/prefix-aware-routing.html) deliberately sends matching prefixes to the same instance.
- vLLM [parallelism and scaling](https://docs.vllm.ai/en/stable/serving/parallelism_scaling/) supports single-node multiprocessing and multi-node tensor/pipeline parallel execution, with Ray available for multi-node deployments. It recommends identical execution environments across nodes and container images for consistency.
- SGLang [PD disaggregation](https://docs.sglang.ai/backend/pd_disaggregation.html) illustrates that prefill/decode separation and KV transfer introduce their own heartbeat, transfer, and cleanup failure modes. **Analytical conclusion:** keep runtime and topology in an immutable release manifest; do not promise disaggregated serving before scope-matched benchmark and fault evidence.

**Derived finding:** always-on execution KV cache and cross-request prefix reuse are technically compatible with tenant isolation. Cache loss on interruption changes latency, not model correctness. This does not prove that GPU/NVMe cache material is non-sensitive; the architecture must treat it as ephemeral confidential data.

## Alternatives

| Alternative | Decision | Reason |
| --- | --- | --- |
| One Kubernetes cluster stretched across GPU providers | reject | WAN/API/network failure couples providers; many reviewed products expose containers or VMs rather than a supported node substrate; one control-plane failure would enlarge the blast radius. |
| One Kubernetes cluster per provider/region, centrally managed by Karmada | defer | Reasonable after several mature Kubernetes cells exist, but it adds a second scheduling/control system and does not solve price, offer, bootstrap, cache, or request routing. |
| Cluster API for every provider | reject as universal seed contract | CAPI is a sound lifecycle contract, but reviewed GPU marketplaces lack listed infrastructure providers; writing providers is not revenue-critical seed work. |
| Direct provider APIs only, no cell abstraction | reject | Fast for one vendor but leaks provider lifecycle into serving, prevents common release/health/security semantics, and makes later capacity pooling a rewrite. |
| Cell abstraction with native provider adapters and optional cell-local Kubernetes | choose | Matches the demonstrated provider surfaces, keeps provider mechanics off the hot path, and permits Kubernetes where it reduces rather than creates operations work. |

## Inferences and uncertainties

- **Inferred:** an AWS inference edge is the cleanest stable serving endpoint for allocations with dynamic addresses or outbound-only connectivity. Its latency, throughput, connection model, and cost are unmeasured.
- **Inferred:** provider-native interrupt notices are optimization signals only. Runpod explicitly allows interruption at any time, Vast bid instances can be displaced, and Nebius provides a notice; the portable contract must assume no notice.
- **Inferred:** vLLM is the best first runtime candidate because the reviewed current docs expose tenant cache salting and cache-aware Kubernetes routing. SGLang and specialized runtimes remain release-qualified alternatives, not transparent runtime swaps.
- **Unknown:** current capacity, actual prices, quotas, geographic availability, private networking, DPA terms, support quality, host isolation, model-download time, and interruption frequency for every provider.
- **Unknown:** whether cross-request KV offload to local NVMe is worthwhile after encryption and deletion requirements. Seed qualification should start with GPU/RAM cache and add local encrypted spill only after measurement.
- **Unknown:** whether any provider's managed Kubernetes control-plane cost or minimum commitment defeats spot savings at seed scale.

## Required implementation spikes before provider admission

For each provider candidate, record measured evidence for API idempotency, quota/rate behavior, failed allocation cleanup, startup-to-ready distribution, artifact transfer, GPU/topology verification, network path/streaming, spot interruption and notice, orphan billing, secure bootstrap, log/content defaults, deletion, and effective successful-token cost. Run one container-marketplace adapter and one managed-Kubernetes adapter before freezing the second provider interface version.

The fleet architecture may proceed now. No provider should be advertised, placed in a production route release, or receive retained customer traffic from this desk research alone.
