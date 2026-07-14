# Simplified owned-inference implementation blueprint

## Boundary

Owned serving executes one immutable qualified release across external GPU providers. The public gateway admits money and calls owned inference; the private inference router selects an authenticated ready cell and owns connectivity/dispatch; the cell agent owns runtime launch, local scheduling and cache; fleet roles own slow-path capacity acquisition/cleanup.

PostgreSQL tables—`capacity_sources`, `capacity_targets`, `allocations`, `allocation_members`, and `cells`—are the only durable fleet state. Kubernetes hosts the AWS roles and ordinary research Jobs; there are no fleet CRDs, fake Nodes, cross-provider cluster or per-target signer. A cell may contain one or many nodes but remains one routing, failure and cache unit.

## Processes and source layout

```text
product/services/
  inference-router/src/   connection registry, dispatch, stream relay
  fleet/src/              planner, provider drivers, cell enrollment/observations, sweeper
  cell-agent/src/         bootstrap, runtime supervisor, local scheduler/cache, health/drain
  inference-contracts/    generated serving Protobuf
  inference-testkit/      fake provider/cells/runtime, fault schedules
```

`fleet` exposes role commands. Planner and each provider-driver run with separate credentials even though they share one image. The inference router has no PostgreSQL, Kubernetes or provider API credential. The cell agent has no customer key, billing state, trace key or database route.

## Serving contract

Package is `gradiated.inference.v1`. The request/event fields are exactly those in [the simplicity review](../../docs/SIMPLICITY_REVIEW.md#gateway-to-cell). The release digest is the only product/runtime identity sent downstream.

Rules:

- deadline can only tighten downstream;
- event sequence and cumulative usage are monotonic;
- a cell rejects a release-digest mismatch before output;
- retry is a gateway decision and only before usable output;
- `cache_scope` is opaque and cannot reveal a tenant;
- billing reservations, public model/effort/speed and provider allocation IDs never cross this wire.

## Inference router

```rust
trait CellRegistry {
    fn eligible(&self, release: Digest, region: &Region) -> Vec<CellConnection>;
}

trait CellTransport {
    async fn generate(&self, cell: &CellConnection, request: GenerateRequest)
        -> Result<GenerateStream, CellError>;
}

struct Dispatcher {
    registry: Arc<dyn CellRegistry>,
    transport: Arc<dyn CellTransport>,
}
```

Cells establish outbound long-lived mTLS HTTP/2 connections through the dedicated AWS cell-connect endpoint to at least two router replicas. Cells expose no inbound customer port. A later private/direct transport may use the same serving contract after provider-specific qualification. Registration proves cell/allocation identity, release and topology digest, runtime/bundle attestation, region and capacity class. Only a multi-node cell's coordinator connects to routers; workers remain cell-local. Each router keeps connection/health state in memory; reconnect rebuilds it. The gateway never reads cell topology.

The provider driver stores a one-use, short-lived bootstrap-token digest on the allocation and sends the plaintext only through provider bootstrap. The cell generates its own private key and submits a CSR/token to the public narrow enrollment endpoint. The fleet enrollment role consumes the token transactionally, verifies active allocation/release, asks AWS Private CA for a short-lived certificate, records serial/expiry and returns an allocation-tagged short-lived artifact credential restricted to the exact S3 object paths and runtime ECR repository. The cell verifies signed digests after download. Rotation requires the existing mTLS identity and active allocation. Router trust bundles overlap during CA rotation; expired/drained identities cannot register. Provider drivers and routers never hold the CA key or issue certificates.

Selection filters exact release/region/readiness/deadline, then uses deterministic cache affinity among healthy cells. The router cannot substitute a release or acquire capacity. Existing connections continue serving while fleet/PostgreSQL are unavailable.

## Cell agent and runtime

Lifecycle:

```text
bootstrap -> verify allocation token -> receive bounded identity/artifact grants
 -> fetch and verify bundle/image digest
 -> materialize artifacts -> launch OCI runtime child
 -> local conformance/readiness -> connect routers -> ready
 -> serving -> draining -> stopped
```

```rust
trait RuntimeSupervisor {
    async fn launch(&self, bundle: &BundleManifest) -> Result<RuntimeHandle, LaunchError>;
    async fn stop(&self, handle: RuntimeHandle, deadline: Instant) -> Result<(), StopError>;
}

trait LocalScheduler {
    async fn admit(&self, request: GenerateRequest) -> Result<RuntimePermit, CellError>;
}
```

The runtime is one OCI image behind a versioned Unix-domain socket Protobuf protocol. Its implementation language is irrelevant; remove `python_plugin|native_library|rust_engine` modes and C-ABI loading. A bundle specifies image digest, protocol version, command and required one-or-many-node topology. Runtime-specific coordination such as Ray stays inside the image/manifest. This supports vLLM/custom Python/native/Rust implementations without changing the cell/gateway contract.

The local scheduler considers estimated tokens, active sequences, deadline, memory, runtime readiness and drain state. It rejects overload before runtime spend. A single-runtime process is enough until measured GPU sharing requires replicas.

## Cache

Every generative release has active-sequence and prefix KV cache. Cache identity includes opaque scope, exact release, tokenizer/runtime cache-layout version, canonical prefix and position. Intelligence/no-retention and workspace/channel scopes never collide.

Cache remains GPU/RAM or qualified ephemeral local state. It is not written to Valkey, PostgreSQL, S3, traces, logs or backups. Loss affects latency only. Deletion/privacy policy changes rotate the scope epoch; draining destroys local cache. Remote/distributed cache and cross-cell transfer are deferred until a measured bottleneck.

## Fleet state and provider abstraction

The required fields and states are in [the minimal capacity model](../../docs/SIMPLICITY_REVIEW.md#owned-capacity).

```rust
#[async_trait]
trait CapacityDriver {
    async fn quote(&self, request: &AcquireTopology) -> Result<Quote, DriverError>;
    async fn acquire(&self, allocation: &Allocation, topology: &TopologyManifest, quote: &Quote) -> Result<ProviderTopology, DriverError>;
    async fn observe(&self, provider: &ProviderTopologyRef) -> Result<ObservedTopology, DriverError>;
    async fn release(&self, provider: &ProviderTopologyRef) -> Result<ReleaseResult, DriverError>;
}

trait FleetStore {
    async fn claim_allocation(&self, source: SourceId) -> Option<Allocation>;
    async fn transition(&self, id: AllocationId, epoch: u64, next: ObservedState) -> Result<(), Conflict>;
}
```

Planner compares ready cells with `capacity_targets` and inserts bounded `allocations`. Provider driver claims rows using PostgreSQL locks/leases, uses deterministic provider idempotency tags, updates observed state and proves cleanup. It never edits releases or Valkey routes directly.

`allocation_members` records every underlying provider resource, ordinal/role, one-use join-token state, observation and cleanup proof. Single-node uses one coordinator member. Partial multi-node acquisition rolls back; unknown member cleanup freezes the source. The complete topology, provider-substrate, identity, scaling and qualification design is [Multi-node owned inference](MULTI_NODE_INFERENCE.md).

Provider-specific code is compiled/curated, not dynamically loaded. Native VM/container and managed-Kubernetes APIs implement the same trait; Kubernetes is one provider API shape, not the universal abstraction. Add one driver at a time with its own account, secret, egress and rate/spend bounds.

Fleet observation records normalized lifecycle/attestation state in `cells`; router heartbeats are ephemeral serving health. The router relies on mTLS allocation identity and exact bundle/release attestation, not a second signed `CellTarget` document or Valkey cell projection. Signed bundle/image provenance remains mandatory.

## Spot, failure and cleanup

- Spot/preemption is assumed without notice. A pre-output loss may retry another exact-release cell; post-output loss terminates and settles known usage.
- Provider acquisition failure leaves other sources eligible and cannot change product identity.
- Allocation cleanup is `pending|confirmed|uncertain`. Uncertain cleanup freezes new acquisitions for that source and alerts the sweeper; it is never reported as released.
- Every provider object carries allocation/release/environment tags and an expiry. Independent sweeper lists provider objects and reconciles orphans to PostgreSQL.
- PostgreSQL/fleet loss stops new capacity decisions but does not stop ready cells. Router loss reconnects to another replica. Valkey loss closes new gateway admission.

## Bundle readiness

A cell becomes ready only if:

1. bundle canonical digest/signature and runtime image provenance verify;
2. runtime reports the exact digest/protocol/capabilities;
3. hardware/memory/driver compatibility matches the bundle;
4. a local deterministic conformance request passes;
5. cache isolation and authoritative usage probes pass;
6. every required topology member and collective passes for multi-node releases;
7. both router connectivity and deadline health are valid.

Qualification reports live in S3/PostgreSQL. The cell does not reproduce the whole qualification suite, only boot/readiness proofs.

## Deployment and observability

AWS runs at least three inference-router replicas across AZs with disruption protection. Fleet planner/registry need one active replica with standby; each provider driver is isolated. Cells run outside AWS on curated providers.

Metrics use provider/source, region, release class, allocation/cell state, capacity class and error class. No customer ID/payload. Required runbooks cover router isolation, provider freeze, allocation leak, attestation failure, cache leak suspicion, preemption storm and release drain.

## Verification and ordered packages

Use Rust unit/proptest models, fake provider APIs, fake cells/runtime, PostgreSQL/Valkey Testcontainers and network fault injection. Kind is needed only for testing a managed-Kubernetes provider driver, not for a management CRD system.

1. `OI-00`: reduced Protobuf, tiny runtime and fault testkit.
2. `OI-01`: cell bootstrap/supervisor/local scheduler/cache isolation.
3. `OI-02`: inference-router connection registry and exact-release dispatch.
4. `OI-03`: SQL fleet schema/store/planner and state-machine PBT.
5. `OI-04`: fake capacity driver, lease/idempotency/cleanup/sweeper and Private-CA enrollment fake.
6. `OI-05`: authenticated router registration and gateway-owned-route integration.
7. `OI-06`: first native provider driver under a hard budget.
8. `OI-07`: allocation members, coordinator/worker joins and two-node CPU/fake topology conformance.
9. `OI-08`: one exact single-node and one exact multi-node GPU topology qualification.
10. `OI-09`: one exact bundle `grad/medium/standard` soak/preemption/rollback.
11. `OI-10`: managed-Kubernetes driver only when a selected provider requires it.

No package may add a CRD, target signing service, runtime-language enum or cell billing field without a new measured need and ADR.
