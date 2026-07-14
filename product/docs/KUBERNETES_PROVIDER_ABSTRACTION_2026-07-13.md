# Kubernetes abstraction for heterogeneous GPU providers

Date: 2026-07-13

Decision: historical; superseded for implementation by [the simplicity review](../../docs/SIMPLICITY_REVIEW.md), [current fleet blueprint](../../infra/docs/MULTI_PROVIDER_GPU_FLEET.md) and [multi-node contract](MULTI_NODE_INFERENCE.md)

Scope: fleet actuation and observation; not request routing, financial authority, or a promise that every provider runs Kubernetes

## Answer

> Do not implement the CRDs or signed Redis targets described below. PostgreSQL allocation/member/cell rows and direct Rust provider drivers are the current authority. This document is retained to explain the rejected Kubernetes-management abstraction.

We should abstract every curated GPU provider through the **Kubernetes API**, but we should not abstract every provider as **Kubernetes compute**.

The AWS management EKS cluster hosts a Grad fleet API and controllers. Native providers reconcile a Grad `CapacityAllocation` to their container/VM API. Managed-Kubernetes providers reconcile that same resource to a bounded child cluster/NodePool plus a signed Grad cell bundle. Both produce an `InferenceCell` and eventually a signed Redis `CellTarget`. Native allocations never become fake Nodes, and no request waits on Kubernetes.

```text
PostgreSQL desired policy / lease authority
              |
              v
      fleet-spec-writer (AWS EKS)
              |
       CapacityPool CRD
              |
       capacity broker
              |
    CapacityAllocation CRD
       /                \
native provider       managed-K8s provider
controller            controller + child agent
       \                /
        InferenceCell CRD/status
                 |
       target projector signs
                 |
       Redis CellTarget snapshot
                 |
gateway -> AWS inference edge -> cell runtime
```

The value is operational uniformity: reconciliation, status, conditions, events, RBAC, admission, finalizers, replayable tests, and one operator view. The boundary remains truthful because the provider-specific controller still owns the leaky lifecycle details.

## Vocabulary

Use these terms consistently:

| Term | Meaning | Examples |
| --- | --- | --- |
| **model provider** | Upstream company/API whose exact model a direct customer selects | OpenAI, Anthropic, Google |
| **capacity provider** | Infrastructure supplier from which Grad acquires GPU allocations | a GPU marketplace, VM cloud, managed-Kubernetes GPU cloud |
| **distribution channel** | Gateway or platform that sends paid traffic to Grad-owned inference | OpenRouter, Cloudflare AI Gateway |
| **cell substrate** | How a capacity-provider cell is run | native container/VM, managed Kubernetes, self-managed Kubernetes |
| **owned inference** | Grad-controlled model/runtime/release and serving contract | Hardware may be rented from a capacity provider |

Never use a generic `provider` field where more than one interpretation is possible. Contracts use `model_provider_id`, `capacity_provider_id`, or `distribution_channel_id`.

## Authority and writer matrix

| State | Durable authority | Runtime projection / writer | Request-path use |
| --- | --- | --- | --- |
| Org money, workspace/key policy, channel receivable policy | PostgreSQL | financial projector -> Redis | gateway reads/mutates Redis atomically |
| Model/release qualification and price books | PostgreSQL | ModelOps -> signed Redis route release | gateway reads Redis |
| Desired capacity policy, budgets, durable lease history | PostgreSQL | fleet planner -> CRD spec | none |
| Runtime capacity actuation | rebuildable CRD instances | one fleet-spec-writer (planner/broker) writes spec; provider controller reconciles | none |
| Provider external resource | provider API | matching provider controller only | none |
| Cell registration/readiness | rebuildable `InferenceCell.status` | authenticated cell registry/controller | none |
| Ready serving targets | signed release in Redis | target projector only | gateway selects target |
| Edge connection ownership | inference-edge shard memory | cell establishes/renews connections | edge dispatch only |

Production admission policy permits only fleet service accounts to write dynamic specs and their assigned status subresources. Human edits are break-glass and audited. GitOps owns schemas/controllers, not dynamic instances. If EKS is lost, PostgreSQL plus provider list/audit rebuilds the resources; etcd is never the only record of spend or external ownership.

## Fleet API

The initial API group is `fleet.grad.dev/v1alpha1`. CRDs use structural schemas, status subresources, printer columns, bounded lists/strings, CEL validation where sufficient, and conversion tests before another served version appears. No CRD contains customer IDs, prompts, generated content, tokens, cache keys/tensors, provider credentials, bootstrap bearer grants, or trace data.

### `CapacityPool`

One aggregate desired-capacity projection for an exact immutable release and policy envelope.

`spec` includes:

- `intentId`, `intentGeneration`, `releaseDigest`, environment, speed, region/data/security classes;
- desired ready token capacity, warm floor, maximum allocations and queue/SLO envelope;
- allowed capacity-provider classes, purchase classes, GPU/topology constraints and concentration limits;
- maximum quote/effective-successful-token cost, hourly/daily budget references and acquisition deadline;
- immutable policy/evidence digests and PostgreSQL owner epoch.

`status` is summarized by the broker: desired/ready/draining token capacity, active allocation counts, constrained reason, observed generation, last decision digest, and standard conditions. It does not contain one unbounded provider-offer list.

Only the fleet-spec-writer creates/updates pool spec. A stale owner epoch cannot reduce or expand capacity.

### `CapacityAllocation`

One provider lifecycle unit and the Kubernetes projection of one durable PostgreSQL `CapacityLease`.

`spec` includes:

- `leaseId`, `poolRef`, `capacityProviderId`, adapter/version and opaque provider account reference;
- selected opaque offer token, region/zone, exact GPU/topology and cell substrate;
- signed bootstrap/release manifest digests, ingress mode, acquisition deadline, TTL;
- quoted maximum price, billing quantum/cost ceiling, idempotency key and owner epoch.

`status` includes:

- sanitized opaque external-resource hash/reference and provider observation generation;
- normalized lifecycle state and timestamps;
- acquired quote/billing start/stop evidence class;
- conditions `Accepted`, `Acquired`, `Bootstrapped`, `Attested`, `Ready`, `Draining`, `Released`, `Degraded`, and `OrphanRisk`;
- failure category, retry-after, observed generation, assigned cell reference and cleanup evidence digest.

Exactly one controller selected by `capacityProviderId` owns status and `fleet.grad.dev/external-cleanup`. Apply and cleanup are idempotent. Updating fields that change provider identity, release, topology, or price ceiling creates a new allocation; it does not mutate an acquired allocation in place.

### `InferenceCell`

One provider/region/security/ingress boundary with one or more allocation references and exact release groups.

`spec` contains only fleet-spec-writer-owned identity and immutable eligibility: cell ID, capacity provider, substrate, region/data/security class, allocation refs and approved release digests. `status` contains authenticated agent generation, short-lived certificate identity hash, ingress mode, edge shard registrations, ready/draining release capacity, sanitized heartbeat time, and conditions `Connected`, `Attested`, `ReleaseReady`, `CapacityReady`, `Draining`, and `Fenced`.

A cell never makes itself routable. The cell registry validates certificate, allocation, manifest, hardware/runtime attestation and synthetic warmup. The target projector then constructs and signs a bounded `CellTarget` from qualified PostgreSQL release state plus Ready cell status.

## Reconciliation paths

### Native container/VM capacity

1. The fleet-spec-writer selects a qualified offer, atomically records the durable PostgreSQL `CapacityLease`/owner generation, then creates the matching `CapacityAllocation` and `InferenceCell.spec` projection.
2. The provider controller uses stable lease tags/idempotency identity to search before create, then calls the native API. It writes sanitized external identity/status to Kubernetes; the lease observer persists those observations to PostgreSQL, and tag-based search closes the create-before-status crash window.
3. The allocation receives a one-use bootstrap reference, starts the signed cell image, and establishes mTLS/outbound relay.
4. The cell registry verifies the allocation/release/hardware and updates `InferenceCell.status`.
5. The target projector publishes only after all required conditions and release evidence pass.
6. Deletion/fencing first removes routing, drains bounded work, calls native release, confirms bill stop, records evidence, and removes the finalizer.

The launched process is an external allocation, not a Pod. We do not promise Kubernetes Services, volumes, exec/log APIs, PodDisruptionBudgets, or scheduler behavior where the provider cannot implement them.

### Managed-Kubernetes capacity

Persistent provider account/network/cluster foundations may be Terraform-owned when their lifetime justifies it. A provider controller reconciles the allocation into the provider-supported GPU NodePool or capacity API. A pull-based cell agent applies the signed, cell-scoped runtime bundle inside the child cluster and reports readiness. The AWS management controller does not need a permanent cluster-admin credential to every child cluster.

Provider autoscaling may satisfy bounded desired nodes inside the allocation, but it cannot exceed the broker's budget/concentration envelope. Argo in AWS does not own child runtime instances. No child cluster has Aurora, Valkey, ClickHouse, Stripe, trace-S3, or capacity-provider credentials.

### Self-managed Kubernetes

This is an evidence-gated substrate for stable raw-VM providers, not the default adapter. Control-plane nodes must be regular/non-spot, and one cluster remains inside one provider/region cell. The same central CRDs represent allocation and cell readiness; local Kubernetes remains an implementation detail.

## Target publication and inference-edge connections

Kubernetes is too slow and too failure-prone to be a per-request registry. The target projector watches cell status and release state, removes stale/fenced targets immediately, signs the resulting target set, and atomically advances the Redis release pointer. The gateway only sees bounded signed targets.

For `OUTBOUND_RELAY`, every production cell maintains connections to at least two inference-edge shards in different AWS AZs. `CellTarget` carries an edge shard set and target epoch. The gateway deterministically chooses a healthy shard; the edge dispatches from its in-memory connection table. A disconnect fences that shard registration, and the projector removes the cell when the required redundant connectivity/heartbeat window is lost. There is no live lookup in PostgreSQL or Kubernetes. `DIRECT_MTLS` and `MANAGED_LB` targets use the same epoch/fencing rules.

## Failure, deletion, and recovery

| Failure | Required behavior |
| --- | --- |
| Kubernetes API/controller outage | Existing Redis targets/edge connections serve; no new capacity mutation; TTL/budget alarms fire. |
| PostgreSQL/fleet planner outage | Existing CR specs reconcile and cells serve; no new intent generation or budget expansion. |
| Provider API outage | Existing cells serve; acquisition/release retries are bounded; unknown billing state freezes new allocations for that adapter. |
| Controller restart/duplicate event | Search by lease tags/idempotency, compare owner epoch, and converge without duplicate allocation. |
| Finalizer stuck | Alert before TTL/cost bound; provider-list sweeper attempts cleanup; break-glass records orphan risk and cleanup owner before removal. |
| Management cluster loss | Freeze acquisition, restore GitOps/controllers, recreate CR projections from PostgreSQL, list/re-adopt or release tagged provider resources, then republish targets. |
| Cell spoof/stale heartbeat | Certificate/allocation/release mismatch is rejected; stale epoch is fenced; no route is signed. |
| Provider resource exists without lease | Quarantine, stop route publication, release after conservative audit, and freeze adapter on unexplained recurrence. |

CRs exist only for active and bounded recent operational history. Terminal allocation detail is copied to PostgreSQL, then CR instances are garbage-collected after the audit/recovery window. Cardinality is proportional to capacity, never traffic.

## Security model

- One controller deployment/service account/network policy/credential identity per capacity provider; a compromise cannot read another provider's credential or sign routes.
- Raw credentials stay in Secrets Manager and are mounted only into the matching controller. CRDs store opaque references and sanitized hashes.
- Admission validates immutable identity, release/topology, maximum cost, deadlines, bounded strings/lists, and allowed provider/substrate combinations.
- Controllers use leader election, exponential backoff with jitter, provider token buckets, request deadlines, circuit breakers, and content-free events.
- The target projector and release signer are separate from provider controllers. A provider adapter cannot make an unqualified cell routable.
- Cell agents receive short-lived, lease/release/provider-bound certificates and manifests, never database, Redis, customer key, trace-decrypt, or provider API credentials.
- Kubernetes audit, controller logs, metrics, events, and status are leak-scanned; provider error bodies are classified/sanitized before persistence.

## Why not the tempting alternatives

| Option | Decision | Evidence / reasoning |
| --- | --- | --- |
| Grad CRDs/controllers | Choose | Kubernetes documents custom resources/controllers as a declarative API over controlled resources with spec/status, validation, RBAC and finalizers. This is exactly the capacity lifecycle shape. |
| Make native supply fake Nodes with Virtual Kubelet | Reject | Virtual Kubelet explicitly masquerades as a kubelet and requires Pod/container/supporting-resource lifecycle behavior. Allocation APIs do not honestly satisfy the full model, and Grad does not need arbitrary Pod scheduling. |
| Crossplane | Defer | Managed resources correctly reconcile external APIs, but custom capacity providers and Grad's bidding/interruption/attestation/route logic still have to be built. Current polling/composition/RBAC/upgrade surface adds more seed machinery than it removes. |
| Cluster API everywhere | Reject | Its provider contracts are cluster/machine/machine-pool/bootstrap/control-plane contracts. Use an existing qualified provider for a durable child cluster, not for every disposable serving allocation. |
| Karmada/global cluster | Reject | Workload propagation is not native capacity acquisition. A WAN-spanning scheduling/control failure domain conflicts with disposable independent cells. |
| PostgreSQL-only bespoke loops | Fallback | Simpler dependency count, but gives up the management-cluster API/operator tooling. The same Protobuf adapter contract keeps reversal possible. |

## Verification contract

Before a real provider controller may acquire production capacity:

- CRD schema/version golden tests and generated Rust/TypeScript/JSON Schema sync checks pass;
- Rust `proptest` state machines generate create/update/delete/restart/duplicate/reorder/API-timeout/finalizer/owner-epoch/orphan sequences against fake providers;
- TypeScript `fast-check` models compare PostgreSQL intent/lease history, CR spec/status, provider inventory, and Redis target projection;
- Kind envtest proves status RBAC, admission rejection, leader failover, finalizer cleanup, CRD upgrade and Argo non-ownership of dynamic instances;
- E2E proves management API/PG/provider API loss does not interrupt already-published cell traffic;
- a paid bounded qualification run proves create/list/re-adopt/fence/release/bill-stop/orphan audit under a hard maximum cost and unconditional cleanup;
- target publication tests prove no stale, self-asserted, mismatched-release, single-shard relay, or unqualified cell reaches Redis;
- telemetry leak tests reject customer IDs/content, credentials, bootstrap grants, provider raw error bodies and cache material.

Every property failure persists seed, shrink path, normalized provider trace, CR snapshots and a copy-paste `grad test replay` command.

## Evidence and uncertainty

Evidence labels below are explicit:

- **Vendor-reported:** Kubernetes says custom resources plus controllers provide a declarative API and supports separate status authorization, validation and finalizers; it also warns against using CRDs as application/end-user data storage. [Kubernetes custom resources](https://kubernetes.io/docs/concepts/extend-kubernetes/api-extension/custom-resources/)
- **Vendor-reported:** Kubernetes controllers reconcile `.spec` desired state toward observed state. [Kubernetes controllers](https://kubernetes.io/docs/concepts/architecture/controller/)
- **Vendor-reported:** finalizers delay deletion until controllers complete cleanup, but deletion remains pending while finalizers exist. [Kubernetes CRD finalizers](https://kubernetes.io/docs/tasks/extend-kubernetes/custom-resources/custom-resource-definitions/#finalizers)
- **Vendor-reported:** Crossplane managed resources create and reconcile external resources; external observation commonly relies on polling, and controller/provider availability is required for cleanup. [Crossplane managed resources](https://docs.crossplane.io/latest/get-started/get-started-with-managed-resources/), [Crossplane reconciliation](https://docs.crossplane.io/latest/guides/pods/)
- **Vendor-reported:** Virtual Kubelet presents other APIs as Kubernetes Nodes and provider integrations must support Pod/container/supporting-resource lifecycle. [Virtual Kubelet overview](https://virtual-kubelet.io/docs/), [provider interface](https://virtual-kubelet.io/docs/providers)
- **Vendor-reported:** Cluster API's current provider contracts cover infrastructure clusters/machines/machine pools, bootstrap, control plane, IPAM and add-ons. [Cluster API provider contracts](https://cluster-api.sigs.k8s.io/developer/providers/contracts/overview)
- **Vendor-reported:** the Rust `kube` runtime provides controller, watcher, event and finalizer building blocks; its finalizer documentation requires idempotent apply/cleanup and notes deletion can stick while cleanup fails. [kube runtime](https://docs.rs/kube/latest/kube/runtime/), [kube finalizer](https://docs.rs/kube-runtime/latest/kube_runtime/finalizer/fn.finalizer.html)
- **Analytical/derived:** Grad CRDs reduce operational vocabulary but do not erase provider differences; that conclusion follows from the external-resource contracts and must be validated through two unlike adapters.
- **Uncertainty:** no Grad controller, provider API, EKS failure, etcd scale, or real allocation was exercised in this planning pass. Runtime/version choice and thresholds remain qualification-gated.

Falsification: reverse the decision if a native and managed-Kubernetes spike shows the CRD projection creates persistent dual-authority races or materially worse acquisition/cleanup reliability than a PostgreSQL-only controller, or if a supported Crossplane provider removes most custom lifecycle code and passes the same security/cost gates.
