# ADR-0006: Kubernetes management API for heterogeneous GPU capacity

- Status: superseded for implementation by the 2026-07-14 simplicity review
- Date: 2026-07-13
- Supersedes: the direct-adapter actuation detail in [ADR-0005](0005-multi-provider-spot-inference.md); all serving, cache, and placement decisions in ADR-0005 remain active

## Decision

> Do not implement the management fleet CRDs below. PostgreSQL owns capacity sources/targets/allocations/cells and curated Rust drivers reconcile provider APIs directly. Kubernetes remains valid inside a provider cell and for research jobs, but is not the universal fleet API. See [the simplicity review](../SIMPLICITY_REVIEW.md) and [current fleet blueprint](../../infra/docs/MULTI_PROVIDER_GPU_FLEET.md).

Use the AWS management EKS cluster as the common **declarative fleet actuation surface** for external GPU capacity. Grad-owned CRDs in `fleet.grad.dev/v1alpha1` represent aggregate desired pools, provider allocations, and serving cells. Rust controllers built with a pinned `kube` controller runtime reconcile those resources through curated capacity-provider adapters.

This does **not** make every provider a Kubernetes compute substrate. A provider-native allocation is an external resource reconciled from a `CapacityAllocation`; it does not masquerade as a `Node`, and its runtime is not scheduled as an ordinary `Pod`. A provider with managed Kubernetes may use the same allocation resource to reconcile a NodePool and a signed cell bundle in its bounded child cluster. No Kubernetes control plane, etcd quorum, or Pod network spans providers.

PostgreSQL remains durable business, budget, release, qualification, desired-capacity, lease-history, and audit authority. Kubernetes stores rebuildable runtime intent and observed status only. Redis stores the signed, bounded hot-path route target projection only. The gateway and inference edge never query Kubernetes.

The initial resources are:

- `CapacityPool`: a PostgreSQL-derived desired-capacity projection for one immutable release/region/speed/security envelope;
- `CapacityAllocation`: one provider lifecycle unit, keyed by the durable PostgreSQL lease ID and reconciled by exactly one capacity-provider controller;
- `InferenceCell`: content-free observed registration/readiness/capacity for one provider/region/security/ingress boundary.

Argo CD owns CRD definitions, controller deployments, RBAC, policies, and static configuration. One `fleet-spec-writer` identity (planner/broker modules) is the only normal writer of `CapacityPool`, `CapacityAllocation.spec`, and `InferenceCell.spec`; provider controllers own allocation status/finalizers; the authenticated cell registry owns cell status; the target projector alone signs and publishes ready `CellTarget` records to Redis. Argo does not prune dynamic resource instances. Terraform owns AWS and persistent provider foundations, never ephemeral allocations.

Finalizers make cleanup retryable but are not the only orphan defense. Every allocation has stable provider tags/idempotency identity, an owner epoch, TTL, cost ceiling, and durable PostgreSQL lease record. A separate sweeper lists provider resources and quarantines/releases unknown or expired allocations. Break-glass finalizer removal requires cleanup evidence or an explicit orphan-risk incident record.

## Why

Kubernetes custom resources and controllers are designed for declarative automation over collections of controlled resources, with separate spec/status authorization, validation, events, and finalizers. Kubernetes also warns against using custom resources as storage for application or end-user data, which is why financial and release authority stays in PostgreSQL and request serving stays off the Kubernetes API.

This gives operators one bounded vocabulary and one reconciliation/testing model without forcing the least Kubernetes-like provider to implement Node, Pod, storage, network, and kubelet behavior it cannot honor.

## Alternatives

1. **Chosen: Grad CRDs plus provider-native reconcilers.** Common operations and lifecycle semantics with honest external-resource mappings and a small seed dependency surface.
2. **Direct fleet service with only PostgreSQL state.** Viable, but loses Kubernetes status/events/RBAC/tooling and would create a second bespoke operator framework beside EKS. Retained as rollback: controllers can consume the same Protobuf adapter contract outside Kubernetes if the API server proves operationally unsuitable.
3. **Crossplane providers/compositions.** Crossplane correctly models external managed resources, but it does not remove custom marketplace offer, bid, interruption, cell-attestation, route-publication, or cost logic. Its provider packaging, polling, composition, privileged RBAC, and upgrade surface are unnecessary at seed. Reconsider after at least three stable adapters show that Crossplane removes more code than it adds.
4. **Virtual Kubelet/fake Nodes.** Rejected. It requires providers to implement a kubelet-like Pod lifecycle and creates misleading scheduling, network, volume, preemption, and readiness semantics for allocation APIs.
5. **Cluster API as the universal provider contract.** Rejected for capacity. Cluster API's contracts center clusters, machines, machine pools, bootstrap, and control planes. It may manage a durable child cluster where a supported provider already exists; it is not the Grad serving/allocation contract.
6. **Karmada or a stretched/global cluster.** Rejected. Multi-cluster workload propagation does not acquire native marketplace allocations and adds correlated control-plane/network complexity. Each cell remains a disposable failure boundary.

## Consequences

- positive: one `kubectl`/events/conditions view, one status model, deterministic reconciliation, provider isolation, and no provider API on the request path;
- positive: existing cells and Redis releases continue serving during PostgreSQL, Kubernetes API, planner, or provider API outages;
- positive: a native provider and a managed-Kubernetes provider share the same pool/allocation/cell contract without sharing implementation details;
- negative: Grad owns CRD versioning, controller upgrades, admission policy, finalizer recovery, status cardinality, and etcd capacity;
- negative: PostgreSQL-to-CRD projection and CRD-to-PostgreSQL observation require explicit epochs and single-writer rules;
- limit: one CR exists per active/recent allocation or cell, never per request, customer, trace, token, or cache block;
- migration: first implement fake adapters and Kind PBT, then one native adapter. Add managed-Kubernetes reconciliation only after the native lifecycle and ownership model pass. Existing provider adapters move behind allocation reconcilers without changing the gateway/edge/cell Protobuf contract;
- reversal trigger: sustained Kubernetes API/etcd or controller-runtime failure makes actuation less reliable than the existing PostgreSQL state machine, or Crossplane gains qualified providers that demonstrably eliminate most Grad lifecycle code without weakening ownership/security.

## Evidence

The source-backed analysis, falsification criteria, and implementation contract are in [Kubernetes provider abstraction](../../product/docs/KUBERNETES_PROVIDER_ABSTRACTION_2026-07-13.md). The complete architecture gap review is in [Architecture audit](../../product/docs/ARCHITECTURE_AUDIT_2026-07-13.md).
