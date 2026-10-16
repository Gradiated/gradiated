import { RE2JS } from "re2js";
import { z } from "zod";

import type { Backend } from "./backend.js";
import { rangeParameters, timeRange, toTimestamp } from "./time-range.js";
import type { RegisterReadTool } from "./tools.js";

const promql = z.string().min(1).max(2000);

const metadataResponse = z.object({
  data: z.record(
    z.string(),
    z.array(
      z.object({
        type: z.string(),
        help: z.string(),
        unit: z.string().optional(),
      }),
    ),
  ),
});

const targetsResponse = z.object({
  data: z.object({
    activeTargets: z.array(
      z.object({
        scrapePool: z.string(),
        scrapeUrl: z.string(),
        labels: z.record(z.string(), z.string()),
        health: z.string(),
        lastError: z.string(),
        lastScrape: z.string(),
        lastScrapeDuration: z.number(),
      }),
    ),
  }),
});

export const searchMetadata = (
  data: unknown,
  search: string | undefined,
  limit: number,
) => {
  const pattern = search
    ? RE2JS.compile(search, RE2JS.CASE_INSENSITIVE)
    : undefined;
  const matches = Object.entries(metadataResponse.parse(data).data)
    .flatMap(([name, entries]) =>
      entries.slice(0, 1).map((entry) => ({ name, ...entry })),
    )
    .filter(
      ({ name, help }) => !pattern || pattern.test(name) || pattern.test(help),
    )
    .sort((left, right) => left.name.localeCompare(right.name));

  return {
    metrics: matches.slice(0, limit),
    total_matches: matches.length,
    truncated: matches.length > limit,
  };
};

export const registerPrometheusTools = (
  register: RegisterReadTool,
  backend: Backend,
) => {
  register(
    "active_alerts",
    'Alerts that Prometheus rules are firing or pending now, with labels, annotations (summary, dashboard and log links) and activeAt. For past alerts, run query_metric_history on ALERTS{alertstate="firing"}. For silences and notification state, use alertmanager_alerts.',
    {},
    () => backend("prometheus", "/api/v1/alerts"),
  );

  register(
    "query_metrics",
    [
      "Instant PromQL query, evaluated now or at time (RFC 3339). Returns at most 200 series.",
      "Do not guess metric or label names: find them with metric_metadata, label_values and series first.",
      "Conventions: Gradiated services export gradiated_* metrics with a service label (api, gateway, proxy, collector, worker). Counters end in _total, so wrap them in rate() or increase(). Histograms expose _bucket, _sum and _count: histogram_quantile(0.99, sum by (le) (rate(name_bucket[5m]))).",
      "Kubernetes object state is kube_* (kube-state-metrics; namespace, pod, deployment, container labels). Container CPU and memory are container_* (cAdvisor). EKS nodes are node_*. Synthetic probes are probe_* with job gradiated-*-synthetic. ALB metrics come from CloudWatch as aws_applicationelb_*. Scrape health is up{job=...}.",
      "To look back without a range query, use a subquery such as max_over_time(expr[3d:5m]) or the @ modifier. To find when something happened, max_over_time(timestamp(expr > 0)[3d:5m]).",
      "An empty result does not mean healthy: confirm the series exists with series, and check prometheus_targets for scrape failures.",
    ].join(" "),
    { query: promql, time: z.iso.datetime({ offset: true }).optional() },
    ({ query, time }) =>
      backend("prometheus", "/api/v1/query", {
        query,
        ...(time && { time: toTimestamp(time) }),
        timeout: "5s",
        limit: "200",
      }),
  );

  register(
    "query_metric_history",
    "PromQL range query between two RFC 3339 datetimes; returns at most 50 series. step_seconds defaults to about 121 points across the range; choose a larger step for long ranges and a smaller one to find exact onset times. Make range windows at least as long as the step, for example increase(x[30m]) with step_seconds 1800, or events between points are missed. Use the same conventions as query_metrics. Aggregate with sum by (...) to stay under the series limit.",
    { query: promql, ...timeRange },
    ({ query, ...range }) =>
      backend("prometheus", "/api/v1/query_range", {
        query,
        ...rangeParameters(range),
        timeout: "5s",
        limit: "50",
      }),
  );

  register(
    "metric_metadata",
    "Find metric names with their type (counter, gauge, histogram, summary), help text and unit. search is a case-insensitive RE2 regular expression over names and help text, for example 'worker.*fail', 'valkey' or '^kube_deployment'. Lookarounds and backreferences are unsupported; invalid expressions return a diagnostic error. Histograms and summaries are listed under their base name; query name_bucket, name_sum or name_count. Recording-rule outputs have no metadata; list them with label_values name=__name__.",
    {
      search: z.string().min(1).max(200).optional(),
      limit: z.number().int().min(1).max(500).default(100),
    },
    async ({ search, limit }) =>
      searchMetadata(
        await backend("prometheus", "/api/v1/metadata"),
        search,
        limit,
      ),
  );

  register(
    "prometheus_targets",
    "Scrape targets with health (up, down, unknown), last scrape time and duration, last error, scrape pool and target labels. Use it when a metric is missing, to tell a failed scrape from an idle service. Filter by health, job or scrape_pool.",
    {
      health: z.enum(["up", "down", "unknown"]).optional(),
      job: z.string().min(1).max(200).optional(),
      scrape_pool: z.string().min(1).max(200).optional(),
    },
    async ({ health, job, scrape_pool }) => {
      const response = await backend("prometheus", "/api/v1/targets", {
        state: "active",
        ...(scrape_pool && { scrapePool: scrape_pool }),
      });

      return {
        targets: targetsResponse
          .parse(response)
          .data.activeTargets.filter(
            (target) =>
              (!health || target.health === health) &&
              (!job || target.labels.job === job),
          ),
      };
    },
  );

  register(
    "prometheus_rules",
    "Alerting and recording rules: PromQL expression, for duration, labels, annotations, rule health, last evaluation error and time, and the alerts each rule holds now. Read an alert's rule before interpreting the alert; for example, a sum across pods fires differently from a per-pod expression. Filter by type, rule_name, rule_group or file.",
    {
      type: z.enum(["alert", "record"]).optional(),
      rule_name: z.array(z.string().min(1).max(200)).max(20).optional(),
      rule_group: z.array(z.string().min(1).max(200)).max(20).optional(),
      file: z.array(z.string().min(1).max(500)).max(20).optional(),
    },
    ({ type, rule_name, rule_group, file }) =>
      backend("prometheus", "/api/v1/rules", {
        ...(type && { type }),
        ...(rule_name && { "rule_name[]": rule_name }),
        ...(rule_group && { "rule_group[]": rule_group }),
        ...(file && { "file[]": file }),
      }),
  );
};
