# Owned inference implementation blueprint

## Scope and safety boundary

This is the concrete build contract from an admitted Grad request to an exact model runtime on external GPU capacity. It deepens [Owned Grad inference architecture](OWNED_INFERENCE_ARCHITECTURE.md) without changing its invariants.

AWS owns the public gateway, inference edge, durable release/capacity authority and fleet control. External cells are disposable execution domains. No live request calls PostgreSQL, Kubernetes or a capacity-provider lifecycle API. No cell receives a customer/channel credential, billing balance, provider API credential, trace decrypt key or database access.

## Processes and source layout

```text
product/services/
  inference-edge/
    crates/edge-server edge-core edge-transport edge-testkit
  cell-agent/
    crates/cell-server cell-router bundle-launcher runtime-supervisor cell-cache cell-testkit
  fleet/
    crates/fleet-domain fleet-planner fleet-controller target-projector provider-api provider-<name> fleet-testkit
```

Seed process consolidation:

- `inference-edge` is one Rust binary.
- `cell-agent` contains cell registration, local router, bundle launcher and runtime supervisor. A Python/native/Rust model runtime is a supervised child or colocated container behind a local contract, not another internet service.
- `fleet` is one Rust source workspace. Planner, target projector, sweeper and each provider controller run as separate entrypoints/Deployments because their IAM and scale differ.

## Canonical contracts

Internal Protobuf package names use `gradiated.inference.v1` under `product/proto/gradiated/inference/v1/`. Public model IDs may still begin with `grad/`.

### Gateway to edge/cell request

```text
GenerateRequest
  request_id, attempt_id
  route_release_id, bundle_digest, alias_generation
  canonical_model_identity, effort, speed
  canonical_input, capability_requirements, max_output_tokens
  absolute_deadline, queue_deadline
  request_scope_id, cache_scope, cache_affinity_key
  data_mode, event_schema_version

GenerateEvent
  event_sequence
  accepted(cell_id, runtime_replica_id, bundle_digest)
  queued(queue_class, estimated_start_deadline)
  output_delta(canonical_delta)
  usage(cumulative_input, cumulative_cached_input, cumulative_output)
  terminal(finish_reason, cumulative_usage, runtime_identity)
  error(stage, code, retry_scope, output_visible, cumulative_usage, usage_certainty)
```

`request_scope_id` is an opaque isolation/correlation value. It is not a billing principal and cannot be reversed to organization/workspace by edge/cell. Reservation IDs and sell prices remain in the gateway; an attempt ID is sufficient for cross-plane correlation.

All events are monotonically sequenced. Reconnect replay is allowed only within one attempt and deduplicated by sequence. Deadlines only tighten downstream. Edge/cell/runtime reject a request whose release, bundle digest, capabilities or data mode differ from their attested readiness.

### Product-to-fleet contracts

- `QualifiedBundleRef`: digest, qualification ID/policy/expiry, placement envelope, runtime mode and signatures.
- `RouteRelease`: public product/price/SLO plus exact qualified bundle and eligible placement policy.
- `CapacityIntent`: desired token capacity/warm floor by exact release/region/speed, allowed purchase/provider classes, budget and generation.
- `CapacityLease`: durable provider allocation identity, owner epoch, price/time bounds, release/topology, lifecycle and cleanup evidence.
- `CellAttestation`: observed hardware/software/runtime/bundle/cache/network identity signed by cell bootstrap identity.
- `CellTarget`: signed bounded serving projection containing release, cell, edge shards, epoch, hard attributes, expiry and target signature.

The canonical full bundle manifest is RFC 8785 canonical JSON governed by JSON Schema. Protobuf carries refs/commands/events and never defines a second full-manifest authority.

## Inference edge

### Core classes

```rust
pub trait TargetVerifier {
    fn verify(&self, target: &SignedCellTarget, now: Instant) -> Result<VerifiedTarget, TargetError>;
}

pub trait CellConnectionRegistry {
    fn register(&self, hello: CellHello, connection: CellConnection) -> Result<ConnectionLease, RegisterError>;
    fn heartbeat(&self, lease: &ConnectionLease, heartbeat: EdgeHeartbeat) -> Result<(), RegisterError>;
    fn candidates(&self, target: &VerifiedTarget) -> Vec<ReadyConnection>;
    fn fence(&self, cell: CellId, target_epoch: TargetEpoch, reason: FenceReason);
}

#[async_trait]
pub trait EdgeDispatcher {
    async fn generate(&self, target: VerifiedTarget, request: GenerateRequest,
                      cancellation: CancellationToken) -> Result<GenerateStream, EdgeError>;
}
```

`CellHello` includes cell/allocation/release/bundle identity, certificate identity, target epoch, connection mode, maximum streams and protocol version. Registration does not create route authority; it only proves connectivity for a target already signed by the target projector. Mismatched or expired epochs are fenced.

The edge accepts gateway calls only over private service identity and cells only over cell-scoped mTLS. Direct mode dials a cell endpoint; tunnel mode uses an outbound cell connection to one of at least two edge shards. Both implement `CellConnection` and identical event/deadline behavior.

Edge request steps:

1. authenticate gateway service and bound request size;
2. verify signed target, expiry, release/bundle and requested shard;
3. choose a ready connection by deterministic attempt hash and local saturation;
4. reserve an edge stream slot and forward request;
5. relay ordered events/backpressure/cancel without payload logs;
6. return typed pre-output retry scope or terminal interruption.

The edge holds no persistent request queue. If it cannot immediately choose a connection likely to meet the downstream queue deadline, it returns capacity failure. Fleet/control outages do not invalidate already verified unexpired targets/connections.

## Cell agent and local routing

### Cell lifecycle

```text
allocated -> bootstrapping -> identity_ready -> materializing
 -> starting -> warming -> attesting -> ready -> draining -> terminated
                               \-> failed -----------^
```

Every transition carries allocation ID, owner/target epoch, observed time and safe reason. `ready` requires exact artifact digest/signature, hardware/topology/driver envelope, runtime identity, cache policy, synthetic protocol/usage probe and redundant edge connectivity. A stale agent cannot overwrite a newer owner epoch.

### Core classes

```rust
pub trait BundleLauncher {
    fn inspect(&self, reference: BundleRef) -> Result<VerifiedBundle, BundleError>;
    async fn materialize(&self, bundle: &VerifiedBundle, destination: &Path,
                         budget: MaterializeBudget) -> Result<MaterializedBundle, BundleError>;
    async fn launch(&self, bundle: MaterializedBundle,
                    observed: PlacementIdentity) -> Result<RuntimeHandle, LaunchError>;
}

#[async_trait]
pub trait RuntimeSupervisor {
    async fn prepare(&self, manifest: &RuntimeManifest) -> Result<(), RuntimeError>;
    async fn start(&self, manifest: &RuntimeManifest) -> Result<RuntimeHandle, RuntimeError>;
    async fn health(&self, handle: &RuntimeHandle) -> Result<RuntimeHealth, RuntimeError>;
    async fn drain(&self, handle: &RuntimeHandle, deadline: Instant) -> Result<(), RuntimeError>;
    async fn terminate(&self, handle: RuntimeHandle) -> Result<ZeroizeReport, RuntimeError>;
}

pub trait CellScheduler {
    fn admit(&self, request: &GenerateRequest, now: Instant,
             snapshot: &ReplicaSnapshot) -> Result<QueueTicket, CellAdmissionError>;
    fn choose_replica(&self, ticket: &QueueTicket, snapshot: &ReplicaSnapshot)
        -> Result<RuntimeReplicaId, CellAdmissionError>;
}
```

The scheduler's hard ordering is exact bundle/readiness -> queue deadline/token capacity -> drain/health -> cache affinity. Cache locality never overrules correctness/deadline. Queue estimates use bounded declared input/output and measured service profile; stale estimates cause early rejection rather than infinite queueing.

## Runtime modes and local protocol

`RuntimeManifest.mode` is one of:

- `python_plugin`: pinned vLLM/SGLang/factory runtime process; Rust agent communicates over a Unix-domain socket using `RuntimeGenerateRequest/Event` derived from the same canonical model.
- `native_library`: Rust agent launches a small isolated host process that loads the qualified library through a versioned C ABI; avoid unsafe in-process loading at seed.
- `rust_engine`: Rust executable/process implementing the local runtime protocol; in-process optimization requires a later measured decision.

All modes expose:

```text
GetIdentity -> runtime/package/operator/bundle identities
Warmup(WarmupPlan) -> measurements and cache proof
Generate(RuntimeGenerateRequest) -> RuntimeGenerateEvent stream
Health -> content-free queue/GPU/cache health
Drain(deadline)
Shutdown
```

The Unix socket directory has cell-only permissions; messages have maximum sizes, protocol version, deadline and request sequence. Runtime crash isolation is mandatory. The supervisor owns restart budget and never silently changes bundle or runtime flags. A crash during an attempt produces explicit usage certainty.

## Cache contract

Active-sequence and prefix KV caching are mandatory for every generative ready runtime, including no-retention. `cache_scope` is opaque and already separated by principal, exact release and retention class. Block identity additionally includes tokenizer/adapter revision, multimodal canonical hash, prefix tokens and position.

`CacheManager` exposes only aggregate operations/metrics:

```rust
pub trait CacheManager {
    fn validate_policy(&self, manifest: &CacheManifest, placement: &PlacementIdentity) -> Result<(), CacheError>;
    fn fence_epoch(&self, old: CacheEpoch) -> Result<(), CacheError>;
    fn pressure(&self) -> CachePressure;
    fn zeroize(&self) -> Result<ZeroizeReport, CacheError>;
}
```

No control/product API lists blocks. No raw key/token/tensor appears in logs, metrics, crash dumps or support artifacts. Optional local NVMe spill is encrypted, bounded by service TTL, excluded from snapshots/backups and destroyed at teardown. Remote/distributed cache is not seed scope.

## Fleet authority and CRDs

PostgreSQL owns `capacity_intents`, `capacity_leases`, provider observations and budgets. Kubernetes objects are rebuildable projections:

| Resource | Spec writer | Status writer | Final action |
| --- | --- | --- | --- |
| `CapacityPool` | fleet planner/projector from PostgreSQL | capacity broker | aggregate desired/available capacity only |
| `CapacityAllocation` | broker/controller command | exactly one provider controller | acquire/release one external resource and report identity/cost/state |
| `InferenceCell` | fleet controller from lease/release | cell/fleet observer under field ownership | bootstrap/attest/connect/drain one cell |

CRD group is `fleet.grad.dev/v1alpha1`; domain payload fields are generated from or drift-checked against `gradiated.inference.v1`. Kubernetes metadata/finalizers/conditions remain CRD-specific.

### Fleet classes

```rust
pub trait CapacityPlanner {
    fn plan(&self, demand: DemandSnapshot, releases: ReleaseSnapshot,
            budget: FleetBudget) -> Result<Vec<CapacityIntent>, PlanError>;
}

pub trait CapacityBroker {
    fn reconcile(&self, intent: &CapacityIntent, observed: FleetSnapshot)
        -> Result<Vec<AllocationCommand>, BrokerError>;
}

#[async_trait]
pub trait CapacityProvider {
    async fn quote(&self, request: QuoteRequest) -> Result<Vec<CapacityOffer>, ProviderError>;
    async fn acquire(&self, request: AcquireRequest) -> Result<ExternalAllocation, ProviderError>;
    async fn observe(&self, id: ExternalAllocationId) -> Result<AllocationObservation, ProviderError>;
    async fn release(&self, id: ExternalAllocationId, reason: ReleaseReason) -> Result<ReleaseReceipt, ProviderError>;
    async fn list_owned(&self, lease_tag: LeaseTag) -> Result<Vec<ExternalAllocation>, ProviderError>;
}

pub trait TargetProjector {
    fn evaluate(&self, release: &RouteRelease, lease: &CapacityLease,
                attestation: &CellAttestation, edge: &EdgeConnectivity)
        -> Result<TargetDecision, TargetError>;
}
```

Provider adapters normalize offers but preserve evidence: raw offer reference/digest, quote time/expiry, currency/unit, interruption class, region, topology and vendor-reported versus measured fields. The broker applies hard release/security/topology/price/provider-concentration constraints before cost scoring.

### Durable acquire/release rule

Before an external acquire call, PostgreSQL records `CapacityLease(requested)` with provider idempotency/lease tag and maximum spend. After acquire, persist external identity before considering it owned. Provider resource tags always include environment, lease ID, owner epoch and expiry. A finalizer requests fenced/drained release, but a separate sweeper lists provider resources and cleans expired/unknown lease tags. Stuck finalizers never prove billing stopped.

Provider credentials exist only in the matching controller deployment. The target projector has signing/Redis rights but no provider secret. Cells have neither.

## Target publication and route safety

Target projector input is a consistent PostgreSQL/observed snapshot:

1. approved unexpired route release and qualification;
2. active capacity lease inside budget/placement envelope;
3. valid cell attestation for exact bundle/runtime/hardware/cache policy;
4. healthy redundant edge connectivity and target epoch;
5. no provider/cell/release fence or concentration violation.

It signs a bounded target set and submits a projection command. Node control projection activates the Redis version; gateway accepts only signature/key version/expiry it knows. Provider controllers and cells cannot write Redis routes.

## Spot and failure behavior

- Preemption notice fences new work immediately and drains until provider deadline; zero-notice heartbeat loss behaves as abrupt failure.
- Before output, gateway may retry another target for the exact release inside its attempt/deadline policy.
- After output, emit interruption and settle known usage; never replay.
- Fleet/PostgreSQL/Kubernetes/provider API outage leaves existing unexpired targets/cells serving and freezes unsafe new acquisition/publication.
- Edge shard loss uses another signed shard before output; no edge has target-signing or lifecycle authority.
- Exact release capacity exhaustion returns 429 and cannot consume a slower/other release.
- Cache loss changes performance only. Bundle/attestation mismatch prevents readiness and pages security/operations.

## Deployment and configuration

- Inference edge: minimum multi-AZ on-demand replicas, private service from gateway, public/tunnel listener restricted to cell mTLS, no database/provider API network path.
- Fleet planner/projector: AWS management EKS general on-demand nodes; leader election; PostgreSQL roles split from target signing/Redis role where practical.
- Provider controller: one deployment/service account/secret/network policy per provider account and rate limit.
- Cell agent: provider-specific hardened image/bootstrap; outbound-only mode preferred; artifact endpoints and edge only; rootless/read-only where runtime permits; no shell/SSH in production.

Configuration separates static process config (listeners, trust roots, protocol versions) from signed release/bundle and durable capacity intent. Helm/provider templates cannot override bundle-contained model/runtime/cache semantics.

## Verification and junior-agent packages

Cross-language goldens cover Protobuf, canonical bundle refs and target signatures. Proptest state machines cover cell lifecycle, edge reconnect/event dedupe, CRD owner epochs, provider acquire/release/idempotency, finalizer/sweeper races, target publication and spot loss. Kind covers CRD/RBAC/admission/leader/rebuild; Compose covers native allocation/fake cell.

Implement in order:

1. `OI-00`: Protobuf, canonical refs, target signing and fake edge/cell/provider simulator.
2. `OI-01`: edge target verifier, connection registry, stream relay and two-shard faults.
3. `OI-02`: bundle inspector/materializer and cell lifecycle/attestation.
4. `OI-03`: runtime supervisor plus Python-plugin tiny runtime over UDS.
5. `OI-04`: cell scheduler, mandatory cache scopes and preemption behavior.
6. `OI-05`: PostgreSQL capacity domain, CRDs and deterministic fleet reconciler.
7. `OI-06`: one native provider controller with fake then bounded real qualification.
8. `OI-07`: target projector and Redis route integration.
9. `OI-08`: managed-Kubernetes cell provider and portability qualification.
10. `OI-09`: diversified capacity/sparse speed publication and operations.

The first vertical requires one tiny signed bundle, fake provider/cell and official client through gateway/edge. The first real release uses one native provider and publishes only `grad/medium/standard` after exact cache, interruption, protocol, quality, cost and margin gates. Fast/turbo, multi-node, disaggregated serving and native/Rust runtime optimization remain separate evidence-driven packages.
