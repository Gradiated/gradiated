# ADR-0005: Cell-based multi-provider GPU inference

- status: accepted for implementation planning; every provider/release remains qualification-gated
- GitHub issue: https://github.com/joshsny/gradiated/issues/7
- owner: product and infrastructure workstreams
- date: 2026-07-13

## Decision

Host the public gateway, regional inference edge, fleet controller, ModelOps, authoritative data, and observability in AWS. Run normal owned Grad GPU execution in disposable cells across curated external GPU providers. AWS GPU capacity is not a default or fallback merely because the control plane is there; it must pass the same release economics gate.

A cell is one capacity-provider/region/security/orchestration boundary. As refined by [ADR-0006](0006-kubernetes-provider-abstraction.md), slow-path Grad CRDs/controllers in AWS EKS project PostgreSQL capacity intent and acquire capacity through isolated provider-native reconcilers, then publish qualified ready targets through the ModelOps/Redis route-release path. The gateway selects a signed cell target from Redis and calls the AWS inference edge. The edge forwards to a cell-local router or registered native allocation. No capacity-provider API, PostgreSQL query, Kubernetes discovery, or fleet scheduling occurs on the live gateway/edge path.

Use managed or cell-local Kubernetes where the provider offers a credible Kubernetes/VM substrate. Use native container/VM lifecycle APIs for marketplace providers. Do not create a stretched global Kubernetes cluster or require Cluster API/Karmada support from every provider.

Every generative Grad release has active-sequence KV cache and cross-request prefix reuse enabled, including Private/No Retention. Cache is salted into an opaque workspace/channel/release/retention-class trust domain and remains confidential ephemeral serving state in GPU/RAM or qualified encrypted local NVMe. It is not written to Redis, PostgreSQL, S3, ClickHouse, backups, traces, or logs. No-retention means no durable customer payload trace, not no transient execution/cache state.

## Context

Owned inference margin depends on buying GPU capacity below hyperscaler prices and exploiting heterogeneous spot/preemptible supply. The product must also preserve exact Grad effort/speed releases, low-friction gateway adoption, prepaid billing correctness, and a smooth customer surface. External provider mechanics therefore need to be abstracted without becoming another customer routing language or a request-path control dependency.

Current primary docs show heterogeneous control surfaces: interruptible container Pods, bid-priced marketplace instances, raw VM APIs, and managed Kubernetes GPU NodePools. Cluster API can manage providers that implement its lifecycle contracts, while Karmada adds a multi-cluster control plane and beta failover; neither removes the need for GPU offer, bootstrap, cache, economics, and interruption logic. Current vLLM supports salted prefix cache isolation and cache-aware routing, making always-on cache compatible with separated trust domains.

## Alternatives considered

1. **Chosen: AWS inference edge + external cells + capacity-provider reconcilers.** Keeps a stable serving contract, isolates provider failures, supports native/Kubernetes substrates, and leaves slow capacity control off the hot path. ADR-0006 adds the management-cluster CRD actuation surface.
2. **One stretched Kubernetes cluster.** Rejected because provider/WAN/node heterogeneity enlarges control and network blast radius, and several target suppliers expose containers/VMs rather than a supported node substrate.
3. **Karmada as the seed fleet manager.** Deferred. It may distribute resources among mature Kubernetes cells later, but it adds a control plane and does not solve provider acquisition, spend, cache-aware live routing, or signed bootstrap.
4. **Cluster API provider for every GPU supplier.** Rejected as seed scope. Existing providers may be reused, but building and operating missing CAPI providers delays revenue without replacing the product-specific fleet contract.
5. **Direct capacity-provider API integration in the gateway.** Rejected because it leaks credentials/lifecycle into the request path, couples correctness to provider APIs, and makes multi-provider pooling a gateway rewrite.
6. **Disable KV/prefix cache for no-retention.** Rejected by product requirement and performance economics. Privacy is enforced through no durable traces, ephemeral storage, trust-domain salting, TTL/eviction, no logs/backups, and provider qualification.

## Consequences

- positive: capacity and provider interruptions are isolated; Kubernetes is used selectively; gateway/public APIs remain simple; existing cells survive fleet-controller/PG outages; exact-release and cache affinity are explicit; spot cost is evaluated per successful token.
- positive: no-retention customers keep normal generation and prefix-cache performance while durable payload capture remains suppressed.
- negative: Grad must build an inference edge, cell agent/router, fleet operator, capacity-provider reconcilers, signed bootstrap, and cross-provider operations rather than rely on one cloud autoscaler.
- negative: an extra AWS edge-to-cell hop and external network can affect TTFT/stream jitter; this must pass each speed gate.
- negative: cache is lost on spot interruption, and post-output interruption cannot be transparently replayed.
- migration: begin with fakes/CRD PBT, one pinned vLLM single-node release, one native capacity-provider reconciler, and one managed-Kubernetes comparison. Publish `flex`/`standard` cells only after measured gates. Add provider breadth, multi-node topologies, `fast`, and `turbo` incrementally.
- rollback: fence a provider/cell/target epoch in Redis, stop new acquisition, drain/terminate leases, and retain direct-provider gateway service. No customer model is silently moved elsewhere.

## Evidence

- [Dated multi-provider GPU fleet brief](../../product/docs/MULTI_PROVIDER_GPU_EVIDENCE_2026-07-13.md) — current vendor-reported facts, analytical choice, uncertainties, and falsification.
- [Owned Grad inference architecture](../../product/docs/OWNED_INFERENCE_ARCHITECTURE.md) — product/runtime contracts.
- [Multi-provider GPU fleet](../../infra/docs/MULTI_PROVIDER_GPU_FLEET.md) — infrastructure implementation and qualification plan.

No provider capacity, economics, DPA/security behavior, edge latency, or cache teardown claim has been measured in this planning task.

## Reversal triggers

Revisit the abstraction if two provider classes cannot implement the lease/cell contract; the inference edge violates speed SLOs; secure ephemeral cache cannot satisfy the data contract; operational cost exceeds the savings; or effective successful-token cost fails margin. A mature multi-cluster system may replace parts of fleet deployment only if it preserves the same hot-path, exact-release, cache, financial, and failure boundaries.
