# Worker

This TypeScript deployment runs supervised loops. Generation ingestion
moves terminal generation events from Valkey to ClickHouse. Settlement posts
ClickHouse usage to the PostgreSQL ledger. When `CONTENTS_BUCKET` is configured,
trace cleanup removes archived or deleted workspace content from S3.

## Generation ingestion

The loop reads the generation stream through a Valkey consumer group. For each
entry, it inserts the generation into ClickHouse and then acknowledges the
entry. It never acknowledges an entry before ClickHouse confirms the insert.
Entries that another consumer left pending are reclaimed after
`GENERATION_CLAIM_IDLE_MS`.

After each pass, the loop trims the stream. The trim never passes the oldest
pending entry. The loop reads the pending list and the delivery cursor in one
transaction, so a concurrent delivery cannot move the trim or the settlement
boundary past an entry that is not yet in ClickHouse.

## Settlement

Settlement posts one charge per organization for each five-minute slot. One
worker replica holds a PostgreSQL advisory lock and settles. The other replica
waits and takes control if the leader loses its database session.

A slot is eligible when it ends before both of these times:

- The ingestion boundary: the oldest pending stream entry, or the last
  delivered entry when none is pending.
- The current time minus `SETTLEMENT_DELAY_SECONDS`.

The leader validates a whole slot before it posts any charge in that slot. Each
generation must have one set of financial values
(`EGENERATION_FINANCIAL_CONFLICT`). The slot must match, each organization must
occur once, each charge must have generations, and each charged organization
must have a billing account. The
source ID `<slot>:<organization>` makes each posting idempotent. When the
leader restarts, it posts the latest posted slot again. The ledger replays a
posting with the same amount. A posting with a different amount stops
settlement at that slot with `ESETTLEMENT_CONFLICT`.

## Trace cleanup

Every five seconds, the loop checks one page of at most 1,000 objects against
the workspace's archive state and deletes content only for archived or deleted
workspaces. Active workspaces are skipped. S3 lifecycle handles normal expiry
using each batch's retention tag. Changing workspace retention affects new
captures only. Cleanup retries failures and revisits prefixes for late writes.

## Failures

A rejected stream entry stays pending. Valid entries that the same read
delivered after it also stay pending. The trim keeps the rejected entry and all
later entries, and settlement stops at the rejected entry. An operator must
remove or repair the entry before ingestion and settlement continue.

If a pending entry leaves the stream before ingestion, Valkey removes it from
the pending list when the loop reclaims it. That generation is not ingested or
billed. The loop logs `generation_entry_deleted` and increments
`gradiated_worker_ingestion_deleted_messages_total`. Repair a poison entry in
place when you can. Delete it only when its generation must not be billed.

A rejected slot stops settlement at that slot. Each failure logs
`worker_loop_failed` with a bounded `error_code`. The loop then restarts with
a backoff that doubles up to 30 seconds. The backoff resets after an attempt
that ran for at least one minute.

## Operation

Deployment reconciliation reads GPU Kubernetes pods using the worker
ServiceAccount. It verifies model process incarnations through the production
SDK before marking them Ready and projecting serving endpoints. No scheduler
certificate issuance, renewal or ACL token is involved.

Each loop writes a readiness file when it is ready and removes it when it
fails or stops:

- `/tmp/gradiated-generation-ingestion-ready`
- `/tmp/gradiated-settlement-ready`

The worker serves Prometheus metrics on `GET /metrics` at `METRICS_PORT`
(default 9464). It exposes no other HTTP service.

## Stream contract

The worker reads `generation-settled:{settlement-0}`. Each stream entry must
have exactly these two fields:

- `generation_id`: the generation UUID.
- `properties`: the JSON form of `GenerationProperties` without `settlement`.

The worker derives `settlement.slot_id` from the stream entry ID. It rejects an
entry that has missing fields, additional fields, or an invalid properties
document. It also rejects an entry whose component amounts do not equal
quantity multiplied by unit price, or whose charge does not equal the sum of
the component amounts. It does not acknowledge a rejected entry.

## Tests

`pnpm check` starts a disposable local Valkey container for the ingestion
integration tests. Set `WORKER_TEST_VALKEY_URL` to use a local Valkey instead.

## Public inference monitoring

`INFERENCE_PROBE_BASE_URL` enables real inference checks through the public API.
The existing verification workspace and user issue short-lived API keys that are
rotated automatically and revoked on shutdown. Keys and response bodies are not
logged. One worker holds a fifteen-second Valkey lease; standby workers take over
when it expires. This runs independently of settlement leadership.

Every five seconds the leader discovers available catalog models and deployment
rows independently. Every available catalog model gets a request through normal
gateway routing, including OpenRouter fallback when it has no local replicas.
Decision models use System One based on their catalog type. Models marked
unavailable or retired are excluded. Scaling to zero removes deployment targets
while retaining model requests and their alert metrics.
Every worker also reads the available catalog during metrics scrapes, independently
of probe leadership. The monitoring watchdog compares that inventory with the
leader's routed targets and success gauges, so an older leader cannot silently
omit zero-replica models. Missing catalog telemetry also alerts during a rollback.

After the routed model requests complete, the leader probes each available
deployment once per minute, staggered across passes, using the exact-deployment
verification header with fallback disabled. Chat requests use eight output tokens;
System One requests use a small classification. Valid responses identify a
generation and contain a completed inference result; targeted responses must
also acknowledge the deployment. Each phase has a four-second request deadline
and no retries. Canary and draining replicas are excluded from targeted probes;
rollout qualification still uses its separate SDK checks.

Prometheus scrapes workers and evaluates availability rules every five seconds.
An available model without successful routed inference for fifteen seconds alerts
after another minute. Targeted deployment failures alert after seventy-five
seconds without success, sustained for one minute. Stopped monitoring alerts
separately. Alertmanager waits
five seconds before notifying and groups notifications by model and deployment.
Incident.io then groups all occurrences of the same alert type in a fixed
30-minute window, regardless of deployment. This probes
the public serving path from EKS; it does not provide an independent external
monitoring vantage point or replace customer request availability measurements.
