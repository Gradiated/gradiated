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
| Worker         | private `:9464/metrics` PodMonitor     | loop up/ready/failures/restarts/progress, pass latency, ingestion throughput/backlog/age, settlement lag, projected object counts, Node process/GC/event loop                | `Gradiated / Worker`           |
| Gateway        | private in-cluster `/metrics`          | request outcomes, admission/rejection, active and terminal generations, tokens/charges, dispatch/runtime/TTFT/TPOT/throughput, finalization, Valkey/catalog/SGLang readiness | `Gradiated / Gateway`          |
| SGLang runtime | gateway deployment-scoped observations | readiness, active work, terminal outcomes, runtime latency, TTFT, TPOT, per-request output throughput                                                                        | `Gradiated / SGLang Runtime`   |
| Console        | external HTTPS blackbox probe          | end-to-end availability, HTTP status, DNS/TLS/request phases, response size, certificate expiry                                                                              | `Gradiated / Console`          |
| Metabase       | private metrics plus HTTPS probe       | end-to-end availability, replica state, restarts, CPU, memory, JVM heap and application metrics                                                                               | `Gradiated / Metabase`         |
| Whole product  | all sources plus kube-state-metrics    | endpoint/service health, traffic, generation outcomes, pipeline lag, alerts, desired/available replicas                                                                      | `Gradiated / Service Overview` |

The API and worker metrics listeners are not attached to an HTTPRoute. The
gateway public route accepts only inference paths. Its health and metrics
routes remain private even though they share the in-cluster HTTP port.

## Alert coverage

The `gradiated-services` PrometheusRule covers:

- missing telemetry for each server-side process;
- public DNS, TLS, CDN/ALB, and application availability;
- PostgreSQL, Valkey, catalog, and SGLang readiness failures;
- API/gateway error ratios and latency regressions;
- worker crashes, readiness loss, pass stalls, ingestion backlog, poison-event
  age, and settlement lag;
- generation failures, finalization uncertainty, settlement backpressure, and
  generation ownership stalls;
- Node event-loop saturation, Kubernetes replica loss, restart loops, and
  memory pressure;
- public certificate expiry;
- Metabase endpoint, replica, restart, and memory failures.

Critical alerts repeat every 15 minutes; warnings repeat every two hours.
Alertmanager groups by alert, service, and severity and sends firing and
resolved events to the configured incident webhook. Populate the externally
managed `gradiated/prod/platform/alertmanager-notifications` AWS Secrets
Manager value with JSON containing `webhook-url` and `webhook-token`.
Alertmanager reads the token as a Bearer credential. The URL and token must
never enter Git.

The `Watchdog` alert goes to a null receiver. It does not create an incident.
The managed EKS control plane does not expose controller manager or scheduler
targets. The chart disables alerts that require these targets.

Thresholds are launch defaults, not measured long-term SLOs. Review them after
the first seven days of representative traffic, retaining failure coverage
while adjusting only thresholds that have measured evidence.

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

In Prometheus, confirm all API, worker, and gateway targets are up and both
blackbox probes return `probe_success == 1`. In Alertmanager, use a temporary
non-production receiver test from the incident system; do not create a fake
production outage merely to test routing.

## Verification

After a change, run the product, Rust, Kubernetes, Helm, dashboard, PromQL,
Prometheus rule, Alertmanager, and DevEx checks that apply to the change.
Verify scrape targets, dashboard data, blackbox probes, and notification
delivery after Argo CD reconciliation. SGLang visibility is derived from the
gateway because the runtime is external to this cluster.

## Telemetry missing

Check the Deployment/Pod first, then Prometheus Targets and the matching
ServiceMonitor or PodMonitor. From an authorized in-cluster debug pod, request
the metrics port directly. If the process is healthy but the target is absent,
inspect Prometheus Operator selector labels (`release: observability`) and
Operator events. Restore scraping before trusting other service alerts.

## Public endpoint down

Compare the blackbox probe phase metrics to local readiness. DNS failures point
to Route 53/ExternalDNS; TLS failures point to ACM/CloudFront/ALB; successful
DNS/TLS with an HTTP failure points to CloudFront/S3, Gateway API, target
registration, or application readiness. Do not bypass readiness or expose a
private metrics endpoint as a workaround.

## Dependency down

Use the `dependency` label to scope the incident. For PostgreSQL/Valkey, verify
managed-service health and network/IAM access. For `catalog`, validate the
projected model record. For `sglang`, check private connectivity, model pod
readiness, runtime authentication, and the exact deployment release. Keep the
gateway fail-closed behavior.

## High error rate

Break down status and stable error code by route. Correlate the start of the
increase with the immutable release metadata and dependency readiness. Roll
back a causally linked release through the normal deployment mechanism; do not
retry non-idempotent billing or inference operations manually.

## Latency regression

Separate API handler latency from gateway dispatch, runtime TTFT, runtime
duration, and TPOT. Rising dispatch latency implicates local tokenization or
admission; rising runtime TTFT/TPOT implicates SGLang capacity, GPU health, or
private networking. Compare by exact model and deployment before moving load.

## Process saturation

Check CPU, memory limit ratio, heap, GC, and event-loop lag together. Restarting
may provide temporary relief but does not correct a leak, blocking operation,
or under-sized limit. Preserve heap/profile evidence outside customer data and
adjust resources only after identifying whether the pressure is steady-state
or release-related.

## Worker loop failure

Use the `loop` label and pod logs. A loop is independently supervised, so
confirm whether only ingestion, settlement, or projection is affected. Fix the
specific dependency or invalid event and let the loop's bounded backoff recover;
do not restart healthy sibling loops unless the pod itself is unhealthy.

## Worker loop stalled

An up/ready loop with an old last-success timestamp is blocked inside a bounded
pass. Inspect operation latency and dependency calls, then compare with the
configured poll and timeout. Capture the blocking query/event before restarting
so the stall remains diagnosable.

## Ingestion backlog

Compare unread count, pending count, oldest-pending age, and ingestion rate. A
large unread count suggests throughput or ClickHouse availability; one old
pending event suggests a repeatable insert/schema problem. Preserve the stream
event ID and error, repair idempotently, and allow the consumer group to
acknowledge it. Never delete the settlement stream to clear the alert.

## Settlement lag

Confirm ClickHouse ingestion progress first, then settlement leadership,
eligible slot queries, organization existence, and PostgreSQL transaction
writes. Settlement is idempotent by source ID. Repair the failing dependency
and let the loop replay; do not synthesize balance transactions by hand.

## Generation failures

Group by exact model, deployment, stream mode, and stable error code. Check
SGLang health, overload, usage validity, deadlines, and private networking. Do
not add a silent model/provider fallback; drain or repair the explicit
deployment through the catalog/GitOps contract.

## Finalization failure

Treat any unconfirmed finalization as a billing-integrity incident. Preserve
the gateway logs and generation ID from logs (never as a metric label), inspect
the Valkey lease/account/stream atomically, and determine whether finalization
settled, returned `already_absent`, or remained unknown. Do not manually charge
or emit a second terminal event without proving the existing state.

## Settlement backpressure

The gateway has reached the configured safety bound and is deliberately
rejecting new inference. Follow the ingestion and settlement runbooks, verify
the stream lag is falling, and retain fail-closed admission until the backlog is
below the bound.

## Generation stall

Active leases without a terminal generation beyond the request deadline imply
lost ownership, runtime cancellation, or finalization failure. Inspect the
gateway task/drain state and SGLang request, then the lease expiry. Do not delete
live leases to restore capacity.

## Metabase

Check the `metabase` Deployment, both container logs, and the ExternalSecret
conditions. Then check the dedicated RDS instance and the shared Gateway route.
The metrics proxy must reach `127.0.0.1:9191` inside the pod. It must not expose
that port through a public route. If a data connection fails, test the matching
`metabase_reader` credential and its read-only grants. Do not give Metabase a
write-capable product credential.

## Certificate expiry

Identify the `instance`, then verify the authoritative ACM/CloudFront
certificate and DNS validation records. Renew or replace through Terraform and
the managed edge before changing any probe threshold.

## Pod health

Inspect rollout status, pod events, previous container logs, probe failures,
resource limits, and node health. Compare the running digest with the release
ConfigMap. Roll back through the immutable deployment workflow when the release
is causal; do not edit the live Deployment outside GitOps.
