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
| Gateway        | private in-cluster `/metrics`          | request outcomes, admission/rejection, active and terminal generations, tokens/charges, dispatch/runtime/TTFT/TPOT/throughput, finalization, Valkey/catalog readiness | `Gradiated / Gateway`          |
| SGLang runtime | gateway deployment-scoped observations | active work, terminal outcomes, runtime latency, TTFT, TPOT, per-request output throughput                                                                        | `Gradiated / SGLang Runtime`   |
| Console        | external HTTPS blackbox probe          | end-to-end availability, HTTP status, DNS/TLS/request phases, response size, certificate expiry                                                                              | `Gradiated / Console`          |
| Metabase       | private metrics plus HTTPS probe       | end-to-end availability, replica state, restarts, CPU, memory, JVM heap and application metrics                                                                               | `Gradiated / Metabase`         |
| Whole product  | all sources plus kube-state-metrics    | endpoint/service health, traffic, generation outcomes, pipeline lag, alerts, desired/available replicas                                                                      | `Gradiated / Service Overview` |

The API and worker metrics listeners are not attached to an HTTPRoute. The
gateway public route accepts only inference paths. Its health and metrics
routes remain private even though they share the in-cluster HTTP port.

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
Same-alert critical/warning inhibition is scoped to the affected resource. Alert runbook links
and local alert runbook procedures are omitted. Product and logging alerts carry
a `dashboard_url` and a `panel_url` linking to the relevant provisioned Grafana
dashboard and diagnostic chart. Every new alert must include a relevant chart
on its service dashboard, show its underlying signal and threshold/window, and
link directly to that panel. Keep missing telemetry distinguishable from health.
The managed EKS control plane does not expose controller manager or scheduler
targets. The chart disables alerts that require these targets.

Thresholds are launch defaults, not measured long-term SLOs. Review them after
the first seven days of representative traffic, retaining failure coverage
while adjusting only thresholds that have measured evidence.

## Alert selection

There are 33 custom alerts: 28 service alerts and five logging alerts. Retain
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

Coverage limits still requiring follow-up:

- Watchdog has no external heartbeat receiver. A complete monitoring/cluster
  outage cannot report itself through this stack.
- HTTPS probes run inside the cluster against public URLs; they do not prove
  reachability from an independent external location or execute real inference.
- Database, Valkey, ClickHouse, and SGLang failures are detected through service
  readiness or downstream progress/errors; dedicated capacity and GPU health
  coverage is not established by these rules.
- Error-ratio alerts have minimum traffic gates; isolated failures at low
  traffic may not alert. Per-model regressions can be hidden by aggregate rates.
- Configuration review does not establish live scrape health or notification
  delivery. Verify these after reconciliation; AWS SSO access is required.

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
and missing probes plus idle, stalled, and progressing generations.

After a change, run the product, Rust, Kubernetes, Helm, dashboard, PromQL,
Prometheus rule, Alertmanager, and DevEx checks that apply to the change.
Verify scrape targets, dashboard data, blackbox probes, and notification
delivery after Argo CD reconciliation. SGLang visibility is derived from the
gateway because the runtime is external to this cluster.
