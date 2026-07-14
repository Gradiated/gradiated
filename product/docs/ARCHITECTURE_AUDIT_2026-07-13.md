# Full product and architecture audit

> Historical audit. The current implementation authority is [the system manual](../../docs/SYSTEM_MANUAL.md), [implementation manual](../../docs/implementation/README.md) and [simplicity review](../../docs/SIMPLICITY_REVIEW.md). Do not implement the older fleet-CRD, ClickHouse or protocol breadth described here.

Date: 2026-07-13

Scope: seed product, gateway, billing, traces, owned inference, external capacity, distribution channels, AWS/Kubernetes, testing, delivery and operations

Companion decision: [Kubernetes provider abstraction](KUBERNETES_PROVIDER_ABSTRACTION_2026-07-13.md)

## Executive result

The architecture is coherent enough to proceed one level deeper after the corrections in this pass. The core shape remains:

- revenue-first prepaid gateway and simple Vite/Hono control plane;
- organization-funded billing with workspace policy/keys;
- Rust gateway with Redis as its only synchronous **internal state/control** dependency;
- curated exact direct-model lanes and Grad-owned `grad/<effort>/<speed>` lanes;
- PostgreSQL authority, S3 retained encrypted payloads, ClickHouse replayable content-free analytics;
- AWS inference edge plus independent external-provider cells;
- Kubernetes CRDs/controllers as the fleet actuation interface, without fake Nodes or a global cluster;
- always-on tenant-isolated KV/prefix cache, including no-retention;
- OpenRouter first as a downstream distribution channel for differentiated Grad supply.

The review found no reason to replace these foundations. It did find ambiguous vocabulary, a gateway dependency wording error, incomplete provider-channel accounting, underspecified CRD/PG ownership, relay-connection routing, reserve estimation, allocation-cost attribution, cache deletion fencing, and GitOps ownership. Those are resolved below. Remaining items are measured release gates, not hidden architecture choices.

## Canonical invariants

1. PostgreSQL is durable authority for business/configuration/release/financial/audit state; no other store can mint credit, membership, price, qualification, or desired budget.
2. Redis is the gateway's only synchronous internal **state/control** dependency before dispatch. Direct model APIs and the AWS inference edge are upstream serving dependencies. The gateway does not call PostgreSQL, Kubernetes, provider lifecycle APIs, Stripe, S3, ClickHouse, or the Hono API.
3. A customer direct ID remains on the exact curated model provider/model/version. A Grad ID remains on the exact immutable Grad release and speed/effort policy. No silent cross-lane downgrade or fallback exists.
4. One organization owns credit; workspaces and keys own attribution and limits, not wallets. Low-credit concurrency is calculated atomically after proposed reserve.
5. Every dispatch has one admitted reservation or one separately admitted distribution-channel receivable authorization. These accounting domains never share balances or credentials.
6. Product Intelligence retains encrypted payload traces by default; no-retention suppresses durable payloads but never disables active/prefix KV cache.
7. Kubernetes/provider APIs are slow-path actuation only. Gateway and inference edge use signed Redis targets and live connection state, never Kubernetes discovery.
8. Cells are untrusted, disposable execution boundaries. They have no customer keys, financial/customer database authority, trace-decrypt keys, route-signing key, or capacity-provider credentials.
9. Routes, releases, prices, model/runtime/artifact identities and capacity targets are immutable/versioned; rollback advances a pointer and never reinterprets an admitted request.
10. Property-based tests and official-client E2E are implementation gates, with real-provider/GPU runs bounded and protected.

## Resolved gap matrix

| Area | Finding | Resolution / canonical owner | Status |
| --- | --- | --- | --- |
| Vocabulary | “Provider” meant model API, GPU supplier and downstream gateway. | Freeze `model provider`, `capacity provider`, `distribution channel`, and `cell substrate`; identifiers must be qualified. | Resolved |
| Gateway boundary | “Only internal network dependency is Redis” contradicted the AWS inference-edge call. | Redis is the only synchronous internal **state/control** dependency; edge is an owned upstream serving dependency after admission. | Resolved |
| Fleet authority | PostgreSQL leases and proposed CRDs could both appear authoritative. | PG owns durable intent/lease/budget/audit; fleet worker alone projects CR spec; controllers own status/finalizers; CRs are rebuildable. | Resolved |
| Kubernetes abstraction | Native providers lacked a common operational surface. | Central Grad CRDs/controllers reconcile native APIs or managed child substrates; no fake Node/Pod semantics or stretched cluster. | Resolved |
| GitOps/runtime ownership | Argo “owns Kubernetes apps” could prune dynamic fleet objects. | Argo owns CRDs/controllers/RBAC/static config only; fleet services own dynamic CR instances; ApplicationProjects exclude/prune-ignore those instances. | Resolved |
| Endpoint model | `ProviderEndpoint` conflated direct model endpoints with Grad cells. | Rename concept to `DirectModelEndpoint`; Grad uses `InferenceCell` and signed `CellTarget`. Migration aliases are read-only and time-bounded. | Resolved |
| Relay HA | Cell registration did not say which edge pod owned an outbound connection. | Cells maintain two-AZ edge-shard connections; targets carry shard set/epoch; edge uses in-memory shard registry and projector fences stale connectivity. | Resolved |
| Route publication | Cell heartbeat appeared capable of becoming a route indirectly. | Cell registry may update status only; independent target projector combines qualification + attestation + connectivity and alone signs Redis targets. | Resolved |
| Kubernetes outage | Desired behavior existed, rebuild authority did not. | Existing targets serve; freeze mutations; rebuild CRs from PG, list/re-adopt/release tagged resources, then republish. | Resolved |
| Finalizer/orphans | Finalizer alone cannot guarantee external cleanup. | Stable tags/idempotency, PG lease, provider-list sweeper, TTL/cost alarms, and audited break-glass orphan risk are mandatory. | Resolved |
| Provider secrets | Adapter modules shared one fleet-controller identity in the earlier shape. | One deployment/SA/network policy/secret identity per capacity provider; broker and route signer have no provider secret. | Resolved |
| Reserve estimation | Token/multimodal maximum was not safely bounded for every protocol. | Known tokenizer exact count; otherwise conservative byte/item/modality upper bound plus max-output/context; reject if a published maximum sell exposure cannot be proved. | Resolved |
| Capacity reject after reserve | Settlement path for stale capacity was only implicit. | Release reservation, decrement concurrency exactly once, emit a zero-sell settlement reason, retain failed-attempt buy evidence, return stable 429/503 by stage. | Resolved |
| Midstream charging | “Partial usage” left customer policy ambiguous. | Charge measured delivered units under fixed SKU; no transparent replay after output; no-usable-output gets one compensating credit when eligible. Partial usable output is charged, with service credits handled as explicit compensating policy. | Resolved |
| Cache-priced units | Customer charge for Grad cache hits was not explicit. | Reserve assumes uncached worst case; runtime terminal usage authoritatively reports cached input; settle against immutable cached-input SKU. Cache metrics never override metering. | Resolved |
| Cache deletion | Trace deletion did not immediately prevent reuse of old ephemeral cache. | Workspace/org deletion or privacy-boundary change closes admission and rotates the projected cache epoch/scope; new requests cannot address old blocks, which expire/evict without payload indexing. | Resolved |
| Distribution billing | OpenRouter traffic was said to have separate accounting but lacked admission architecture. | PG channel contract/receivable ledger -> Redis `ChannelAccountProjection`; atomic channel limits/reserve, separate credentials/cache scope/price book, channel settlement export and reconciliation. | Resolved |
| Channel data | External marketplace traces could accidentally feed first-party intelligence. | Channel policy defaults to content-free metering/SLO facts; no first-party trace UI or migration recommendations; payload use requires an explicit downstream contract and isolated scope. | Resolved |
| GPU cost accounting | Request buy cost did not naturally map to hourly allocations/idle cost. | PG records invoices/leases; ClickHouse derives request GPU-seconds/token cost, idle and interruption loss by release/cell; allocation cost informs margin but never mutates customer usage. | Resolved |
| Model artifacts | Lifecycle existed but license provenance could be detached from release. | Artifact/license/source/redistribution/region digests are immutable release eligibility and signed manifest fields; invalidation fences release targets. | Resolved |
| Public errors | `cell_not_available`, 429, 503 terms overlapped. | Pre-dispatch policy/catalog absence is 404 only for nonexistent/ineligible product; admitted temporary exact-lane capacity is 429; internal admission/route infrastructure outage is 503; wire adapters map stable internal codes. | Resolved |
| Client idempotency | Billing idempotency existed but caller replay semantics were unclear. | Optional bounded `Idempotency-Key`/`x-grad-request-id` deduplicates in-flight admission and charge; no response-body replay guarantee. Duplicate completed inference returns a conflict/status reference unless a protocol later defines replay. | Resolved |
| Trace authority | ClickHouse and S3 boundaries were already sound. | Keep PG trace registry/tombstone authority, S3 ciphertext payload, ClickHouse typed replayable facts; no gateway or browser DB access. | Confirmed |
| No-retention | Requirement could be read as zero transient state. | Explicitly disclose encrypted transport/process memory and bounded ephemeral tenant-isolated cache; no durable payload trace. | Confirmed |
| DR | External GPUs could be misread as AWS-region failover. | Cells are not a shadow control plane. Single-region financial/Valkey authority remains an explicit seed limitation. | Confirmed |
| CI/cloud writes | Direct-to-main automation could imply unapproved production mutation. | Main runs checks/dev reconciliation; staging/prod remain protected environment promotions; real provider runs have explicit secret, cost and cleanup gates. | Confirmed |
| Product simplicity | Fleet/provider breadth risked leaking into customer UX. | Default UI remains keys, models, usage, traces and billing; capacity provider/host/bidding controls are operator-only. | Confirmed |

## End-to-end request contracts

### First-party prepaid request

```text
workspace key -> Redis auth/policy/route snapshot
              -> conservative maximum sell reserve + concurrency
              -> exact direct model provider OR signed Grad cell target
              -> stream and monotonic usage evidence
              -> one Redis settlement
              -> PG ledger + usage + analytics outbox
              -> optional encrypted Product Intelligence trace
```

The capability planner must prove an upper sell bound before reserve. For known tokenizers it counts exact canonical input. Otherwise it uses a tested safe upper bound from bytes/items plus published multimodal units and the smaller of request/model maximum output. Unsupported/unbounded inputs fail before spend. Worst-case reserve prices input as uncached; settlement uses measured input/cached-input/output/reasoning/tool units from the exact release/adapter.

If target capacity disappears after reserve but before output, the gateway performs only the release-allowed exact-lane retry. Terminal failure creates an idempotent zero- or measured-sell settlement, releases unused reserve, decrements in-flight once, and emits failed-attempt buy evidence. After any protocol-usable output, no transparent replay occurs.

### Distribution-channel request

OpenRouter and other gateways authenticate as a `distribution_channel_id` and credential, not as a customer organization/workspace. PostgreSQL owns contract status, credit/receivable ceiling, aging/risk state, channel price book, model allowlist, concurrency/rate/capacity caps and payout/reconciliation terms. A projector writes a `ChannelAccountProjection` to Redis.

The gateway runs a channel-specific atomic admission command that reserves receivable exposure and concurrency before dispatch. It shares protocol, exact Grad release, cell routing and metering code, but never touches organization credit, workspace keys, first-party trace retention, or cache scopes. Settlement appends channel usage/revenue events; a worker posts the receivable ledger and exports/reconciles downstream request IDs and units. Credit/invoice aging can restrict or suspend new channel traffic while already-admitted requests settle.

### Owned Grad request

The gateway selects a signed exact-release `CellTarget` from Redis and calls the named inference-edge shard. The edge validates release/target epoch and uses its live connection registry. The cell router admits against local queue/token/deadline and cache affinity, then serves the immutable release. Provider lifecycle and Kubernetes APIs never enter this path.

## Store and plane map

| Plane / store | Owns | Must not own |
| --- | --- | --- |
| PostgreSQL | org/workspace/users, ledger, channel receivables, prices/releases/qualification, desired capacity/lease history, trace registry, experiments/audit | live request dispatch, payload blobs, hot GPU discovery |
| Redis/Valkey | projected auth/policy/balance/channel exposure, atomic reservations/concurrency, signed route targets, financial events, encrypted trace transport | durable business truth, raw cache, provider lifecycle |
| Kubernetes management API | rebuildable capacity pool/allocation/cell runtime intent/status | customer/application data, money, route signing authority, per-request objects |
| Capacity-provider API | external allocation reality and invoice evidence | customer identity, sell price, route decision |
| Inference edge | target validation, live cell/shard connections, canonical stream relay | money, provider acquisition, PostgreSQL/Kubernetes lookup |
| Cell | exact release runtime, local queue, ephemeral tenant-salted cache, content-free health | customer keys/IDs, traces, route publication, financial authority |
| S3 | encrypted retained payloads and separately scoped signed model artifacts | query analytics, financial truth, live cache |
| ClickHouse | replayable content-free request/attempt/evaluation facts and aggregates | authorization, raw payloads, ledger, admission |

## Product surface after simplification

Seed customer concepts remain only:

- organization, default workspace and optional additional workspaces;
- workspace API keys, members, hard limits and Product Intelligence/no-retention;
- exact curated models or `grad/<effort>/<speed>`;
- usage/traces/recommendations and organization billing/top-ups.

Customers do not configure capacity providers, Kubernetes, bids, cells, runtime engines, replicas, cache nodes, fallback graphs, or host allowlists. Advanced users can pin a supported **model provider** for direct models; that is distinct from the hidden capacity provider serving Grad.

## Remaining measured gates before implementation depth increases

These are not architecture ambiguities; they require evidence or product/legal input at the named checkpoint:

1. Select the first native capacity provider and one managed-Kubernetes comparison candidate from current API/security/cost qualification.
2. Measure whether pinned Rust `kube` controller/runtime plus EKS satisfies reconciliation latency, leader failover, finalizer and etcd cardinality gates; retain a PostgreSQL-only fallback.
3. Freeze v1alpha1 CRD schemas only after fake-provider PBT shrinks at least the duplicate/reorder/restart/orphan cases and a migration/versioning exercise passes.
4. Benchmark inference-edge relay sharding, two-AZ reconnect, backpressure and stream recovery under expected concurrent streams.
5. Qualify production Valkey acknowledged-write durability and memory-pressure behavior; this remains the highest financial infrastructure gate.
6. Measure exact per-release tokenizer/reserve bounds, runtime usage accuracy and cache-hit metering before publishing prices.
7. Validate one Grad release on exact GPU/topology for quality, cache isolation, TTFT/ITL/throughput, interruption, successful-token cost and contribution margin.
8. Complete model license/redistribution, capacity-provider DPA/security, no-retention disclosure and distribution-channel commercial review.
9. Run an OpenRouter provider compatibility/soak and receivable reconciliation spike before applying or sending credentials.
10. Select primary AWS region and seed SLO/capacity numbers from latency, residency, provider connectivity and load evidence.

## Implementation order

The revenue path should not wait for broad GPU orchestration:

1. ship org/workspace/key/top-up, Redis admission, curated direct provider and usage UI vertical slice;
2. in parallel build fleet Protobuf/CRDs, fake controllers, Kind and inference-edge/cell simulator;
3. qualify one Grad release and one native capacity-provider controller under a hard budget;
4. expose only measured `flex`/`standard` Grad products to first-party design partners;
5. add the OpenRouter distribution-channel admission/settlement path and provider compatibility soak;
6. compare one managed-Kubernetes provider and add `fast`/`turbo` only where warm redundancy and margin pass.

This preserves fast gateway revenue while building the differentiated owned-inference supply in parallel.

## Audit method and limitations

Reviewed the current product/infra READMEs, ADR-0001 through ADR-0005, product architecture/API/billing/integration/testing/security/delivery documents, owned-inference and ClickHouse decisions, and infrastructure cloud/Kubernetes/autoscaling/Terraform/CI/security/local/delegation documents. Targeted searches compared authority, ownership, request path, provider terminology, retention/cache, billing/settlement, deployment and failure claims.

Evidence for the new fleet decision is current official Kubernetes, Crossplane, Virtual Kubelet, Cluster API and `kube` documentation linked in the companion brief. No cloud account, provider API, Kubernetes cluster, model runtime, payment processor or real request was exercised. All provider behavior, performance, costs, legal claims and numeric thresholds remain unmeasured until the listed gates run.
