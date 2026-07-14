# Multi-node owned inference

## Decision

Multi-node is a first-class owned-inference capability before public Grad inference, while single-node remains a valid and preferred topology when a release fits and meets its SLO. Multi-node is not required for every meaningful model: a multi-GPU node can serve many useful models. It is required for models or throughput/topology strategies that cannot fit or perform adequately within one node, and Grad's frontier/open-weight ambition makes that capability non-optional.

A serving cell is the scheduling, failure, cache and routing unit regardless of whether it contains one node or many. The gateway and inference router never see ranks or provider instances.

## Invariants

- One cell belongs to one provider, region, fabric/security domain, exact release and exact topology manifest.
- A cell never spans providers or regions.
- Every member uses the same immutable runtime image/environment and qualified accelerator/driver class.
- The cell is routable only when every required rank is joined, attested, healthy and running the exact bundle.
- Loss of a required member drains/fences the whole cell in the seed; elastic rank repair is deferred.
- Scaling adds/removes complete cells, not arbitrary workers from a live topology.
- Partial allocation, uncertain cleanup or topology mismatch cannot become ready.

## Runtime topology contract

`RuntimeManifest` contains one required topology block; single-node is `node_count: 1`:

```text
topology {
  schema_version
  node_count
  accelerators_per_node
  tensor_parallel_size
  pipeline_parallel_size
  data_parallel_size
  expert_parallel_size
  coordinator_kind
  collective_backend
  fabric { kind, rdma_required, minimum_bandwidth_gbps? }
  placement { homogeneous_accelerator, same_region, same_fabric_domain }
  startup_timeout_seconds
}
```

The product of declared parallel dimensions must match the runtime's qualified world-size rules. The manifest also freezes cache-layout version, launch command, rank environment mapping, health protocol and artifact placement. Runtime-specific configuration such as Ray for a vLLM multi-node candidate stays inside the signed image/manifest; Ray is not Grad's fleet authority or a gateway dependency.

Qualification scope includes provider, accelerator, node count, accelerators per node, interconnect/fabric, driver/runtime image, parallelism, model/bundle and cache layout. Evidence does not transfer across a changed dimension.

## Persistent fleet model

Keep `capacity_sources`, `capacity_targets`, `allocations` and `cells`, and add the necessary resource-membership table:

| Model | Required fields |
| --- | --- |
| `allocation_members` | `allocation_id`, `ordinal`, `role`, `provider_resource_id?`, `observed_state`, `bootstrap_token_digest?`, `bootstrap_expires_at?`, `joined_at?`, `last_observed_at?`, `cleanup_state` |

`role` is `coordinator|worker`; ordinal is stable rank-placement input. One-node allocations have one coordinator member. The existing optional `allocations.provider_allocation_id` is a provider group/node-pool ID when one exists; member rows prove every underlying VM/node and its cleanup. Allocation-level desired/observed/lease/cleanup remains group authority.

Do not persist pod names, IP addresses, router connection IDs, GPU utilization or runtime ranks in PostgreSQL. Those are cell-local/ephemeral observations. Do not add a generic topology table: the signed runtime manifest is immutable topology authority, and the allocation references the release/bundle that contains it.

## Capacity driver contract

```rust
trait CapacityDriver {
    async fn quote(&self, request: &AcquireTopology) -> Result<Quote, DriverError>;
    async fn acquire(
        &self,
        allocation: &Allocation,
        topology: &TopologyManifest,
        quote: &Quote,
    ) -> Result<ProviderTopology, DriverError>;
    async fn observe(&self, topology: &ProviderTopologyRef)
        -> Result<ObservedTopology, DriverError>;
    async fn release(&self, topology: &ProviderTopologyRef)
        -> Result<ReleaseEvidence, DriverError>;
    async fn list_owned(&self, environment: Environment)
        -> Result<Vec<OwnedResource>, DriverError>;
}
```

`acquire` returns optional provider group ID plus the exact member resource IDs. Drivers tag every member with allocation/release/environment/ordinal/expiry. A timeout after mutation always runs observe/list-by-tag before retry. If only some members exist, the driver either completes the exact topology within the bounded deadline or releases all members. It never substitutes hardware, fabric, count or provider.

Group cleanup is `confirmed` only after every member is individually absent or provider-group deletion is authoritative and list-owned finds no resource. Any unknown member freezes new acquisition for that capacity source.

## Cell bootstrap and identity

1. The driver provisions all members with the same digest-pinned bootstrap image and a signed allocation/topology descriptor.
2. Each member receives a unique one-use join token whose digest/expiry is stored in `allocation_members`.
3. The coordinator consumes the allocation bootstrap token, generates its private key and obtains the short-lived AWS Private CA cell identity.
4. Workers consume member tokens to join only that coordinator/allocation and receive cell-local short-lived identity.
5. The coordinator verifies exact image, bundle, rank set, hardware/fabric and collective health before launching the runtime.
6. Only the coordinator establishes outbound mTLS router connections. Workers have no route to AWS databases, Valkey, Stripe, customer keys or provider lifecycle credentials.

The coordinator may issue cell-local worker identities because compromise of one member already compromises that disposable cell; it cannot mint router identity or capacity. Token replay, cross-allocation join and rank duplication fail closed.

## Provider substrates

### Native VM/container providers

The driver acquires a private same-fabric group or exact set of instances, installs the signed descriptor through provider bootstrap and observes every member. Coordinator discovery uses provider-private DNS/static membership from the descriptor. No Kubernetes is installed merely to normalize the provider.

### Provider-managed Kubernetes

The driver acquires or selects a private cluster/node pool with the exact node count/class first, then applies a cell-scoped Helm release containing an ordinary headless Service and pinned StatefulSet/Pods. Readiness requires all expected members on owned nodes. The remote cluster has no product CRDs and no application authority.

Kueue/JobSet remains appropriate for finite research/qualification jobs. Production serving is a long-lived cell supervised by the cell agent; it does not need to turn the SQL fleet into a batch scheduler. If a selected managed provider requires RayJob or another runtime operator, it is bundle/provider implementation detail and must pass the same cell contract.

## Runtime launch and serving

The cell agent materializes artifacts once per member or through provider-local read-only cache, launches coordinator/workers with deterministic ranks, and waits for collective/runtime conformance. The local runtime endpoint is exposed only by the coordinator/cell router.

For vLLM baseline candidates, single-node can use multiprocessing; a qualified multi-node image may use Ray and tensor/pipeline/data/expert parallel configuration. Custom factory-produced runtimes may replace this without changing the gateway/router contract.

The cell router admits based on whole-topology active sequences, KV capacity, queue deadline and drain state. Prefix KV cache is sharded according to the exact runtime topology and salted by opaque tenant/release/retention scope. Member loss invalidates the cell cache; no durable or cross-provider cache recovery occurs.

## Routing and failure

The inference router registers one cell connection with exact release, region, topology digest, capacity class and health. It dispatches a request to the cell, not a rank. Gateway-to-cell Protobuf remains unchanged.

- Member/preemption notice: immediately remove cell from new routing, attempt bounded stream drain, then release/recreate the whole topology.
- Silent member loss/collective failure: fail health, close affected streams under the public pre/post-output rules and fence allocation.
- Coordinator loss: router drops the cell; no seed leader promotion because hidden partial state/cache makes it unsafe.
- Router/fleet/PostgreSQL outage: already connected healthy cells continue; lifecycle mutation stops.
- Spot scarcity: planner tries another already-qualified capacity source for the same exact topology/release, never mixes providers in one cell.

## Scaling

`capacity_targets.minimum_cells/maximum_cells` counts complete topology cells. The SQL fleet planner considers ready cells, queued/rejected requests, startup time, interruption rate, cost and budget. It requests/releases full allocations through drivers.

KEDA scales AWS gateway/router/control workers from bounded service metrics; it does not acquire external GPUs. Provider autoscalers may fulfill a driver-created exact node pool, but the allocation is not ready until all members are observed and the cell passes readiness.

## Research-to-production interaction

The research factory can vary parallelism, collective backend, scheduler, kernel, cache layout, runtime and hardware mapping. Each candidate emits an exact signed topology/runtime manifest. Qualification must run the same image/bundle through the production cell agent on the target topology and test quality parity, startup, collectives, streaming, cache isolation, load, member loss, spot cleanup and rollback.

Promotion moves the same bundle digest to a model release/capacity target. Production never reconstructs command-line flags from research metadata.

## Verification

Ordinary CI:

- Rust proptest model for partial acquire, duplicate/timeout, member reorder, join replay, rank collision, loss, drain and cleanup;
- two-node CPU/tiny-runtime process harness proving coordinator/worker and router opacity;
- fake native and managed-Kubernetes providers with per-member leaks and uncertain group deletion;
- Kind test for headless discovery, all-member readiness and whole-cell fencing;
- manifest arithmetic/canonical digest and cross-language fixtures.

Protected GPU qualification:

- smallest two-node topology that exercises real inter-node collectives;
- exact runtime/bundle startup and deterministic known-answer request;
- streaming/usage, concurrent load, prefix-cache isolation and warm-hit evidence;
- kill one worker and coordinator separately; prove cell removal and one billing settlement;
- preemption/partial allocation/cleanup, list-owned zero-orphan proof and cost evidence;
- soak and rollback to prior exact release.

The first public owned Grad release requires one qualified single-node topology and one qualified multi-node topology through the same contracts. It may route only to the topology qualified for that release; multi-node capability does not force every request onto multiple nodes.

## Build packages

1. `MN-00`: topology manifest, arithmetic validation, fixtures and two-node CPU runtime.
2. `MN-01`: allocation-member migration/store and topology-aware fake driver/PBT.
3. `MN-02`: coordinator/worker one-use join, cell-local identity and all-rank readiness.
4. `MN-03`: native-provider grouped acquisition/release and zero-orphan sweeper.
5. `MN-04`: managed-Kubernetes headless/StatefulSet cell path if required by the chosen provider.
6. `MN-05`: vLLM/Ray baseline image and protected two-node qualification.
7. `MN-06`: integrate exact topology qualification with bundle promotion and production capacity targets.

## Primary references

- [vLLM distributed inference guidance](https://docs.vllm.ai/en/v0.10.0/serving/distributed_serving.html)
- [vLLM multi-node serving example](https://docs.vllm.ai/en/latest/examples/ray_serving/multi-node-serving/)
- [Kueue responsibility and all-or-nothing overview](https://kueue.sigs.k8s.io/docs/overview/)
- [JobSet concepts](https://jobset.sigs.k8s.io/docs/concepts/)
