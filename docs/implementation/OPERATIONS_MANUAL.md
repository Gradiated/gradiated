# Operations and incident manual

Status: canonical seed operations contract

This manual defines operating ownership and safe first responses. Concrete commands are added by the package that creates the service and must be exposed through `grad` or a reviewed runbook script. Operators never improvise ledger edits, delete provider resources without identity evidence or expose customer payload in tickets.

## 1. Operating principles

- Money, authorization, exact model identity and retention fail closed.
- Preserve evidence before repair, but never preserve plaintext payload outside its authorized store.
- Contain the smallest safe scope: request, key, workspace, organization, channel, release, cell or capacity source.
- Financial repair is append-only, idempotent, attributable and dry-run diffable.
- Unknown external mutation outcome is observed by stable identity before retry.
- Application rollback changes immutable pointers. Database migrations and Terraform state are forward-fixed.
- One incident commander owns timeline, authority, containment, reconciliation, customer/legal decision and follow-up.
- A provider/service failure is not permission to weaken billing, tenant or privacy guarantees.

## 2. Severity and ownership

| Severity | Examples | Response target | Required owner |
| --- | --- | --- | --- |
| SEV-0 | active cross-tenant payload exposure, uncontrolled financial loss, signing/supply-chain compromise | immediate page and global containment | incident commander + security + founder/legal |
| SEV-1 | admission without reserve, ledger mismatch, Valkey acknowledged-write uncertainty, broad auth bypass, provider resource leak with ongoing spend | immediate page | service owner + finance/security as relevant |
| SEV-2 | material partial outage, posting lag near retention, trace delete miss, Grad release unavailable, cleanup uncertainty isolated to source | on-call response | service owner |
| SEV-3 | degraded noncritical UI/analytics/research, optional provider probe failure | business-hours issue | workstream owner |

Customer payload detail is not copied into the incident timeline. Reference opaque request/trace IDs and use the authorized trace-access path only when the incident role permits it.

## 3. Standard incident sequence

1. Declare severity, commander, start time and affected authority scope.
2. Freeze unsafe mutation/admission/acquisition using the narrow documented switch.
3. Capture content-safe versions, offsets, lease epochs, counts, digests and dependency health.
4. Preserve immutable financial/provider/audit evidence; do not rotate/delete it prematurely.
5. Diagnose from authority outward: PostgreSQL truth, Valkey projection/reservation, consumer state, external observation.
6. Choose forward repair or immutable pointer rollback.
7. Reconcile invariants before reopening.
8. Observe through one full lease/stream/request/rollout window.
9. Record customer/legal/accounting impact and create follow-up issue.

For a customer-impacting incident, the commander assigns one communications owner. That owner updates the public status surface with payload-free scope and timestamps, uses the published support/security channel, preserves any contractual notification deadline and posts resolution only after authority reconciliation. Internal dashboards/issues are not the public status system.

## 4. Service ownership and health

| Service | Readiness means | Liveness means | Primary owner |
| --- | --- | --- | --- |
| control API | required config and PostgreSQL available; role-specific dependencies checked where command requires | event loop/process progresses | control |
| financial | PostgreSQL + Valkey stream reachable and consumer can claim/post | loop heartbeat progresses | billing |
| intelligence | PostgreSQL + trace stream + S3 write path available | loop heartbeat progresses | intelligence |
| trace-access | PostgreSQL + nonce + S3/KMS decrypt path available | process progresses | security/data |
| MCP | REST/OAuth metadata reachable | process progresses | control |
| gateway | Valkey qualified and scripts loaded; provider/router health does not globally gate readiness | process/accept loop progresses | serving |
| inference router | trust/config loaded and can accept gateway/cell connections | process progresses | owned inference |
| fleet | PostgreSQL lease operations and owned driver credentials available | reconcile heartbeat progresses | fleet |
| cell | exact bundle/runtime/topology and all required members ready | coordinator progresses | owned inference/provider |
| research worker | Temporal task queue and owned activity dependencies available | worker poll/heartbeat progresses | research |

Liveness must not restart a healthy process merely because an external dependency is unavailable. Readiness must not claim a role can safely accept work when its required authority is unavailable.

## 5. Required dashboards

### 5.1 Customer and serving

- requests, success/terminal class, actual model/release, stream/non-stream, TTFB/duration and cancellations;
- admission accepted/rejected by bounded reason, reserve/settle latency and reservation age;
- direct endpoint and owned-cell availability, attempts, pre-output retry and post-output failure;
- alias generation/canary assignment, session stability and rollback age.

### 5.2 Money

- organization/channel available/held/outstanding aggregates without customer-ID metric labels;
- billing stream length, pending/oldest age, consumer duplicates and poison events;
- usage posting and projection version lag;
- reconciliation differences, suspended accounts, Stripe webhook outcomes and failed-request credits;
- ledger imbalance must remain structurally impossible and page on any violated verification query.

### 5.3 Data and security

- trace capture/skipped status, bytes, stream lag/headroom, S3/KMS errors and delete backlog;
- grant denials/replay attempts, certificate enrollment/rotation/revocation and secret expiry;
- auth/RBAC denials by bounded class, key abuse and WAF/rate events;
- no prompt/completion/tool/cache content and no unbounded tenant/request labels.

### 5.4 Platform, fleet and research

- Aurora saturation/locks/failover/backups and bounded query latency;
- Valkey memory/noeviction/replication/durability/failover/script errors;
- pod/node/AZ readiness, KEDA fallback/max and GitOps drift;
- allocation/member lease, provider spend, ready/draining cells, interruption and cleanup uncertainty;
- Temporal queue/workflow/activity/replay, campaign budget and cleanup.

## 6. Runbook: Valkey unavailable or write certainty lost

Trigger: connection/script failures, failover with uncertain acknowledged writes, data loss alarm, noeviction/headroom breach or projection regression.

1. Stop new workspace and channel admission globally or for affected shards; do not fall back to PostgreSQL on the request path.
2. Keep gateway instances alive for safe terminal settlement attempts and evidence collection.
3. Record failover epoch, stream groups/pending entries, reservation counts/ages and latest published projection versions.
4. Restore/qualify Valkey health. Claim/post all durable billing events that remain.
5. Build a new projection epoch from PostgreSQL ledger/catalog/policy.
6. Add conservative holds for reservations whose terminal effect cannot yet be proven.
7. Compare account balances, limits, release digests, streams and uncertain holds.
8. Atomically switch to the new epoch and reopen canary admission only after comparison passes.

Forbidden: clearing reservations, truncating billing stream, publishing ledger balance without uncertain holds or treating Valkey as a disposable cache.

## 7. Runbook: ledger, balance or usage mismatch

1. Suspend only affected organization/channel admission unless structural scope is unknown.
2. Snapshot content-safe ledger transaction/entry IDs, balance version, usage IDs and stream event IDs.
3. Rebuild balance from entries and compare business keys/event receipts.
4. Classify duplicate, missing posting, projection error, over-reserve or external payment conflict.
5. Redeliver idempotent event or append a compensating transaction; never update old entries/usage.
6. Publish a higher snapshot version and rerun reconciliation.
7. Reopen only after equality and one observation window.

Any unexplained imbalance is SEV-1 and blocks broad projection rebuild from being trusted.

## 8. Runbook: billing stream lag, pending or poison event

1. Protect billing headroom by shedding/throttling trace capture first.
2. Scale financial consumers within PostgreSQL connection/write bounds.
3. Claim stale pending entries and inspect stable schema/error code without printing raw bytes.
4. For a valid event, fix reader compatibility and replay. For corrupt/conflicting identity, preserve bytes in restricted incident storage and suspend affected account.
5. Never acknowledge an unposted financial event only to reduce lag.

## 9. Runbook: Stripe outage, duplicate or chargeback

- Checkout creation failure leaves intent uncredited and retryable by idempotency key.
- Webhook outage queues at Stripe; restore endpoint and rely on event dedupe.
- Duplicate equal event returns success after existing effect is confirmed.
- Same object/identity with conflicting amount/organization suspends intent/account and pages.
- Refund/chargeback appends balanced transactions and updates account balance/status/admission; it does not create a separate risk profile or reopen/rewrite top-up history.

## 10. Runbook: provider or malformed stream failure

1. Confirm exact release/provider/model/endpoint and whether usable output was delivered.
2. Before output, allow only release-qualified retry within deadline and buy-risk budget.
3. After output, do not retry; terminate protocol consistently and settle metered use/credit policy once.
4. Quarantine endpoint/release if identity, usage or stream shape is impossible.
5. Preserve bounded attempt/error class, never provider body or customer payload.

Direct traffic must not switch provider/model. Grad traffic must not switch release/effort/speed.

## 11. Runbook: trace stream, S3 or KMS failure

1. Protect billing stream/memory first.
2. If encryption material is unavailable, emit a safe capture status and no plaintext envelope.
3. If persistence fails, retain bounded ciphertext in the trace stream only within its quota/retention; otherwise mark skipped and alert.
4. If decrypt/access anomaly occurs, revoke grants/keys, stop affected capture/read, preserve ciphertext/audit and page security.
5. A delete deadline miss disables new Product Intelligence capture for affected scope when necessary; serving may continue under no-retention only if policy is explicit and visible.

## 12. Runbook: organization deletion blocked

1. Keep organization admission and management mutation suspended.
2. Read the stable `last_error_code` and verify current deletion state/window.
3. For financial uncertainty, run organization reconciliation and settle/expire reservations before refund.
4. For Stripe refund uncertainty, observe external idempotency identity before retry.
5. For trace purge uncertainty, ensure wrapped key is revoked before repeating object-version deletion.
6. For session/key revocation failure, retry idempotently and test former access paths.
7. Mark completed only after every stage and pseudonymization verification; never cascade-delete required evidence prematurely.

## 13. Runbook: bad release or canary

1. Stop new canary assignment and record alias generation, release/qualification/bundle digests and gate signal.
2. Atomically point alias to prior active qualified digest.
3. Preserve in-flight admitted release identity and settle at admitted price.
4. Drain bad cells/endpoints without allowing cross-release cache reuse.
5. Reconcile customer impact, failed-request credits and evidence; qualification remains immutable and receives a new rejection/correction report rather than mutation.

## 14. Runbook: router or cell failure

- Router loss: direct traffic continues; owned traffic fails until another router is ready and cells reconnect/authenticate.
- Stale heartbeat/wrong attestation: remove cell immediately and revoke identity if compromise suspected.
- Required member loss: fence whole multi-node cell, stop assignment and drain/terminate; do not repair elastically in seed.
- Spot notice: stop new assignment, drain within deadline, preserve exact-release retry rules and let fleet replace capacity asynchronously.
- Cache is disposable: never delay safety drain to preserve cache state.

## 15. Runbook: provider lifecycle uncertainty or orphan

1. Freeze new acquisition for affected capacity source.
2. Fence driver lease epoch if ownership is uncertain.
3. List provider resources by stable Grad ownership/expiry tags using independent read credentials when available.
4. Match every SQL allocation/member to provider resource and every provider resource to SQL authority.
5. Observe unknown create identity before retry; delete only resources proven owned by the affected environment/source.
6. Confirm absence for every member/resource, update cleanup evidence and reopen source after a second clean sweep.

Do not remove SQL rows/final evidence to make the dashboard green.

## 16. Runbook: Temporal or research failure

1. Serving/release aliases remain unchanged.
2. Pause new campaigns/provider acquisition if workflow ownership or cleanup is uncertain.
3. Restore Temporal/worker and replay deterministic histories.
4. Reconcile workflow IDs against PostgreSQL run states and artifact refs.
5. Activities observe idempotency identity before repeating external mutation.
6. Preserve negative/failed evidence and prove GPU cleanup before resuming portfolio loop.

## 17. Runbook: Aurora loss and restore

1. Existing gateway traffic may continue only within valid Valkey snapshots/reservations; stop control mutation and financial acknowledgement without PostgreSQL.
2. Allow protected billing stream to queue within qualified capacity and page before retention/headroom risk.
3. Restore/fail over Aurora and verify schema/migration version.
4. Run tenant, ledger/balance, usage receipt, trace tombstone, fleet lease and research workflow reconciliation.
5. Resume financial consumers, then projection publishers/control API, then provider acquisition/research.
6. Never reconstruct financial authority from Valkey alone.

## 18. Runbook: EKS loss

1. Product data remains in managed stores; do not recover from etcd snapshots as business authority.
2. Recreate cluster/IAM/network integrations from Terraform, then Argo bootstrap and digest-pinned applications.
3. Verify Pod Identity and negative reachability before enabling public target groups.
4. Start financial/control/gateway/router/fleet/research in dependency-safe order.
5. Reconnect cells, reconcile streams/leases and run synthetic funded request before public reopen.

## 19. Credential and certificate rotation

| Credential | Rotation contract |
| --- | --- |
| workspace/channel key | create new display-once key, migrate caller, revoke old; no generic grace state |
| provider API secret | versioned secret ref, bounded dual-read where provider permits, test new, revoke old |
| Stripe webhook secret | provider-supported overlap with signature-version fixtures, then remove old |
| KMS/trace ingest key | new writes use new version; authorized old decrypt retained only through retention/delete contract |
| cell certificate | short-lived automatic renewal using current valid identity and allocation; compromise revokes and drains |
| signing/provenance key | keyless/purpose policy; compromise freezes promotion and re-verifies trusted digests |

Every rotation has synthetic rehearsal and audit. Secret values never appear in command lines, Git, Terraform plans saved as artifacts or issue comments.

## 20. Change and deployment operations

- Main reruns all affected checks from the exact commit.
- CI builds/signs once and GitOps promotes immutable digests.
- Database readers land before new writers; contract and Valkey epoch rollout follows compatibility order.
- Nonproduction low-risk Terraform may auto-apply; production/destructive plans require protected approval against a fresh plan.
- Never cancel Terraform apply, rewind state or apply a stale saved plan.
- Production canary has hard abort signal and prior digest/alias pointer ready before start.

## 21. Backup and drill schedule

| State | Protection | Minimum drill |
| --- | --- | --- |
| Aurora | Multi-AZ, PITR, snapshots | quarterly isolated restore plus ledger/tenant checks |
| Valkey | qualified Multi-AZ persistence | quarterly failover and conservative full rebuild |
| trace S3 | versioning/lifecycle/envelope keys | quarterly authorized decrypt and cryptographic delete |
| artifact S3/ECR | immutable/versioned/signed | reconstruct exact bundle/runtime by digest |
| Terraform state | versioned KMS S3/native locks | isolated version recovery and lock contention |
| Temporal | DB backup/retention | worker replay plus DB restore/reconciliation |
| EKS/Argo | Terraform + Git | full cluster/application rebuild |

Provider orphan sweeps and budget alarms run continuously. Certificate/secret/backup/dependency expiry checks run nightly and open/update GitHub issues.

## 22. Production readiness handoff

Each service owner supplies:

- dashboard and alert links/definitions;
- current SLO and last measured report;
- dependency/role/network matrix;
- deploy/rollback and schema compatibility window;
- top three incident runbooks with tested commands;
- backup/restore or rebuild evidence;
- capacity/cost limits and on-call escalation;
- known limitations and disabled catalog/features.

No service is “done” because it deploys. It is done when it can fail, alert, be contained, reconcile and recover without violating the product invariants.
