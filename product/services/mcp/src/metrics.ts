import type { MiddlewareHandler } from "hono";
import { createServer, type Server } from "node:http";
import {
  collectDefaultMetrics,
  Counter,
  Gauge,
  Histogram,
  Registry,
} from "prom-client";

export type ToolOutcome = "success" | "rejected" | "failed";

export type AuthenticationResult =
  "accepted" | "missing" | "rejected" | "error";

export type McpMetrics = ReturnType<typeof createMcpMetrics>;

export const createMcpMetrics = ({
  collectProcessMetrics = true,
}: { collectProcessMetrics?: boolean } = {}) => {
  const registry = new Registry();
  const registers = [registry];

  registry.setDefaultLabels({ service: "mcp" });
  new Gauge({
    name: "gradiated_mcp_service_info",
    help: "Constant service identity metric used to detect missing MCP telemetry.",
    registers,
  }).set(1);

  const httpRequests = new Counter({
    name: "gradiated_mcp_http_requests_total",
    help: "Completed MCP HTTP requests.",
    labelNames: ["method", "route", "status"],
    registers,
  });
  const httpDuration = new Histogram({
    name: "gradiated_mcp_http_request_duration_seconds",
    help: "MCP HTTP request duration in seconds.",
    labelNames: ["method", "route", "status_class"],
    buckets: [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30],
    registers,
  });
  const httpInFlight = new Gauge({
    name: "gradiated_mcp_http_requests_in_flight",
    help: "MCP HTTP requests currently being handled.",
    labelNames: ["method"],
    registers,
  });
  const httpExceptions = new Counter({
    name: "gradiated_mcp_http_exceptions_total",
    help: "Unhandled MCP request exceptions caught by the HTTP boundary.",
    labelNames: ["method", "route"],
    registers,
  });
  const toolCalls = new Counter({
    name: "gradiated_mcp_tool_calls_total",
    help: "MCP tool calls by tool and outcome; rejected is a caller error, failed an upstream one.",
    labelNames: ["tool", "outcome"],
    registers,
  });
  const toolDuration = new Histogram({
    name: "gradiated_mcp_tool_call_duration_seconds",
    help: "MCP tool call duration in seconds.",
    labelNames: ["tool", "outcome"],
    buckets: [0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60],
    registers,
  });
  const authentications = new Counter({
    name: "gradiated_mcp_authentications_total",
    help: "MCP request authentications by result.",
    labelNames: ["result"],
    registers,
  });
  const cacheRequests = new Counter({
    name: "gradiated_mcp_credential_cache_requests_total",
    help: "Credential cache reads and failed writes by result.",
    labelNames: ["result"],
    registers,
  });
  const inferenceCredentials = new Counter({
    name: "gradiated_mcp_inference_credentials_total",
    help: "Inference keys obtained for OAuth connections, by result.",
    labelNames: ["result"],
    registers,
  });
  const dependencyReady = new Gauge({
    name: "gradiated_mcp_dependency_ready",
    help: "Whether an MCP dependency is connected.",
    labelNames: ["dependency"],
    registers,
  });

  if (collectProcessMetrics)
    collectDefaultMetrics({ prefix: "gradiated_mcp_", register: registry });

  const middleware: MiddlewareHandler = async (context, next) => {
    const method = context.req.method;
    const started = process.hrtime.bigint();

    httpInFlight.inc({ method });
    try {
      await next();
    } finally {
      httpInFlight.dec({ method });
    }

    const route = context.req.routePath || "unmatched";
    const status = String(context.res.status);

    httpRequests.inc({ method, route, status });
    httpDuration.observe(
      { method, route, status_class: `${status[0] ?? "0"}xx` },
      Number(process.hrtime.bigint() - started) / 1e9,
    );
    if (context.error && context.res.status >= 500)
      httpExceptions.inc({ method, route });
  };

  return {
    registry,
    middleware,
    toolCall: (tool: string, outcome: ToolOutcome, seconds: number) => {
      toolCalls.inc({ tool, outcome });
      toolDuration.observe({ tool, outcome }, seconds);
    },
    authentication: (result: AuthenticationResult) =>
      authentications.inc({ result }),
    cache: (result: "hit" | "miss" | "error") => cacheRequests.inc({ result }),
    inferenceCredential: (result: "minted" | "cached" | "failed") =>
      inferenceCredentials.inc({ result }),
    dependency: (dependency: "valkey", ready: boolean) =>
      dependencyReady.set({ dependency }, ready ? 1 : 0),
  };
};

export const startMetricsServer = (
  metrics: McpMetrics,
  hostname: string,
  port: number,
): Server => {
  const server = createServer((request, response) => {
    if (request.method !== "GET" || request.url !== "/metrics") {
      response.writeHead(404).end();
      return;
    }

    void metrics.registry.metrics().then(
      (body) => {
        response.writeHead(200, {
          "Content-Type": metrics.registry.contentType,
          "Content-Length": Buffer.byteLength(body),
        });
        response.end(body);
      },
      () => response.writeHead(500).end(),
    );
  });

  return server.listen(port, hostname);
};
