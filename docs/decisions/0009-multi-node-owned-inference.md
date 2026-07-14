# ADR-0009: Multi-node is a first-class owned-inference topology

- Status: accepted
- Date: 2026-07-14
- Extends: ADR-0005 and ADR-0006

## Decision

Support single- and multi-node production inference cells before public owned Grad inference. A cell remains one exact-release routing, failure and cache unit; it never spans provider, region or fabric domain. The gateway and inference router see one cell and an unchanged serving protocol, never provider resources or ranks.

The signed runtime manifest freezes node/GPU counts, parallel dimensions, coordinator/collective backend, fabric and placement requirements. PostgreSQL adds `allocation_members` so drivers can prove every underlying resource, one-use join and cleanup. A required member loss fences the whole cell in the seed; elastic repair and coordinator failover are deferred.

Provider-managed Kubernetes uses ordinary cell-scoped networking/workload objects after exact capacity acquisition. Native providers use VM/container groups directly. Ray or another distributed runtime may exist inside a qualified runtime image but is not Grad fleet authority. KEDA does not acquire GPUs; the SQL planner scales complete cells.

## Why

Many useful releases fit a single multi-GPU node, so forcing all inference to be multi-node would waste cost and reliability. Frontier/open-weight models and some throughput/parallelism strategies nevertheless require multiple nodes. Deferring the capability until a chosen model fails to fit would force a late redesign of allocation identity, cleanup, runtime manifests and qualification.

Keeping topology behind the cell boundary adds the required capability without complicating customer products, billing or gateway routing.

## Consequences

- positive: the same product/serving contract supports small and frontier-scale releases;
- positive: exact member ownership and cleanup are durable and property-testable;
- positive: provider APIs remain honest rather than being forced behind fake Kubernetes Nodes;
- negative: provider qualification must cover fabric, collectives, partial allocation and member loss;
- negative: the first public owned release needs a real bounded two-node qualification in addition to single-node evidence;
- limit: no cross-provider topology, elastic ranks, live coordinator promotion or durable cross-cell KV cache at seed;
- limit: qualification does not transfer across topology/provider/hardware/runtime dimensions.

## Detailed contract

[Multi-node owned inference](../../product/docs/MULTI_NODE_INFERENCE.md)
