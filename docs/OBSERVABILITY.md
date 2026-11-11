# Production observability

Prometheus, Grafana, Alertmanager, kube-state-metrics, node-exporter, and the
blackbox exporter are reconciled by Argo CD. Product scrape, dashboard, probe,
and alert resources live under
`infra/environments/prod/us-east-1/kubernetes/workloads/observability/`.
Application metrics contain no organization, workspace, API-key, generation,
prompt, or completion labels.

Application metrics for API, gateway, proxy, collector, worker, and Temporal
worker are scraped every 5 seconds with a 5-second timeout. Canary analysis
queries Prometheus every 15 seconds after a 30-second initial delay; its
90-second error window normally contains about eighteen samples per series.
Infrastructure exporters and public probes keep their separate scrape cadences.

## Service coverage

| Service        | Signal source                          | Important signals                                                                                                                                                            | Dashboard                      |
| -------------- | -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------ |
| API            | private `:9464/metrics` Service port   | request rate/status/route, latency, in-flight work, sizes, exceptions, PostgreSQL/Valkey readiness, Node process/GC/event loop                                               | `Gradiated / API`              |
| Worker         | private `:9464/metrics` PodMonitor     | loop up/ready/failures/restarts/progress, pass latency, ingestion throughput/backlog/age, settlement lag, Node process/GC/event loop                | `Gradiated / Worker`           |
| Gateway        | private in-cluster `/metrics`          | request outcomes, admission/rejection, active and terminal generations, tokens/charges, dispatch/runtime/TTFT/TPOT/throughput, finalization, Valkey/catalog readiness, capacity fallbacks and OpenRouter upstream cost (`deployment="openrouter"`) | `Gradiated / Gateway`          |
| Proxy          | private admin `:9003/metrics`          | responses by destination and status, upstream header latency, in-flight requests, identity lookups (fresh, loaded, stale, unavailable), database queries, hosted catalog age and refresh failures | `Gradiated / Proxy`            |
| Collector      | private admin `:9004/metrics`          | contents accepted and rejected by reason, batches and bytes uploaded, upload failures, open streams, batch bytes on disk | `Gradiated / Collector`        |
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

The gateway emits `inference_body` events containing redacted JSON in the `body`
field. `stage` distinguishes the incoming client request, effective runtime request,
runtime response, client response/error and selected response frames; `http_status`
is included when known. Requests retain recognized API field names, nesting,
numeric/boolean operational settings and recognized control strings. Prompt/content fields, credentials, tool definitions
and arguments, schemas, metadata, token IDs, logprobs, media and other payload
containers are replaced by `[redacted]`. Unknown string values are redacted too. Request stages use a separate list of
request controls at exact permitted ancestor paths; retained field names must
use their canonical spelling. Retained enum strings and derived error hints require stage-specific full
paths as well. Response scalars also require exact protocol paths,
so metadata containers nested below payload data do not retain numeric content.
Response-shaped counters, timestamps, and validation metadata
in requests are redacted rather than treated as trusted response metadata.
Unrecognized field names become `_redacted_key_N`; their values are redacted,
including numeric/boolean values and nested containers. Opaque body IDs and unverified
model strings are redacted regardless of their apparent format; trusted request,
model and deployment correlation remains in the existing lifecycle telemetry.
Error messages are replaced with
a redaction marker and a derived reason category, never retained verbatim. These
categories are diagnostic hints, not authoritative validation codes.

Each diagnostic is bounded to 16 KiB of redacted JSON, 256 visited values, depth
12, 64 fields per object and 32 items per array. Original byte bodies larger than
1 MiB, invalid JSON and duplicate keys produce size/parse summaries without raw
content. Larger client requests that classify successfully still log their
redacted parsed envelope, without reparsing the raw body. Truncation is explicit.
Streaming logs first and terminal metadata plus a rejected frame, rather than
every token; public stream logging is capped
at eight frames. No full stream is buffered. Error-body reads for native/SystemOne
are limited to 64 KiB and 250ms so diagnostics cannot indefinitely delay a retry.
Raw HTTP headers and transport URLs are excluded; existing safe header telemetry
and authenticated request spans provide correlation. Stream warnings also carry
the stable protocol `diagnostic_code`. Logs retain the existing 30-day retention.

Loki has verified EKS collection; external Runpod runtime collection is not yet
connected. The runtime dashboard links to gateway diagnostics and must not be
interpreted as proof that GPU/engine logs or engine-internal metrics are present.

## Alert coverage

The `gradiated-services` PrometheusRule covers:

- missing telemetry for each server-side process;
- sustained public DNS, TLS, CDN/ALB, and application availability failures,
  plus missing probe results for API, console, and Metabase;
- bounded public inference probes for every serving deployment and separate
  monitoring-stalled detection;
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

`InferenceModelProbeFailed` measures normal customer routing: one request per
model every five seconds, with a fresh random opening prefix, the gateway's
normal selection and fallback, no SDK retries and a four-second deadline. It is
critical after fifteen seconds without success and one minute of continued
failure. This is a short-request availability check; long-prefill performance
needs separate measurements. Routed checks finish before targeted diagnostics
begin, so monitoring does not submit overlapping checks to a single-slot
replica. Each request has its own four-second deadline. The normal pass cadence
is five seconds; slow phases can extend a pass, bounded by twelve seconds
including discovery and both phases, within the fifteen-second leader lease.

Targeted probes exercise every serving replica once per sixty seconds with
fallback disabled, staggered across twelve five-second passes to avoid a fleet-wide
burst. Newly discovered replicas receive a slot within sixty seconds; retired
replicas leave the schedule. Failed attempts wait for their next scheduled slot,
without immediate retries. As with model checks, these are nominal cadences:
slow requests, discovery failures or leader failover can delay checks.
A struggling replica remains visible even when customer routing succeeds.
`InferenceDeploymentProbeFailed` allows seventy-five seconds since the last
success to cover the minute cadence, request deadline and scrape delay. It is a
warning after that condition persists for one minute: about two minutes and
fifteen seconds since the last success, allowing two minute-spaced attempts.
Newly discovered deployments receive the same grace before the warning timer
starts, so an unprobed replica does not warn early. Both alerts retain a
five-minute recovery hold to avoid flapping. Model alerts repeat every fifteen
minutes; replica warnings use the normal two-hour warning interval. The worker dashboard shows routed model
availability separately from targeted replica results.
`InferenceProbeMonitoringStalled` also pages if a serving model has no routed
target or success metric on the fresh probe leader, including during a worker
rollback. Stale gauges from the previous leader cannot satisfy that check.

The incident.io Alertmanager source pauses timeout resolution while an alert is
attached to an incident. Unattached alerts have a 48-hour timeout, longer than
the longest reminder interval (24 hours). Explicit resolved events
close recovered alerts promptly. The timeout must exceed all repeat intervals
plus their group interval; otherwise persistent failures falsely close and
reopen between reminders. The separate Watchdog heartbeat detects loss of the
notification pipeline within about ten minutes. Timer expiration is not evidence
of service recovery.

Incident.io groups alerts by type for a fixed 30-minute window starting with the
first alert. Alertmanager titles are rule names (for example,
`InferenceDeploymentProbeFailed`), so model, deployment and host labels do not
create separate incidents of that type within the group. All occurrences update
one Slack summary, and only a priority increase re-escalates. Different types
remain separate; a new occurrence after 30 minutes can create a new group. This is
native time-window grouping, not a calendar-day quota or an indefinite
one-open-incident constraint. Per-deployment alerts and their recovery behavior
remain intact. Separate failures of the same type inside the window can still
share a group and do not re-page at the same priority.

Gateway HTTP and terminal-generation counters distinguish normal routed traffic
from authorised deployment-pinned verification. Critical HTTP/generation failure
alerts, their panels and canary error checks exclude `traffic="verification"`;
persistent replica failures retain their probe warning. Normal routed availability
probes use customer routing and fallback and remain counted. Classification
requires the configured verification workspace and a valid target header after
authentication; a caller cannot suppress failure metrics by forging that header.
Older metrics without a traffic label remain included during mixed-version deployment.

`GatewayRuntimeFailures` requires more than 5% failed completed generations per
model and deployment over three minutes, at least 20 failures, sustained for
one minute. Capacity rejections (`error="capacity_exceeded"`) are excluded from
both the failure count and denominator, including in
`GatewaySevereGenerationFailures` and their dashboard panels. Cancelled
generations remain excluded from the runtime failure denominator. Terminal
records retain their original outcomes for accounting.

`GatewayCapacityRejections` is a separate warning when more than 5% of completed
or capacity-rejected inference requests encounter `capacity_exceeded` over five
minutes, with at least five rejections, sustained for one minute. The numerator
combines terminal capacity outcomes with routing capacity rejections; the
denominator combines all terminal generations with routing capacity rejections.
These are disjoint populations: routing rejections never admit a generation,
and terminal outcomes count once after retries. This includes capacity errors
emitted inside an HTTP 200 SSE stream as well as returned HTTP 429s. The ratio
is service-wide; model/deployment dashboard filters do not apply to this panel.
Authorised verification traffic and other rate limits (such as workspace
concurrency limits) are excluded. Routing rejection counters label verification
traffic separately; older counters without that label remain included during
mixed-version deployment.

Public inference probes use Gradiated's internal verification account and normal
billing admission. HTTP 402 across all probes can mean that this account exhausted
its prepaid credit; inspect its operational balance before diagnosing GPU failure.
The guarded, idempotent internal reserve-credit operation is documented in
[`tools/models/README.md`](../tools/models/README.md#internal-monitoring-billing).

For the same `gradiated` recovery job, `DatabaseRestoreVerificationFailed`
inhibits the generic `KubeJobFailed` warning. Other jobs and namespaces retain
their notifications, and the generic warning becomes eligible again if the
specific recovery alert stops firing. Both rules remain visible in Prometheus.

`GpuHostTelemetryStale` includes the virtual node identity and inhibits warning
notifications from `KubeNodeNotReady` and `KubeNodeUnreachable` for that same
GPU node. The host failure remains actionable through the specific alert; other
nodes and critical alerts retain their notifications.

`InfoInhibitor` is disabled. It is an upstream helper for suppressing standalone
informational alerts, not a service failure. `InfoInhibitor` and
`info`/`none` severity alerts go to a null receiver.

`Watchdog` always fires. Alertmanager re-sends it every one to two minutes to an
incident.io heartbeat alert source, which raises an Urgent alert when no ping
arrives for ten minutes. A Prometheus, Alertmanager, egress or cluster outage
therefore pages instead of silencing every alert. The `incident-io` Terraform
unit creates the heartbeat and writes its ping URL and token to
`gradiated/prod/platform/alertmanager-heartbeat`; the Alertmanager
ExternalSecret merges them into the same Secret as the incident webhook. A
heartbeat does not monitor until its first ping, so after changing this path
confirm in incident.io that pings arrive. To test paging, silence `Watchdog`
in Alertmanager for 15 minutes and expect a page within about ten. Unknown severities retain
the incident receiver so a mislabeled failure is not silently discarded.
For warning severity in the `gradiated` namespace, `KubeHpaMaxedOut`,
`AutoscalingLimited`, and `RequestPathAutoscalingLimited` also go to the null
receiver. Reaching a replica ceiling alone is capacity information, not evidence of service failure. These
alerts remain visible in Prometheus and Grafana. Autoscaling failures, service
errors/latency, worker backlog/stalls, and unavailable replicas still create
incidents; capacity warnings in other namespaces retain their normal routing.
`ApplicationReconciliationFailed` excludes `Missing` health for manually managed
applications, which can be staged before their first deployment. Degraded or
unknown health still creates incidents, as do missing resources or stalled sync
for automatically managed applications. Kubernetes and service alerts continue
to detect unavailable deployed workloads independently of Argo sync policy.
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
The `gradiated-data-stores` rules read RDS and Valkey CloudWatch metrics through
`cloudwatch-exporter`. They page when product database storage is nearly full or
Valkey evicts keys, and warn on connections, CPU, memory, and Valkey storage,
ECPU and throttling. `DataStoreMetricsMissing` warns if the metrics stop.
Healthy deployments do not create incidents; rollout failures and service
regressions do.

## Production thresholds

Times below exclude scrape/evaluation and notification batching (normally tens
of seconds). Range windows and `for` durations are not interchangeable.

| Failure | Threshold and confirmation | Reason |
| --- | --- | --- |
| Public API/console/Metabase outage | Failed probes continuously for 2m | Detect complete outages promptly while tolerating isolated failed probes. Metabase remains warning. |
| Public inference failure | No successful probe for >15s, then 10s confirmation | Per-deployment alerts retain diagnostics; the shared incident grouping policy combines occurrences of the same type. |
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
| Monitoring and notifications — highest priority | Prometheus/Alertmanager self-monitoring and notification-failure rules; Watchdog heartbeat to incident.io | Both servers have one replica. The heartbeat proves Alertmanager can reach incident.io, not that the incident webhook credential works. Assess HA placement and alert on webhook delivery failures. |
| Customer serving — highest priority | Public API/console probes; authenticated per-deployment inference probes; gateway request, generation and dependency metrics | Probes originate inside EKS. Inference probes validate authentication, completion and usage with a four-second deadline; they depend on the internal monitoring account. An independent external vantage point remains missing. |
| Billing-integrity events | Immediate finalization/backpressure rules with first-event timestamp gauges; leader-aware worker progress and eligible backlog | Timestamp gauges cover first-sample events, but a process that dies before any subsequent scrape can still lose in-memory evidence. Durable billing records remain the accounting authority. |
| PostgreSQL and Valkey | App dependency checks; primary RDS is Multi-AZ, deletion-protected, has 35-day backups and recent restorable time; cache has 30-day snapshots; `gradiated-data-stores` alerts on RDS storage, connections, CPU and memory, and on Valkey storage, ECPU, throttling and evictions | RDS failover and availability events are not routed. Connection thresholds assume the default `max_connections`. |
| ClickHouse / ingestion | Worker failures, pending age, eligible settlement backlog; Terraform specifies two replicas and daily backups retained 30 days | No direct ClickHouse scrape target was present. Add query/insert failures, storage/resource saturation and backup freshness checks. Unread stream age is not measured; pending-only alerts cannot prove ingestion completeness. |
| GPU runtimes | Kubernetes Node and Rollout health, SDK qualification, and gateway generation outcomes | Monitor desired versus ready capacity, Pending pods, controller availability and runtime failures. Pod process health alone is not serving qualification or spare capacity. |
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

## Security monitoring

Argo CD reconciles three open-source security tools from
`infra/environments/prod/us-east-1/kubernetes/platform/`. They support the SOC 2
vulnerability-management, preventive-control and intrusion-detection criteria.
Their alerts are in the `gradiated-security` PrometheusRule and the
`Gradiated / Security` dashboard. Kyverno and Falco dashboards are in the
Grafana `Security` folder.

| Tool | Namespace | What it does | Requested overhead |
| --- | --- | --- | --- |
| Trivy Operator 0.35 (chart 0.37.0) | `trivy-system` | Scans running images for CVEs and exposed secrets, and audits workload configuration, RBAC, node configuration and the EKS CIS, NSA and Pod Security compliance specs. Rescans every 24 hours, two scan jobs at a time. | Operator 50m/128Mi, Trivy server 100m/512Mi and a 5 GiB gp3 volume, scan jobs 100m/128Mi each while running |
| Kyverno 1.19 (chart 3.9.1) | `kyverno` | Four baseline `ValidatingPolicy` resources in **Audit** mode: no privileged containers, no host namespaces or hostPath, no `latest` or untagged images, CPU and memory requests required. Nothing is blocked. Webhooks fail open. | Admission controller 100m/256Mi, reports controller 50m/128Mi |
| Falco 0.45.1 (chart 9.2.0) | `falco` | Runtime intrusion detection on every EKS node with the modern eBPF probe in least-privileged mode and the pinned `falco-rules:5.2.0` default ruleset. Events at Notice and above go to Loki as JSON. | 20m/128Mi per node (16 nodes: 320m/2Gi), default priority so it never preempts workloads |

Falco uses the patched image from `infra/images/falco`, pinned by digest. Its
container plugin is baked into the image; the chart downloads only the pinned
rules artifact. CRI enrichment and the `/run/containerd` directory mount remain
enabled explicitly. `tools/security/check_falco.py` renders the chart and checks
that a plugin download or volume cannot replace or hide the patched library.

Scope limits:

- GPU model pods run on virtual-kubelet nodes backed by external hosts. Falco
  cannot run there, and Trivy skips the `gradiated/*-bundle` images because the
  cluster cannot pull them and they are tens of gigabytes. The Trivy node
  collector also skips `type=virtual-kubelet` nodes. GPU workload configuration
  is still audited by Trivy and Kyverno.
- Trivy scan jobs read private ECR images through the
  `gradiated-prod-trivy-operator` Pod Identity role in the `platform-iam`
  Terraform unit. Apply that unit before or with this change; without it, ECR
  images report scan failures while public images still scan.
- Unfixed CVEs remain in the reports but do not alert.

Kyverno policies live in
`infra/environments/prod/us-east-1/kubernetes/kyverno-policies/`. Exclusions,
taken from the manifests and live workloads:

| Policy | Excluded |
| --- | --- |
| All | `kube-system` (VPC CNI, network policy agent, kube-proxy, EBS CSI, Pod Identity agent, CoreDNS), `kube-public`, `kube-node-lease`, `kyverno` |
| Privileged containers | `falco`; `tailscale-inference`, whose kernel-mode proxies need privileges |
| Host namespaces and hostPath | `falco`; `trivy-system` (node collector); the node-exporter and `alloy-logs` DaemonSets and their pods in `observability`, by a match condition on `app.kubernetes.io/name` and `app.kubernetes.io/instance` (an `objectSelector` exclusion does not apply in Kyverno 1.19 background scans) |

The first reports will include existing findings, for example containers in the
kube-prometheus-stack release that set no resource requests. Fix a finding or
add a commented exclusion before moving any policy to `Deny`.

Falco tuning, in `customRules` of `platform/falco.yaml`; no rule is disabled and
no critical-priority rule is changed:

- `Contact K8S API Server From Container` ignores controllers in `argocd`,
  `tailscale-inference`, `keda`, `external-secrets`, `kyverno`, `trivy-system`,
  `falco`, `observability` and `gpu-inference`, and the product `worker` and
  `temporal-worker` containers, which manage GPU model deployments. Other product
  pods still report.
- `Packet socket created in container` ignores `tailscaled`, which opens an
  AF_PACKET socket for NAT traversal in kernel mode.
- The minimum output priority is Notice, which drops the Informational
  `System user interactive` rule.
- Rules update only when the pinned ruleset changes in Git; weekly automatic
  rule downloads are off.

Review the Falco Loki stream after rollout and add exceptions in the same file.

| Alert | Condition | Severity |
| --- | --- | --- |
| `VulnerabilityCriticalOverdue` | A fixable Critical CVE in an image repository running in a namespace was also present 7–8 days ago, for 1h | warning (In-hours) |
| `VulnerabilityHighOverdue` | The same for a fixable High CVE and 30–31 days | warning (In-hours) |
| `TrivyOperatorNotReporting` | Operator unscraped, or no vulnerability reports exported, for 1h | warning (In-hours) |
| `AwsRootAccountUsed` | CloudTrail root-use metric is positive in a window of 14–15 minutes ending two minutes ago | critical (Urgent) |
| `AwsRootUsageMonitoringMissing` | Root-use metric absent for 30m | warning (In-hours) |
| `FalcoCriticalEvents` | Any Emergency, Alert or Critical Falco rule match in the last 10 minutes | critical (Urgent) |
| `FalcoDown` | A Falco sensor unavailable or unscraped, or the DaemonSet or its scrape targets missing, for 10m | warning (In-hours) |
| `KyvernoPolicyViolationsRising` | A namespace's audited failure count exceeds its count a day earlier for 1h | warning (In-hours) |

incident.io maps `critical` to Urgent and every other severity to In-hours.
Root-account activity and critical runtime detections page at night; vulnerability-remediation and sensor-health
warnings remain In-hours. Vulnerability
alerts repeat daily rather than every two hours. The SLA alerts key on image
repository and CVE, so redeploying the same vulnerable image does not restart
the clock. They need 7 or 30 days of metrics after installation before they can
fire. `KyvernoPolicyViolationsRising` reads per-report failure counts that
kube-state-metrics exports as `kube_policyreport_fail` and waits for a day of
history.

Root activity also pages through the existing Prometheus/Alertmanager integration,
so it does not depend on confirming SNS email subscriptions. The exporter reads
`Maximum` over a window of 14–15 minutes with a two-minute delay. The requested
range is 840 seconds and the aggregation period is 900 seconds, so rounding the
start down by up to a minute cannot introduce a newer partial period that masks
an earlier positive match. Repeated scrapes do not multiply events. CloudTrail delivery adds
latency. The missing-data warning distinguishes an unavailable signal from zero
root use, but quiet audit logs can also leave the metric empty. The Security
dashboard links directly to the CloudWatch audit log for investigation. This is
additional root-use coverage, not a replacement for SNS email confirmation or a
separate notification path for every GuardDuty/Inspector finding. It still depends
on the EKS monitoring stack and its existing incident.io integration.

High-severity GuardDuty finding events (7+) use In-hours review without paging
on-call. Inspector High and Critical static vulnerability events also use
In-hours review, including findings for retained images that are not deployed. This does not disable Inspector scanning,
its evidence stream, or the running-image vulnerability remediation-SLA alerts.

### Exporting SOC 2 evidence

Reports are Kubernetes resources; export them with read-only access and store
the files in the evidence system, not this repository:

```sh
stamp=$(date -u +%Y%m%dT%H%M%SZ)
kubectl get vulnerabilityreports -A -o json > "vulnerability-reports-$stamp.json"
kubectl get exposedsecretreports -A -o json > "exposed-secret-reports-$stamp.json"
kubectl get configauditreports,rbacassessmentreports -A -o json > "config-audit-reports-$stamp.json"
kubectl get clusterrbacassessmentreports,clusterinfraassessmentreports,clustercompliancereports -o json > "cluster-assessment-reports-$stamp.json"
kubectl get policyreports.wgpolicyk8s.io -A -o json > "kyverno-policy-reports-$stamp.json"
kubectl get validatingpolicies.policies.kyverno.io -o yaml > "kyverno-policies-$stamp.yaml"
```

Summaries for a control narrative:

```sh
kubectl get vulnerabilityreports -A -o json | jq -r '.items[] | [.metadata.namespace, .report.artifact.repository, .report.artifact.tag, .report.summary.criticalCount, .report.summary.highCount] | @tsv'
kubectl get clustercompliancereports -o json | jq -r '.items[] | [.metadata.name, .status.summary.passCount, .status.summary.failCount] | @tsv'
kubectl get policyreports.wgpolicyk8s.io -A -o json | jq -r '.items[] | .results[]? | select(.result == "fail") | [.policy, .resources[0].namespace, .resources[0].kind, .resources[0].name] | @tsv' | sort | uniq -c
```

Falco detections are in Loki (`{namespace="falco"}` in Production Logs). They
use the `platform` retention class, so Loki keeps them for 14 days; export them
within that window when an audit period needs the raw events. Alert history is
in incident.io.

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

Prometheus rule fixtures run in parallel suites containing their asserted alerts
and the transitive recording-rule dependencies used by each fixture. This avoids
re-evaluating unrelated rules for long simulated timelines. All fixtures still
run, and the complete generated rule file and dashboard coverage are validated
separately. Unknown alert references fail validation.


Render the pinned monitoring chart and test notification routing with Helm,
PyYAML, and `amtool`:

```sh
python3 tools/observability/check_platform.py
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

GPU serving uses Kubernetes health and per-process SDK qualification rather
than scheduler certificate-renewal metrics. Monitor missing Nodes, Pending pods,
failed Rollouts, controller availability and desired versus qualified capacity.
Verify both allowed private traffic and denied GPU-to-cluster destinations after
network changes; see the [Tailscale guide](../infra/modules/tailscale/README.md).

## Paging policy

Urgent paging has continuous 24-hour schedule coverage, including weekends. Warning
alerts still enter incident.io as In-hours and remain visible in dashboards and Slack;
they do not page the responder. The independent Watchdog heartbeat remains Urgent.
Root use and CloudTrail changes also retain their independent urgent CloudWatch route.

Non-security availability and error conditions must persist at least one minute.
The explicit immediate paging exceptions are root-account activity,
critical Falco detections and generation-finalization failure: these events can
require containment or billing-data recovery even after the triggering operation ends.
A persistence timer is not an event-count filter; settlement backpressure therefore
requires five rejections per minute sustained for a minute rather than keeping a
single rejection timestamp actionable for five minutes.

A healthy replica prevents a fleet-wide dependency or worker-loop-down page. One
OOM kill, per-pod retry failures, per-allocation loader telemetry, log-query latency,
lost redundancy and forecasted capacity pressure are warnings. Critical public
availability, severe request failures, stuck billing progress and actual near-full
storage remain enabled. Losing one Loki replica warns; losing all Loki replicas
for five minutes pages. Metabase database storage is warning-only, independently
of the product database storage page.

Duplicate inhibition is scoped: no-ready-replica suppresses the routed probe only
for the same model; severe generation failure suppresses the lower-ratio runtime
failure only for the same deployment; probe-monitoring loss suppresses only the
inference-probes worker-loop-down alert. Targets become eligible when their source
clears. Different models, deployments, other worker loops and security alerts are
not silenced by these rules. Native incident grouping remains a fixed thirty-minute
window per alert title, not a global paging quota.

The inventory below covers every rule name that was critical in the reviewed pinned
production rule set. Duplicate expressions for the same name (the two control-plane
burn windows and two Loki compactor cases) share the decision. Timing is the `for`
hold after the expression becomes true, not total detection latency. Expressions,
charts and their functional tests remain the source of truth; re-review this inventory
when adding a new critical rule or upgrading the monitoring charts.

| Reviewed alert | Severity | Hold | Decision |
| --- | --- | --- | --- |
| `AlertmanagerClusterCrashlooping` | warning | 300s | Restart instability is diagnostic while delivery succeeds; cluster loss and heartbeat failure still page. |
| `AlertmanagerClusterDown` | critical | 300s | Sustained loss of the Alertmanager cluster threatens paging; independent heartbeat also covers total pipeline loss. |
| `AlertmanagerClusterFailedToSendAlerts` | critical | 300s | All observed members fail the same integration persistently; actual alert delivery is impaired. |
| `AlertmanagerConfigInconsistent` | warning | 1200s | Replica configuration discrepancy is diagnostic; failed delivery still pages. |
| `AlertmanagerFailedReload` | warning | 600s | Last valid config remains in use; broken notification delivery has separate critical and external-heartbeat coverage. |
| `AlertmanagerMembersInconsistent` | warning | 900s | Cluster membership discrepancy is diagnostic; delivery and cluster failure remain critical. |
| `ApiDependencyDown` | critical | 2m | Require all observed API replicas to report the dependency unhealthy. |
| `ApiHighErrorRate` | critical | 5m | Sustained customer HTTP error ratio with a minimum request-volume guard; severe outages have a separate faster rule. |
| `ApiProbeMissing` | warning | 5m | Missing telemetry alone is diagnostic; independent public availability, deployment loss and external heartbeat retain pages. |
| `ApiPublicUnavailable` | critical | 2m | External HTTPS request path continuously fails for two minutes. |
| `ApiSevereErrors` | critical | 1m | At least half of requests/generations fail, with at least five failures, sustained one minute. |
| `ApiTelemetryMissing` | warning | 5m | Missing telemetry alone is diagnostic; independent public availability, deployment loss and external heartbeat retain pages. |
| `AwsRootAccountUsed` | critical | 0m | Immediate security event; required on-call response. |
| `AwsUrgentSecurityFinding` | warning | 0m | High-severity GuardDuty finding; In-hours review without paging. |
| `CacheEvictions` | critical | 1m | Valkey contains unsettled charges and leases; eviction risks billing-data loss. |
| `ConsoleProbeMissing` | warning | 5m | Missing telemetry alone is diagnostic; independent public availability, deployment loss and external heartbeat retain pages. |
| `ConsoleUnavailable` | critical | 2m | External HTTPS request path continuously fails for two minutes. |
| `ContainerOOMKilled` | warning | 0s | One restarted container can recover while other replicas serve; availability/error rules page real impact. |
| `DatabaseStorageLow` | critical | 15m | Product database write-loss risk; optional Metabase storage is a separate warning. |
| `DeploymentUnavailable` | critical | 2m | Zero available replicas of a required, enabled service for two minutes. |
| `FalcoCriticalEvents` | critical | 0m | Immediate critical runtime-security detection. |
| `GatewayDependencyDown` | critical | 2m | Require all observed gateway replicas to report the dependency unhealthy. |
| `GatewayFinalizationFailure` | critical | 0m | Immediate exception: usage, billing or lease finalization may have lost durable state. |
| `GatewayGenerationsStuck` | critical | 5m | Active work with no terminal generation for ten minutes, sustained another five minutes. |
| `GatewayHighErrorRate` | critical | 5m | Sustained customer HTTP error ratio with a minimum request-volume guard; severe outages have a separate faster rule. |
| `GatewayRuntimeFailures` | critical | 1m | More than 5% failed completed generations, at least 20 failures per three minutes, for one minute; capacity rejections, verification and cancellations excluded. |
| `GatewayCapacityRejections` | warning | 1m | More than 5% of completed or capacity-rejected inference requests encounter capacity_exceeded over five minutes, with at least five rejections; includes in-stream errors, excludes verification and other rate limits. |
| `GatewaySevereErrors` | critical | 1m | At least half of requests/generations fail, with at least five failures, sustained one minute. |
| `GatewaySevereGenerationFailures` | critical | 1m | At least half of generations fail, with at least five failures, sustained one minute; capacity rejections and verification excluded. |
| `GatewayTelemetryMissing` | warning | 5m | Missing telemetry alone is diagnostic; independent public availability, deployment loss and external heartbeat retain pages. |
| `GenerationIngestionStuck` | critical | 1m | Oldest pending ingestion work exceeds five minutes for one minute; billing record progress is blocked. |
| `InferenceModelProbeFailed` | critical | 1m | Routed success older than fifteen seconds must stay unhealthy for one minute; five-minute recovery hold. |
| `InferenceProbeMonitoringStalled` | critical | 1m | Monitoring must stay stale or incomplete for one minute; suppress duplicate probe-loop pages. |
| `KubeAPIDown` | critical | 900s | All API-server scrape targets disappear for fifteen minutes; sustained control-plane blindness/outage. |
| `KubeAPIErrorBudgetBurn` | critical | 120s | Retain both multi-window severe control-plane error-budget burn rules. |
| `KubeClientCertificateExpiration` | warning | 300s | One-day certificate warning gives time for daytime rotation; API downtime retains its critical rule. |
| `KubePersistentVolumeErrors` | warning | 300s | An individual Pending/Failed volume may be unused; deployment availability catches actual service loss. |
| `KubePersistentVolumeFillingUp` | critical | 60s | Less than 3% writable persistent storage remains for one minute; imminent durable-storage exhaustion. |
| `KubePersistentVolumeInodesFillingUp` | critical | 60s | Less than 3% writable persistent-volume inodes remain for one minute. |
| `KubeProxyDown` | critical | 900s | All kube-proxy scrape targets disappear for fifteen minutes; sustained cluster-network risk. |
| `KubeStateMetricsListErrors` | warning | 900s | Monitoring collector errors are daytime diagnostics; service and pipeline outage signals remain critical. |
| `KubeStateMetricsShardingMismatch` | warning | 900s | Monitoring collector configuration is a diagnostic, not proof of customer outage. |
| `KubeStateMetricsShardsMissing` | warning | 900s | Missing monitoring shards are a diagnostic, not proof of customer outage. |
| `KubeStateMetricsWatchErrors` | warning | 900s | Monitoring collector errors are daytime diagnostics; service and pipeline outage signals remain critical. |
| `KubeletClientCertificateExpiration` | warning | 0s | One-day certificate warning; node/control-plane outages remain covered. |
| `KubeletDown` | critical | 900s | No kubelet scrape succeeds across known nodes for fifteen minutes. |
| `KubeletServerCertificateExpiration` | warning | 0s | One-day certificate warning; node/control-plane outages remain covered. |
| `LokiCompactorHasNotSuccessfullyRunCompaction` | warning | 3600s | Delayed background compaction is daytime maintenance; storage exhaustion still pages. |
| `LokiRequestErrors` | critical | 900s | More than 10% Loki server errors sustained fifteen minutes; log service is materially failing. |
| `LokiRequestLatency` | warning | 900s | Slow log queries alone do not justify waking the production responder. |
| `LokiRequestPanics` | warning | 0s | A recovered individual panic is diagnostic; persistent request errors and zero replicas still page. |
| `LokiUnavailable` | critical | 5m | Page only when zero replicas remain; one surviving replica raises a redundancy warning. |
| `LoraLoaderUnavailable` | warning | 2m | Per-allocation scrape/loader diagnostic; customer errors and availability retain their pages. |
| `ModelNoReadyReplicas` | critical | 1m | Required model has no fresh healthy replica for one minute; suppress the duplicate routed-probe page. |
| `NodeFileDescriptorLimit` | warning | 900s | 90% descriptor use is capacity headroom, not demonstrated exhaustion or service failure. |
| `NodeFilesystemAlmostOutOfFiles` | critical | 3600s | Writable filesystem has less than 3% inodes for an hour. |
| `NodeFilesystemAlmostOutOfSpace` | critical | 1800s | Writable filesystem has less than 3% space for thirty minutes. |
| `NodeFilesystemFilesFillingUp` | warning | 3600s | Forecasted inode pressure is daytime work; actual less-than-3% capacity retains its page. |
| `NodeFilesystemSpaceFillingUp` | warning | 3600s | Forecasted filesystem pressure is daytime work; actual less-than-3% capacity retains its page. |
| `NodeRAIDDegraded` | warning | 900s | Loss of storage redundancy is daytime repair; actual storage exhaustion and customer failures still page. |
| `PrometheusBadConfig` | warning | 600s | Failed reload retains the previous valid config; alert evaluation and delivery failures retain pages. |
| `PrometheusErrorSendingAlertsToAnyAlertmanager` | critical | 900s | Every Alertmanager destination has sustained notification errors. |
| `PrometheusRemoteStorageFailures` | warning | 900s | Remote archival/export failures do not prove local scrape or alert evaluation failure. |
| `PrometheusRemoteWriteBehind` | warning | 900s | Delayed remote write is daytime investigation while local alerting operates. |
| `PrometheusRuleFailures` | critical | 900s | Repeated rule evaluation failures for fifteen minutes can blind required production alerts. |
| `PrometheusTargetSyncFailure` | warning | 300s | Discovery-sync errors can coexist with working scrapes; investigate during working hours. |
| `ProxyHighErrorRate` | critical | 2m | Sustained customer HTTP error ratio with a minimum request-volume guard; severe outages have a separate faster rule. |
| `ProxyProbeMissing` | warning | 5m | Missing telemetry alone is diagnostic; independent public availability, deployment loss and external heartbeat retain pages. |
| `ProxyPublicUnavailable` | critical | 2m | External HTTPS request path continuously fails for two minutes. |
| `ProxyTelemetryMissing` | warning | 5m | Missing telemetry alone is diagnostic; independent public availability and external heartbeat retain pages. |
| `PublicLoadBalancerErrors` | critical | 5m | At least five ELB errors and over 1% failed requests per reporting period for five minutes, rather than a small absolute count. |
| `SettlementBackpressure` | critical | 1m | At least five admission rejections per minute sustained for one minute; a recovered one-off does not page. |
| `SettlementLagging` | critical | 2m | Leader settlement lag exceeds five minutes for two minutes. |
| `SettlementLeaderMissing` | critical | 2m | No settlement leader across the observed worker fleet for two minutes. |
| `TemporalWorkerUnavailable` | critical | 5m | Enabled Temporal worker deployment has zero available replicas for five minutes. |
| `TopUpChargeStuckPending` | warning | 5m | An individual charge remaining pending is a payment-reconciliation diagnostic, not proof of fleet-wide downtime. |
| `WorkerLoopDown` | critical | 2m | No observed worker has the loop running for two minutes; probe-monitoring outage suppresses its duplicate. |
| `WorkerLoopFailing` | warning | 1m | Per-pod supervised retries can recover or have healthy neighbors; stalled progress remains critical. |
| `WorkerLoopStalled` | critical | 2m | No worker makes required loop progress for over three minutes, sustained another two minutes; settlement uses its leader. |
| `WorkerTelemetryMissing` | warning | 5m | Missing telemetry alone is diagnostic; independent public availability, deployment loss and external heartbeat retain pages. |
| `etcdDatabaseQuotaLowSpace` | critical | 600s | Datastore quota above 95% for ten minutes risks stopping control-plane writes. |
| `etcdGRPCRequestsSlow` | warning | 600s | Latency degradation without a demonstrated outage is daytime investigation. |
| `etcdHighFsyncDurations` | warning | 600s | Disk latency degradation is diagnostic; quorum, RPC failures and capacity remain critical. |
| `etcdHighNumberOfFailedGRPCRequests` | critical | 300s | More than 5% control-plane datastore RPC failures for five minutes. |
| `etcdInsufficientMembers` | critical | 180s | Insufficient members threaten control-plane quorum. |
| `etcdNoLeader` | critical | 60s | Control-plane datastore has no leader for one minute. |
