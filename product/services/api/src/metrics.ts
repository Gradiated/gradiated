import type { MiddlewareHandler } from "hono";
import { createServer, type Server } from "node:http";
import {
  collectDefaultMetrics,
  Counter,
  Gauge,
  Histogram,
  Registry,
} from "prom-client";

import { serviceLog, requestLogFields } from "./logging.js";
import type { ApiEnvironment } from "./types.js";

const durationBuckets = [
  0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10,
];
const sizeBuckets = [
  128, 512, 2_048, 8_192, 32_768, 131_072, 524_288, 2_097_152,
];

const normalizeRoute = (routePath: string | undefined): string =>
  routePath && routePath.length > 0 ? routePath : "unmatched";

const parseContentLength = (value: string | null): number | null => {
  if (!value) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : null;
};

export class ApiMetrics {
  readonly registry = new Registry();

  private readonly previousDependencies = new Map<string, string>();
  private readonly dependencyReady: Gauge<"dependency">;
  private readonly httpDuration: Histogram<"method" | "route" | "status_class">;
  private readonly httpExceptions: Counter<"method" | "route">;
  private readonly httpInFlight: Gauge<"method">;
  private readonly httpRequestSize: Histogram<"method" | "route">;
  private readonly httpRequests: Counter<"method" | "route" | "status">;
  private readonly httpResponseSize: Histogram<"method" | "route">;

  constructor(options: { collectProcessMetrics?: boolean } = {}) {
    this.registry.setDefaultLabels({ service: "api" });
    new Gauge({
      name: "gradiated_api_service_info",
      help: "Constant service identity metric used to detect missing API telemetry.",
      registers: [this.registry],
    }).set(1);
    this.httpRequests = new Counter({
      name: "gradiated_api_http_requests_total",
      help: "Completed API HTTP requests.",
      labelNames: ["method", "route", "status"],
      registers: [this.registry],
    });
    this.httpDuration = new Histogram({
      name: "gradiated_api_http_request_duration_seconds",
      help: "API HTTP request duration in seconds.",
      labelNames: ["method", "route", "status_class"],
      buckets: durationBuckets,
      registers: [this.registry],
    });
    this.httpInFlight = new Gauge({
      name: "gradiated_api_http_requests_in_flight",
      help: "API HTTP requests currently being handled.",
      labelNames: ["method"],
      registers: [this.registry],
    });
    this.httpExceptions = new Counter({
      name: "gradiated_api_http_exceptions_total",
      help: "Unhandled API request exceptions caught by the HTTP boundary.",
      labelNames: ["method", "route"],
      registers: [this.registry],
    });
    this.httpRequestSize = new Histogram({
      name: "gradiated_api_http_request_size_bytes",
      help: "API request Content-Length values when supplied by clients.",
      labelNames: ["method", "route"],
      buckets: sizeBuckets,
      registers: [this.registry],
    });
    this.httpResponseSize = new Histogram({
      name: "gradiated_api_http_response_size_bytes",
      help: "API response Content-Length values when known.",
      labelNames: ["method", "route"],
      buckets: sizeBuckets,
      registers: [this.registry],
    });
    this.dependencyReady = new Gauge({
      name: "gradiated_api_dependency_ready",
      help: "Whether an API dependency passed its latest readiness check.",
      labelNames: ["dependency"],
      registers: [this.registry],
    });

    if (options.collectProcessMetrics !== false) {
      collectDefaultMetrics({
        prefix: "gradiated_api_",
        register: this.registry,
      });
    }
  }

  readonly middleware: MiddlewareHandler<ApiEnvironment> = async (
    context,
    next,
  ) => {
    const method = context.req.method;
    const started = process.hrtime.bigint();
    this.httpInFlight.inc({ method });
    try {
      await next();
    } catch (error) {
      this.httpExceptions.inc({
        method,
        route: normalizeRoute(context.req.routePath),
      });
      throw error;
    } finally {
      const route = normalizeRoute(context.req.routePath);
      const status = String(context.res.status);
      const elapsedSeconds = Number(process.hrtime.bigint() - started) / 1e9;
      this.httpRequests.inc({ method, route, status });
      this.httpDuration.observe(
        { method, route, status_class: `${status[0] ?? "0"}xx` },
        elapsedSeconds,
      );
      this.httpInFlight.dec({ method });
      if (
        !route.startsWith("/health/") &&
        (context.get("user") || elapsedSeconds > 1 || Number(status) >= 400)
      ) {
        serviceLog(
          Number(status) >= 500
            ? "error"
            : Number(status) >= 400 || elapsedSeconds > 1
              ? "warn"
              : "info",
          "request_completed",
          {
            ...requestLogFields(context),
            method,
            route,
            status: Number(status),
            duration_ms: Math.round(elapsedSeconds * 1_000),
          },
        );
      }

      const requestSize = parseContentLength(
        context.req.header("content-length") ?? null,
      );
      if (requestSize !== null) {
        this.httpRequestSize.observe({ method, route }, requestSize);
      }
      const responseSize = parseContentLength(
        context.res.headers.get("content-length"),
      );
      if (responseSize !== null) {
        this.httpResponseSize.observe({ method, route }, responseSize);
      }
    }
  };

  recordDependencies(checks: Record<string, "up" | "down">): void {
    for (const [dependency, status] of Object.entries(checks)) {
      const previous = this.previousDependencies.get(dependency);
      if (
        previous !== status &&
        (previous !== undefined || status === "down")
      ) {
        serviceLog(
          status === "down" ? "error" : "info",
          status === "down" ? "dependency_down" : "dependency_recovered",
          { dependency },
        );
      }
      this.previousDependencies.set(dependency, status);
      this.dependencyReady.set({ dependency }, status === "up" ? 1 : 0);
    }
  }

  async render(): Promise<string> {
    return this.registry.metrics();
  }
}

export const startApiMetricsServer = (
  metrics: ApiMetrics,
  hostname = "0.0.0.0",
  port = 9_464,
): Server => {
  const server = createServer((request, response) => {
    if (request.method !== "GET" || request.url !== "/metrics") {
      response.writeHead(404).end();
      return;
    }
    void metrics.render().then(
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
  server.listen(port, hostname);
  return server;
};
