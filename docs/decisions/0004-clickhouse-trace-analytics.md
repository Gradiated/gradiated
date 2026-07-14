# ADR-0004: ClickHouse Cloud for trace analytics, not raw payload custody

- status: superseded for seed implementation by the 2026-07-14 simplicity review
- date: 2026-07-13
- owners: product and infrastructure
- supersedes: ADR-0003 only where it implied PostgreSQL alone served trace analytics

## Decision

> ClickHouse is not implemented at seed. PostgreSQL indexed usage/trace queries and measured rollups own the initial customer analytics path. This ADR remains the reintroduction evidence if a production-shaped benchmark meets the trigger in [the simplicity review](../SIMPLICITY_REVIEW.md).

Use one environment-scoped ClickHouse Cloud service as the replayable analytical projection for customer trace lists, charts, workload/model summaries, evaluation evidence, and Product Intelligence features.

Keep the authority split:

- PostgreSQL owns authorization, financial facts, trace registry/tombstones, retention/key state, recommendations/experiments, audit, and projection checkpoints.
- Private KMS S3 owns compressed encrypted raw request/response/tool payloads.
- ClickHouse stores only typed, allowlisted metadata, copied usage/latency/cost facts, derived workload/evaluation features, and aggregates. It stores no raw prompts, responses, tool arguments/results, files, credentials, arbitrary headers, or free-form tags.
- Valkey remains the gateway's only synchronous internal state/control dependency and transports financial events plus a separate bounded encrypted payload stream. ClickHouse is never on the serving path.

Hono is the only customer query surface. It authorizes in PostgreSQL and issues typed, parameterized, organization/workspace/time-bounded ClickHouse queries; browsers receive no database credentials or SQL capability. Payload detail is separately authorized and streamed from S3 by trace-access.

Deletes first tombstone and destroy per-trace wrapped-key access in PostgreSQL, then remove all S3 versions and ClickHouse rows asynchronously. TTL and lightweight deletes are treated as delayed physical cleanup, not immediate access revocation. ClickHouse backups use the minimum approved window and restores replay tombstones before query enablement.

## Rationale

Trace analytics is append-heavy, high-cardinality, percentile/aggregation-oriented, and user-facing. ClickHouse fits that workload better than adding broad analytical indexes and scans to the Aurora instance that owns money/control state. Managed Cloud avoids operating a second stateful distributed database on EKS.

ClickHouse is not the sole trace store because current official documentation states TTL and lightweight physical deletion occur through later merges, and Cloud maintains backups. Isolating raw content in our encrypted S3 plus keeping authorization/key state in PostgreSQL gives immediate logical/cryptographic revocation and makes the analytics projection rebuildable.

## Consequences

- positive: fast trace/workload/model analytics can scale independently of Aurora and the gateway;
- positive: no-retain requests can retain permitted usage analytics without any payload object;
- positive: ClickHouse outage causes dashboard lag, not serving, billing, or payload loss;
- negative: a fourth data service, projection lag, schema/versioning, reconciliation, deletion convergence, and vendor cost must be operated;
- negative: organization/workspace query scoping and restore tombstone replay become launch-critical security properties;
- negative: production TDE/CMEK and PrivateLink availability/cost must be decided before service creation and region freeze.

## Rejected alternatives

1. **Raw payloads only in ClickHouse.** Rejected for custody, deletion, mutation, authorization, and large sensitive string concerns.
2. **All trace analytics in Aurora.** Retained as a launch fallback if measured ClickHouse cost/benefit fails, not the target architecture.
3. **S3/Athena as the console backend.** Retained for reconstruction/offline analysis; rejected for the interactive path.
4. **Self-hosted ClickHouse on EKS.** Rejected at seed because operating its storage/replication/upgrades is not product differentiation.
5. **Kafka before ClickHouse.** Rejected at seed; PostgreSQL outbox plus batched idempotent projection is sufficient until measured throughput falsifies it.

## Gates and references

The decision, current primary-source evidence, schema, ingestion/read/delete flows, tests, falsification rules, and unresolved cost benchmark are in [ClickHouse trace analytics decision](../../product/docs/CLICKHOUSE_TRACE_ANALYTICS_DECISION.md).

Production requires measured tenant isolation, duplicate/retry convergence, query latency/cost, outage recovery, retention/delete/restore behavior, and PrivateLink/encryption controls. Failure preserves the public repository interfaces and moves the seed analytical projection to Aurora temporarily; it does not weaken raw-payload or gateway boundaries.
