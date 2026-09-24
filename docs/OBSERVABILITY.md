# Production observability

Prometheus, Grafana, Alertmanager, kube-state-metrics, node-exporter, and the
blackbox exporter are reconciled by Argo CD. Product scrape, dashboard, probe,
and alert resources live under
`infra/environments/prod/us-east-1/kubernetes/workloads/observability/`.
Application metrics contain no organization, workspace, API-key, generation,
prompt, or completion labels.

## Service coverage

| Service        | Signal source                          | Important signals                                                                                                                                                            | Dashboard                      |
| -------------- | -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------ |
| API            | private `:9464/metrics` Service port   | request rate/status/route, latency, in-flight work, sizes, exceptions, PostgreSQL/Valkey readiness, Node process/GC/event loop                                               | `Gradiated / API`              |
| Worker         | private `:9464/metrics` PodMonitor     | loop up/ready/failures/restarts/progress, pass latency, ingestion throughput/backlog/age, settlement lag, Node process/GC/event loop                | `Gradiated / Worker`           |
| Gateway        | private in-cluster `/metrics`          | request outcomes, admission/rejection, active and terminal generations, tokens/charges, dispatch/runtime/TTFT/TPOT/throughput, finalization, Valkey/catalog readiness | `Gradiated / Gateway`          |
| Proxy          | private admin `:9003/metrics`          | responses by destination and status, upstream header latency, in-flight requests, identity lookups (fresh, loaded, stale, unavailable), database queries, hosted catalog age and refresh failures | `Gradiated / Proxy`            |
| SGLang runtime | gateway deployment-scoped observations | active work, terminal outcomes, runtime latency, TTFT, TPOT, per-request output throughput                                                                        | `Gradiated / SGLang Runtime`   |
| Console        | external HTTPS blackbox probe          | end-to-end availability, HTTP status, DNS/TLS/request phases, response size, certificate expiry                                                                              | `Gradiated / Console`          |
| Metabase       | private metrics plus HTTPS probe       | end-to-end availability, replica state, restarts, CPU, memory, JVM heap and application metrics                                                                               | `Gradiated / Metabase`         |
| Whole product  | all sources plus kube-state-metrics    | endpoint/service health, traffic, generation outcomes, pipeline lag, alerts, desired/available replicas                                                                      | `Gradiated / Service Overview` |

The API and worker metrics listeners are not attached to an HTTPRoute. The
gateway public route accepts only inference paths. Its health and metrics
routes remain private even though they share the in-cluster HTTP port. The proxy
serves health, readiness and metrics on a separate admin port, which no route
reaches.

## Dashboards and diagnostic logs

Gateway and runtime dashboards filter by model and deployment and show input,
cached-input, cache-write, output and reasoning tokens, token sizes, input cache
hit ratio, TTFT, latency, throughput and active generations. Cached input is a
subset of input; reasoning is a subset of output. Do not sum overlapping token
categories. Range totals use Prometheus counter estimates, not billing records.
Idle periods show no observation rather than a fabricated successful rate.

Service dashboards link to Production Logs with service and time filters. The
Correlation ID field accepts a request or generation UUID; correlation stays in
the log body, never a metric or indexed Loki label. API/worker diagnostics use
structured levels, stable event names, error codes and stack locations; omit raw
exception messages, request bodies, query strings, headers and customer names/emails.
API logs authenticated request completions, failed/slow requests (>1s), dependency transitions and lifecycle;
worker logs loop lifecycle/failures. Tenant correlation uses organization, workspace and non-secret API-key UUIDs.
Gateway request spans obtain these from verified credentials and propagate them
through background generation/streaming tasks, including rejection and finalization
logs. Invalid credentials have no attributed tenant. API request logs carry the
session user's UUID and requested route resource UUIDs (plus newly created
workspace/API-key IDs from service results) with
`context_source=authenticated_session_requested_resource`; those target IDs do
not assert permission was granted. Infrastructure and batch-level worker events
have no invented tenant identity. No raw key, credential digest, prompt or response
body is added. Production Logs has service, organization, workspace, API-key ID,
and user-ID filters plus request/generation correlation. Resource filters accept
UUIDs or regex (`.*` means all); Grafana parses JSON fields/spans at query time,
without adding high-cardinality Loki or Prometheus labels.

API/worker log budgets are ten events/second per severity per process, so normal request volume cannot consume the error budget,
with suppressed counts on the next emitted event of that severity; metrics remain
unsampled. Gateway terminal events include generation UUID, token categories,
outcome and timing, before billing finalization. Finalization errors are separate.

Loki has verified EKS collection; external Runpod runtime collection is not yet
connected. The runtime dashboard links to gateway diagnostics and must not be
interpreted as proof that GPU/engine logs or engine-internal metrics are present.

## Alert coverage

The `gradiated-services` PrometheusRule covers:

- missing telemetry for each server-side process;
- sustained public DNS, TLS, CDN/ALB, and application availability failures,
  plus missing probe results for API, console, and Metabase;
- PostgreSQL, Valkey, and catalog readiness failures;
- API/gateway error ratios and latency regressions;
- worker crashes, readiness loss, pass stalls, poison-event
  age, and settlement lag;
- generation failures, finalization uncertainty, settlement backpressure, and
  generation ownership stalls;
- complete loss of available API, worker, or gateway replicas;
- public certificate expiry;
- Metabase endpoint and complete replica loss (warning severity).

Critical alerts repeat every 15 minutes; warnings repeat every two hours.
Alertmanager groups by alert, namespace, service, and severity and sends firing and
resolved events to the configured incident webhook. Populate the externally
managed `gradiated/prod/platform/alertmanager-notifications` AWS Secrets
Manager value with JSON containing `webhook-url` and `webhook-token`.
Alertmanager reads the token as a Bearer credential. The URL and token must
never enter Git.

`InfoInhibitor` is disabled. It is an upstream helper for suppressing standalone
informational alerts, not a service failure. `Watchdog`, `InfoInhibitor`, and
`info`/`none` severity alerts go to a null receiver. Unknown severities retain
the incident receiver so a mislabeled failure is not silently discarded.
Fast API/gateway outage pages suppress their slower service-wide ratio pages.
Same-alert critical/warning inhibition is scoped to the affected resource. Alert runbook links
and local alert runbook procedures are omitted. Product and logging alerts carry
a `logs_url`, a `dashboard_url` and a `panel_url` linking to the relevant provisioned Grafana
dashboard and diagnostic chart. Every new alert must include a relevant chart
on its service dashboard, show its underlying signal and threshold/window, and
link directly to that panel. Keep missing telemetry distinguishable from health.
The managed EKS control plane does not expose controller manager or scheduler
targets. The chart disables alerts that require these targets.

Thresholds below are based on failure impact and configured service timing, not
on current traffic volume. They are operational defaults, not contractual SLOs.
Validate them with failure scenarios and service deadlines before using traffic
history to refine them.

## Alert selection

There are 40 custom alerts: 32 service alerts, five logging alerts and three
platform-controller warnings. Retain
alerts for customer impact, lost progress/data, billing integrity, lost telemetry,
or sustained loss of redundancy. Metabase failures are warnings because they
impact internal analytics rather than the customer serving path.

Removed custom alerts for log-volume budgets (25/40 GiB), 90% container memory,
restart counts, 250 ms event-loop lag, and 1,000 queued events. Those thresholds
were capacity/diagnostic heuristics or overlapped default Kubernetes alerts;
they did not establish an actionable service failure. Their diagnostic charts
remain. Backlog age, settlement lag, billing backpressure, customer latency,
crash-loop defaults, and complete replica loss retain failure coverage.

The generation-stall alert operates per deployment and handles an absent
completion counter, including a first generation that never completes. A
healthy deployment cannot mask another deployment with no terminal progress.
Partial replica loss is handled by the default Kubernetes rules rather than
also creating a custom critical alert. SGLang readiness is not emitted by the
current gateway; the runtime dashboard shows observed generation failures.

## Infrastructure and change coverage

The chart's default rules retain node readiness/resource pressure, volume
capacity, failed jobs, pod crash loops, unavailable replicas, stuck Deployment,
StatefulSet and DaemonSet rollouts, and generation mismatches. They also cover
Prometheus rule evaluation/scrape failures and Alertmanager delivery failures.
The `gradiated-logging` rules cover Loki replica loss, collector availability,
dropped logs, delivery retries, and propagation latency.
Healthy deployments do not create incidents; rollout failures and service
regressions do.

## Production thresholds

Times below exclude scrape/evaluation and notification batching (normally tens
of seconds). Range windows and `for` durations are not interchangeable.

| Failure | Threshold and confirmation | Reason |
| --- | --- | --- |
| Public API/console/Metabase outage | Failed probes continuously for 2m | Detect complete outages promptly while tolerating isolated failed probes. Metabase remains warning. |
| No serving replicas | Zero available for 2m with desired replicas >0 | A complete service outage should not wait for rollout diagnostics. |
| Missing service/probe telemetry | No samples for 2m, then 1m confirmation | Roughly 3m of blindness; independent of customer traffic. |
| Dependency down | 2m | Tolerates brief reconnects without concealing a sustained failure. |
| Sustained API / gateway / generation errors | >5% / >2% / >5%, for 5m | Persistent partial failure. Minimum rate gates prevent isolated samples from defining a service-wide incident. API health probes are excluded. |
| Severe API / gateway / generation errors | >=50% and >=5 failures over 2m, for 1m | Fast outage path without paging on one failed request; generation failures evaluated per deployment. |
| Worker loop down / unready / failing | 2m / 5m / >2 failures in 10m for 1m | Distinguishes outages, startup gates, and repeated supervisor failures. |
| Worker progress stalled | No successful pass for 3m, then 2m confirmation | Normal ingestion/settlement cycles are 5/10 seconds. Settlement checks only the leader. |
| No settlement leader | All instrumented workers report no leader for 2m | A live standby is not proof that billing is running. Gate on all workers reporting leadership to avoid false alerts during the initial mixed-version rollout. |
| Ingestion pending | Oldest pending event >5m for 1m | Far beyond the 30s reclaim interval; roughly 6m to detect a continuously aging pending event. |
| Eligible settlement backlog | >5m overdue for 2m | Lag excludes the five-minute slot duration and intentional ten-minute settlement delay. Only fully ingested, eligible slots count. Idle/caught-up passes report zero, even when the pass hit its batch limit. |
| Finalization failure / settlement backpressure | Last event within 5m or observed counter increase; no hold | Billing uncertainty and deliberate admission refusal are actionable immediately. Zero-initialized timestamp gauges detect the first event even without a prior counter scrape. |
| API latency / first token | p95 >1s / >10s for 10m | Sustained performance warnings, with traffic gates. These are not contractual SLOs. |
| Generation progress | Active work and no completions in 10m, for 5m, per deployment | Detects loss of terminal progress; not a per-request deadline monitor. |
| Certificate expiry | <14 days for 1h | Allows time to repair managed certificate renewal. |
| Loki / collectors | <2 ready Loki replicas for 5m (critical); unavailable collector for 5m (warning) | Sustained logging availability loss. |
| Dropped logs / retries / propagation | Any drops (warning); retries for 5m (warning); p95 propagation >30s for 5m (warning) | Ordinary log loss must be investigated, but a single dropped entry is not a customer-serving page. |

## Reliability coverage review

Scope: repository configuration, all loaded Prometheus alert groups and scrape
jobs, Kubernetes workload state, and read-only AWS RDS, cache, and CloudWatch
inventory in production/us-east-1. This is not a failover or restore exercise.
Measured checks found no alert evaluation errors; the monitoring, Kubernetes,
service and logging rule groups are loaded. No CloudWatch metric or composite
alarms were configured in this account/region. This does not establish the
absence of separate vendor-managed notifications outside the inspected systems.

| Area | Existing protection | Important remaining gap and next action |
| --- | --- | --- |
| Monitoring and notifications — highest priority | Prometheus/Alertmanager self-monitoring and notification-failure rules | Watchdog is discarded and both servers have one replica. A cluster/monitoring outage can disable its own alarm. Configure an independently hosted heartbeat receiver and verify missing-heartbeat paging and delivery end to end; then assess HA placement. |
| Customer serving — highest priority | Public API/console probes; gateway request, generation and dependency metrics | Probes originate inside EKS and do not authenticate or run inference. Add an external, bounded exact-model synthetic transaction validating authentication, first token, completion, and usage. It needs an authorized test account, spend limit and external scheduler. |
| Billing-integrity events | Immediate finalization/backpressure rules with first-event timestamp gauges; leader-aware worker progress and eligible backlog | Timestamp gauges cover first-sample events, but a process that dies before any subsequent scrape can still lose in-memory evidence. Durable billing records remain the accounting authority. |
| PostgreSQL and Valkey | App dependency checks; primary RDS is Multi-AZ, deletion-protected, has 35-day backups and recent restorable time; cache has seven-day snapshots | No CloudWatch alarms. Add routed alarms for RDS free storage/connections/CPU credits and database availability, plus Valkey throttling, storage usage and failed requests. Cache caps are 10 GB and 5,000 ECPU/s. Dependency health alone provides no capacity lead time. |
| ClickHouse / ingestion | Worker failures, pending age, eligible settlement backlog; Terraform specifies two replicas and daily backups retained seven days | No direct ClickHouse scrape target was present. Add query/insert failures, storage/resource saturation and backup freshness checks. Unread stream age is not measured; pending-only alerts cannot prove ingestion completeness. |
| Nomad / GPU runtimes | Three Nomad servers and Kubernetes replica/rollout checks; gateway observes generation outcomes | No Nomad or GPU/runtime scrape target was present. Add leader/quorum, unhealthy allocations, missing clients, GPU errors and runtime readiness per serving deployment. Nomad documentation also leaves snapshot/restore checks, certificate renewal and quorum alerts as follow-up. Pod readiness is not proof of runtime health or spare serving capacity. |
| Deployment, DNS, load balancers and secrets | Kubernetes defaults, public probes and direct controller scrapes. Three warnings cover Argo degraded/failed automatic reconciliation (15m), External Secret not ready (10m), and DNS last successful sync >10m for 5m. Controller dashboard includes ALB reconciliation failures/latency. | ALB target health and load-balancer-generated errors still need direct AWS telemetry; edge request metrics only see requests that reach the gateway. Manual-sync application drift is intentionally excluded. |
| Recovery | RDS/Valkey backup retention configured; ClickHouse backup policy in Terraform | Backup policy is not restore proof. Verify backup freshness and perform bounded restore/failover exercises with measured recovery time and data loss. Do not claim these were tested by this alert review. |
| Internal analytics | Metabase endpoint and replica warnings; its RDS has backups and deletion protection | Metabase RDS and application are single-instance; accept that recovery tradeoff explicitly or add redundancy. |

Traffic gates intentionally ignore sparse individual failures, so the independent
synthetic transaction is essential even before traffic grows. Aggregate latency
and sustained-error rules can hide a single model regression; severe generation
failures are per deployment. The generation-stall rule can miss one stuck request
while others complete; an oldest-active-request/deadline metric is still needed.
No automatic external provisioning, test purchases/inference, destructive fault
injection, restore, or failover was performed during this review.

## Verification and access

Render desired state before reconciliation:

```sh
kubectl kustomize infra/environments/prod/us-east-1/kubernetes/workloads >/tmp/gradiated-workloads.yaml
```

After Argo reconciliation:

```sh
kubectl -n gradiated get servicemonitor,podmonitor,probe,prometheusrule
kubectl -n metabase get deployment,service,servicemonitor
kubectl -n observability port-forward svc/observability-grafana 3000:80
```

In Prometheus, confirm all API, worker, and gateway targets are up and all
three blackbox probes return `probe_success == 1`. In Alertmanager, use a temporary
non-production receiver test from the incident system; do not create a fake
production outage merely to test routing.

## Verification

Run the alert/dashboard checks (requires PyYAML and `promtool`):

```sh
python3 tools/observability/check.py
```

This validates panel links and PromQL, and exercises healthy, failed, recovered,
and missing probes, fast-error thresholds, replica outages, ingestion/settlement
delays, settlement leadership, and idle/stalled/progressing generations. Worker
unit tests validate eligibility accounting and leadership cleanup. Kubernetes CI
also runs `tools/observability/check_logs.py` against disposable localhost Loki
to verify the actual dashboard filters for flat API JSON, gateway spans,
unauthenticated events and unstructured logs. Fixtures never go to production.

After a change, run the product, Rust, Kubernetes, Helm, dashboard, PromQL,
Prometheus rule, Alertmanager, and DevEx checks that apply to the change.
Verify scrape targets, dashboard data, blackbox probes, and notification
delivery after Argo CD reconciliation. SGLang visibility is derived from the
gateway because the runtime is external to this cluster.
