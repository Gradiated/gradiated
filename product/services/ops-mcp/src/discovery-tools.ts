import { z } from "zod";

import type { Backend } from "./backend.js";
import { optionalRangeParameters, optionalTimeRange } from "./time-range.js";
import type { RegisterReadTool } from "./tools.js";

const source = z
  .enum(["metrics", "logs"])
  .describe("metrics queries Prometheus; logs queries Loki.");
const selector = z.string().min(1).max(2000);
const limit = z.number().int().min(1).max(1000).default(200);
const labelName = z.string().regex(/^[A-Za-z_][A-Za-z0-9_]*$/);

const listResponse = z.object({ data: z.array(z.unknown()).optional() });

const truncate = (response: unknown, count: number) => {
  const values = listResponse.parse(response).data ?? [];

  return {
    values: values.slice(0, count),
    total: values.length,
    truncated: values.length > count,
  };
};

const METRIC_LOOKBACK_MS = 60 * 60 * 1_000;

// Prometheus searches its whole retention when start is omitted, which lists
// every pod that ever existed; Loki already defaults to six hours.
const discoveryRange = (
  source: "metrics" | "logs",
  range: { start?: string | undefined; end?: string | undefined },
) => {
  if (source === "logs" || range.start) return optionalRangeParameters(range);

  const end = range.end ? Date.parse(range.end) : Date.now();

  return optionalRangeParameters({
    ...range,
    start: new Date(end - METRIC_LOOKBACK_MS).toISOString(),
  });
};

const selectorParameter = (
  system: "metrics" | "logs",
  value: string | undefined,
): Record<string, string> => {
  if (!value) return {};

  return system === "metrics" ? { "match[]": value } : { query: value };
};

export const registerDiscoveryTools = (
  register: RegisterReadTool,
  backend: Backend,
) => {
  register(
    "label_names",
    'List label names, to learn how series or log streams are labelled before writing a query. selector narrows to matching series or streams, for example {job="gradiated/worker"} or {workload="gateway"}. Pass start and end (RFC 3339) for a past period; metrics default to the last hour and logs to the last 6 hours.',
    { source, selector: selector.optional(), ...optionalTimeRange, limit },
    async ({ source, selector, limit, ...range }) =>
      truncate(
        await backend(
          source === "metrics" ? "prometheus" : "loki",
          source === "metrics" ? "/api/v1/labels" : "/loki/api/v1/labels",
          {
            ...selectorParameter(source, selector),
            ...discoveryRange(source, range),
          },
        ),
        limit,
      ),
  );

  register(
    "label_values",
    'List the values of one label, to use exact values instead of guesses. Examples: name=__name__ with selector {__name__=~"gradiated_worker_.*"} lists metric names; name=workload with source=logs lists log workloads; name=loop with selector {__name__="gradiated_worker_loop_failures_total"} lists worker loops. Pass start and end (RFC 3339) for a past period; metrics default to the last hour and logs to the last 6 hours.',
    {
      source,
      name: labelName,
      selector: selector.optional(),
      ...optionalTimeRange,
      limit,
    },
    async ({ source, name, selector, limit, ...range }) =>
      truncate(
        await backend(
          source === "metrics" ? "prometheus" : "loki",
          source === "metrics"
            ? `/api/v1/label/${name}/values`
            : `/loki/api/v1/label/${name}/values`,
          {
            ...selectorParameter(source, selector),
            ...discoveryRange(source, range),
          },
        ),
        limit,
      ),
  );

  register(
    "series",
    'List the full label sets of series or log streams that match a selector, for example {__name__="up",job="api"} or {namespace="gradiated",workload="worker"}. Use it to confirm that data exists and to see every label before filtering or aggregating. Pass start and end (RFC 3339) for a past period; metrics default to the last hour and logs to the last 6 hours.',
    { source, selector, ...optionalTimeRange, limit },
    async ({ source, selector, limit, ...range }) =>
      truncate(
        await backend(
          source === "metrics" ? "prometheus" : "loki",
          source === "metrics" ? "/api/v1/series" : "/loki/api/v1/series",
          { "match[]": selector, ...discoveryRange(source, range) },
        ),
        limit,
      ),
  );
};
