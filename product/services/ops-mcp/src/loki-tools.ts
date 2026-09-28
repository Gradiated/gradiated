import { z } from "zod";

import type { Backend } from "./backend.js";
import { rangeParameters, timeRange } from "./time-range.js";
import type { RegisterReadTool } from "./tools.js";

const logql = z.string().min(1).max(2000);
const queryResult = z.object({
  status: z.string(),
  data: z.object({ resultType: z.string(), result: z.array(z.unknown()) }),
});

export const registerLokiTools = (
  register: RegisterReadTool,
  backend: Backend,
) => {
  register(
    "query_logs",
    [
      'Raw LogQL between two RFC 3339 datetimes, newest first. Metric queries such as sum by (level) (count_over_time({workload="api"}[5m])) also work.',
      'Stream labels: environment="prod"; cluster (eks-prod, or the GPU site for GPU hosts); namespace; workload (the Deployment, StatefulSet or DaemonSet name, such as api, gateway, proxy, collector, worker, ops-mcp, argocd-server; kubernetes-events for Kubernetes events; desmond on GPU hosts); container; job (namespace/container); level (as logged: TypeScript services use info/warn/error, Rust services use INFO/WARN/ERROR, so match with level=~"(?i)error"); __tenant_id__ (eks-prod or model-nebius-prod).',
      'TypeScript services log JSON with timestamp, service, level, event and error_code fields; filter with | json | event="worker_loop_failed". Rust services log JSON with fields.message and fields.error_code; | json flattens them to fields_message and fields_error_code.',
      "Use label_values source=logs to find workloads and log_fields to find parsed field names. The API and worker log only lifecycle events and failures, so an empty result can mean nothing happened; confirm with metrics.",
      "Results are truncated at limit; narrow the range or filter to see more. Never put credentials in a query.",
    ].join(" "),
    {
      query: logql,
      ...timeRange,
      limit: z.number().int().min(1).max(200).default(100),
    },
    async ({ query, limit, ...range }) =>
      queryResult.parse(
        await backend("loki", "/loki/api/v1/query_range", {
          query,
          ...rangeParameters(range),
          limit: String(limit),
          direction: "backward",
        }),
      ),
  );

  register(
    "log_fields",
    'Sample log lines that match a LogQL query between two RFC 3339 datetimes and list the fields Loki detects in them: name, type, cardinality and the parser (json or logfmt) that extracts each one. Use it before writing | json or | logfmt filters, for example query {workload="gateway"}. Nested JSON keys are flattened with underscores, as LogQL | json names them.',
    {
      query: logql,
      ...timeRange,
      line_limit: z.number().int().min(1).max(5000).default(1000),
    },
    ({ query, line_limit, ...range }) => {
      const { start, end } = rangeParameters(range);

      return backend("loki", "/loki/api/v1/detected_fields", {
        query,
        start,
        end,
        line_limit: String(line_limit),
      });
    },
  );
};
