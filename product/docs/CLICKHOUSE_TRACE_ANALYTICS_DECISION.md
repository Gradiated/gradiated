# ClickHouse trace analytics decision

- decision date: 2026-07-13
- status: accepted for planning; implementation and cost/performance qualification remain open
- evidence class: current vendor-reported capabilities plus analytical architecture reasoning; nothing here is a measured Grad benchmark

## Question and decision

Should customer traces live in ClickHouse Cloud so the console can provide fast search, timelines, cost/latency analytics, workload grouping, and Grad migration recommendations?

**Decision:** use ClickHouse Cloud as the derived, customer-visible analytics projection, not as the only trace store and never as an authority for billing, authorization, retention, or raw payload custody.

The storage contract is deliberately split:

| Store | Owns | Must not own |
| --- | --- | --- |
| Aurora PostgreSQL | organization/workspace authorization; trace registry and tombstones; retention policy; per-trace wrapped-key state; financial ledger/usage authority; workload, recommendation, experiment and audit control state; ClickHouse projection checkpoints | raw request/response/tool payloads; high-volume dashboard scans |
| Private KMS S3 | compressed encrypted raw request/response/tool payloads and bounded exports; ciphertext is addressed through an opaque object reference | customer authorization; searchable indexes; financial facts |
| ClickHouse Cloud | replayable request/attempt/evaluation facts, typed dimensions, latency/token/cost copies, workload features, and aggregate projections used by the console | raw prompts/responses/tool arguments; credentials; sole trace copy; ledger truth; access-control truth |
| Valkey | short-lived gateway projections, financial event stream, and a separately quota-protected encrypted trace stream | durable customer analytics or raw-trace authority |

This gives ClickHouse the workload it is good at—append-heavy, high-cardinality analytical reads—while keeping immediate authorization and cryptographic deletion under systems we control.

## Claim scope, hypothesis, and falsification

The hypothesis is that one AWS-region ClickHouse Cloud service can be the seed analytics backend if it provides private application connectivity, encryption, bounded query roles, append/batch ingestion, TTL/deletion tools, and acceptable user-facing latency/cost at the expected trace volume.

The decision is falsified before production if any of these hold in the selected region/tier:

- EKS cannot reach the service through a qualified AWS PrivateLink path while public ingress is denied;
- the required encryption, backup, or contractual controls are unavailable or uneconomic;
- a scope-matched load test misses the trace-list/dashboard SLO or costs materially more than the Aurora-only seed alternative;
- duplicate/reordered projection, tenant isolation, retention, or restore-with-tombstones properties fail;
- ClickHouse failure can block gateway serving, financial posting, raw trace persistence, or deletion authorization;
- legal/security review requires immediate physical removal of every analytics copy on a schedule the managed backup/merge behavior cannot satisfy.

Non-scope: this brief does not select a final ClickHouse service size, prove a price, authorize a vendor contract, benchmark production traffic, or make ClickHouse a training-data store.

## Why ClickHouse Cloud

### Chosen over Aurora-only analytics

Aurora is already required and is the simplest system at very low volume. It remains the correct source of truth, but long-range trace filtering, percentile latency, workload cohorts, token/cost breakdowns, and model/release comparisons compete with financial/control transactions and become expensive to index and scan. Starting with a narrow ClickHouse projection avoids making a later dual-write migration part of the customer-facing trace launch.

The launch gate is still pragmatic: if measured seed volume and Cloud minimum cost do not justify it, the repository interfaces allow an Aurora read model temporarily. The public API never exposes ClickHouse semantics, so this fallback does not change the product contract.

### Chosen over S3 plus Athena

S3 is excellent durable payload custody but a poor interactive trace-list backend. Athena-style scans are useful for offline investigation and reconstruction, not the primary sub-second console path. S3 remains the raw encrypted store and replay source.

### Chosen over self-hosted ClickHouse on EKS

The product already operates EKS, but managing ClickHouse storage, replication, upgrades, backups, and capacity would add a stateful platform workstream unrelated to the inference moat. Cloud is the seed choice; self-hosting or BYOC is reconsidered only after measured cost, residency, or isolation needs justify it.

## Data model

No raw customer content is inserted into ClickHouse. Arbitrary headers, prompts, completions, tool arguments/results, files, URLs, free-form tags and customer-supplied workload labels remain encrypted in S3. The analytics allowlist contains typed fields only; a user-supplied workload identity becomes an internal UUID or workspace-scoped HMAC before projection.

Initial tables:

| Table | Grain | Representative fields |
| --- | --- | --- |
| `request_facts_v1` | one versioned terminal request fact | event/trace/request IDs; organization/workspace/key/workload IDs; start/end; ingress protocol; requested/canonical/actual model; provider or Grad effort/speed/release; data/capture mode; status/error class; capability flags; input/output/cache/reasoning units; copied sell amount; TTFT/queue/total latency; payload availability class; retention deadline |
| `attempt_facts_v1` | one upstream/owned-inference attempt | request/attempt IDs; endpoint class; model/release; start/end; status; safe error class; provider latency; metering evidence class; copied buy-cost evidence class |
| `evaluation_facts_v1` | one immutable replay/shadow/canary evaluation result | workspace/workload/candidate/experiment/release IDs; evidence level; evaluator version; protocol/schema/tool/quality/latency/cost outcomes; sample count; uncertainty and stop reason |
| `workspace_rollups_1h_v1` | one workspace/model/workload/hour aggregate | request/error counts; units; spend copy; latency quantiles; capture states |
| `model_rollups_1h_v1` | one provider/model or Grad release/hour aggregate | availability, units, latency quantiles, errors, margin evidence class |

`request_facts_v1` is a `ReplacingMergeTree`-style versioned projection ordered for `(organization_id, workspace_id, event_date, started_at, trace_id)` access and partitioned by event month or day after measurement. A row-level `retention_expires_at` TTL bounds storage, but every customer query also filters expired rows because TTL execution is asynchronous. Rollups never become financial truth and are recomputable.

Do not create a database/table per customer. One environment-scoped schema keeps operations simple. Tenant identity is the leading query key; public APIs can request only predeclared filters/sorts/aggregations.

## Ingestion and failure behavior

The two projections originate from different correctness paths:

```text
gateway settlement -> financial Valkey stream -> financial worker
  -> PostgreSQL ledger + usage fact + analytics outbox (one transaction)
  -> trace-analytics projector batches safe facts into ClickHouse

eligible Product Intelligence payload -> separate encrypted Valkey trace stream
  -> trace worker persists ciphertext to S3
  -> PostgreSQL trace registry marks object/key available

no-retain request -> no payload trace stream/object
  -> the same safe settled usage fact can still appear in ClickHouse with payload_state=no_retain
```

The projector uses a dedicated insert-only ClickHouse identity, client-side batches or asynchronous inserts with acknowledgement after flush, deterministic insert/deduplication tokens, bounded retries, and a dead-letter/replay state. The PostgreSQL outbox is pruned only after the ClickHouse checkpoint is durable and remains reconstructable from authoritative usage plus trace registry state. At larger scale, I-07 may qualify an S3 Parquet event log and managed S3 ClickPipe; Kafka is not required at seed.

ClickHouse is never in the Rust gateway path. If it is unavailable, inference, reservation/settlement, PostgreSQL financial posting, and S3 payload persistence continue. The console shows an explicit analytics-delay state while the projector catches up. Backpressure caps the projector and cannot consume Valkey billing headroom or exhaust Aurora connections.

## Customer read path

The browser never receives ClickHouse credentials and never submits SQL.

1. Hono authenticates the session and resolves an `AuthScope` containing one organization and the allowed workspace set from PostgreSQL.
2. A typed `TraceAnalyticsRepository` maps a closed set of API filters to parameterized ClickHouse queries. Every table access requires organization/workspace predicates, time bounds, result/byte limits, and a query ID tied to the API audit request.
3. Trace list, charts, model/workload summaries, and recommendation evidence read ClickHouse.
4. Trace detail first rechecks the PostgreSQL registry/tombstone. The control API then issues a signed, single-use trace-access grant; the internal trace-access service retrieves the one S3 object, obtains the still-live wrapped data key, decrypts, and streams without caching.
5. A no-retain or expired/deleted row can remain as minimum usage metadata only when the published policy permits; it never has a payload action.

Use separate ClickHouse identities for projection, read-only queries, schema migration, and deletion. RBAC and row policies are defense in depth, not a substitute for the Hono authorization invariant. The query role receives no mutation, file/table-function, URL, dictionary, or administration privileges.

## Retention and deletion

Logical access removal is immediate even though ClickHouse physical removal is asynchronous:

1. In one PostgreSQL transaction, mark the trace/workspace deleted, revoke outstanding grants, destroy or tombstone the per-trace wrapped data key, append an audit event, and enqueue S3/ClickHouse deletion work. All subsequent APIs deny payload access from this state.
2. Delete the S3 object and every noncurrent version. Per-trace key destruction makes remaining ciphertext unreadable before storage cleanup completes.
3. Issue a ClickHouse lightweight delete for narrow removals or a partition/mutation strategy for bounded bulk removals, then verify the row is no longer query-visible. The API filters PostgreSQL tombstones/retention deadlines during convergence.
4. Track completion in PostgreSQL and page missed deadlines. Restores must replay all tombstones and the current retention cutoff before a restored ClickHouse service becomes queryable.

ClickHouse documents that lightweight deletes mark rows first and physical removal occurs during a later merge; TTL deletion also runs during merges rather than immediately. Cloud backups therefore have an explicit residual window. Keep ClickHouse backup retention at the minimum approved recovery window because the projection is rebuildable, disclose that window, and never promise immediate physical erasure from managed backups. If launch review requires a stronger guarantee, keep personally identifying/content-derived fields out of ClickHouse or reject the design.

## Infrastructure contract

- provision one ClickHouse Cloud service per environment through the official Terraform provider in the selected AWS region;
- production EKS connects through AWS PrivateLink and the ClickHouse public IP allowlist is `DenyAll`;
- enable TLS and provider-managed encryption at minimum; production decides Enterprise TDE/CMEK before service creation because current documentation says TDE cannot be added to an existing service;
- use purpose-separated credentials in Secrets Manager/GitHub environment secrets, never Terraform source, Helm values, browser code, or logs;
- keep the service outside Kubernetes; Helm deploys only API/projector/migration workloads and network policy;
- local/CI use a pinned ClickHouse container with synthetic data; protected staging runs a small Cloud connectivity/schema/query/delete smoke;
- monitor query p50/p95/p99, scanned bytes, memory, errors, parts/merges/mutations, async insert failures, outbox lag/age, deduplication, tombstone age, and Cloud cost.

Initial unmeasured targets are: settled request searchable within 15 seconds at p95, common bounded console queries within 500 ms at p95, zero cross-workspace rows, and no gateway/ledger/S3 availability dependency on ClickHouse. I-07 replaces them with load evidence and a monthly cost envelope before production.

## Property and integration tests

Fast-check and proptest generate organization/workspace/key scopes, trace/usage events, duplicate and reordered projection commands, retention deadlines, deletes, restores, and ClickHouse outages. Required properties include:

- a query result is a subset of the authorized organization/workspace/time scope;
- replaying any event sequence converges to one visible terminal request fact and the expected rollup;
- ClickHouse copies equal authoritative PostgreSQL usage for reconciled sampled windows, but disagreement never mutates the ledger;
- an expired/tombstoned trace cannot return content even while a ClickHouse mutation is pending;
- no-retain produces no payload object/key/grant while retaining only permitted analytics facts;
- projector failure cannot change gateway admission, settlement, credit, or S3 persistence outcomes;
- restore plus tombstone replay cannot resurrect an accessible trace.

Official-client E2E sends synthetic OpenAI, Anthropic, Google, and Grad requests through the gateway, waits for the ClickHouse fact, opens eligible payload detail through trace-access, verifies no-retain has no object, and confirms delete/retention convergence. Pull requests use local ClickHouse; real-provider CI may write only synthetic protected-workspace traces.

## Source record

All sources were retrieved 2026-07-13. ClickHouse documentation is a living source and does not expose a stable page revision date in the rendered page.

| Source | Publication/revision | Evidence type | Relevant claim |
| --- | --- | --- | --- |
| [Private networking](https://clickhouse.com/docs/cloud/security/connectivity/private-networking) | living docs | vendor-reported | ClickHouse Cloud supports AWS PrivateLink connectivity. |
| [Setting IP filters](https://clickhouse.com/docs/cloud/security/setting-ip-filters) | living docs | vendor-reported | public access can be denied when PrivateLink is used; default public allow behavior must be tightened. |
| [Data encryption](https://clickhouse.com/docs/cloud/security/cmek) | living docs | vendor-reported | AES-256 storage encryption is default; Enterprise TDE/CMEK exists; TDE must be selected at service creation. |
| [Manage data with TTL](https://clickhouse.com/docs/guides/developer/ttl) | living docs | vendor-reported | TTL can remove/roll up rows but executes on background merges rather than immediately. |
| [Lightweight DELETE](https://clickhouse.com/docs/sql-reference/statements/delete) | living docs | vendor-reported | rows are marked first and physically removed on a later merge; large/frequent deletes have cost. |
| [Review and restore backups](https://clickhouse.com/docs/cloud/manage/backups/overview) | living docs | vendor-reported | Cloud has mandatory scheduled backups and documents a default daily/24-hour policy. |
| [Access control and account management](https://clickhouse.com/docs/operations/access-rights) | living docs | vendor-reported | ClickHouse supports RBAC and row policies, with row-policy limitations for mutating users. |
| [Getting-started production practices](https://clickhouse.com/blog/common-getting-started-issues-with-clickhouse) | 2026-02-20 | vendor-reported | batching/async inserts with acknowledgement are recommended; many small inserts and mutations create pressure. |

## Uncertainty, competing explanations, and next action

No workload has been measured and no ClickHouse quote or data-processing agreement has been reviewed. The largest uncertainties are minimum Cloud cost, Enterprise/TDE cost, PrivateLink availability/price in the final region, workload cardinality, deletion/backup legal interpretation, and whether Aurora alone is sufficient for the first few design partners.

Implementation package I-07/WP-07 must run a bounded synthetic spike against the selected Cloud tier and Aurora comparison: ingest duplicates/retries, query realistic tenant/time/model/workload filters at target concurrency, exercise TTL/delete/restore, simulate outage/backlog, and estimate monthly compute/storage/egress. Kill ClickHouse-for-launch if it fails a falsification rule; retain the storage/query interfaces and run the seed projection on Aurora until evidence changes.
