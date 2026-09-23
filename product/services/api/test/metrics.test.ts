import { afterEach, describe, expect, it, vi } from "vitest";

import {
  captureServiceLogs,
  createTestApp,
  dependencyDown,
  dependencyUp,
  failWith,
} from "./support.js";
import { ApiMetrics } from "../src/metrics.js";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("API metrics", () => {
  it("logs only dependency transitions", () => {
    const logs = captureServiceLogs();
    const metrics = new ApiMetrics({ collectProcessMetrics: false });

    for (const valkey of [
      dependencyUp,
      dependencyDown,
      dependencyDown,
      dependencyUp,
      dependencyUp,
    ]) {
      metrics.recordDependencies({ valkey });
    }

    expect(logs.events().map(({ event }) => event)).toEqual([
      "dependency_down",
      "dependency_recovered",
    ]);
  });

  it("records route templates, statuses, latency, and dependency health", async () => {
    captureServiceLogs();
    const metrics = new ApiMetrics({ collectProcessMetrics: false });
    const app = createTestApp({
      checkDependencies: async () => ({
        postgres: dependencyUp,
        valkey: dependencyDown,
      }),
      metrics,
    });

    expect((await app.request("/health/live")).status).toBe(200);
    expect((await app.request("/health/ready")).status).toBe(503);
    expect((await app.request("/does-not-exist")).status).toBe(404);

    const body = await metrics.render();
    expect(body).toContain('gradiated_api_service_info{service="api"} 1');
    expect(body).toContain('route="/health/live",status="200"');
    expect(body).toContain('route="/health/ready",status="503"');
    expect(body).toContain('route="/*",status="404"');
    expect(body).toContain("gradiated_api_http_request_duration_seconds_count");
    expect(body).toContain(
      'gradiated_api_dependency_ready{dependency="postgres",service="api"} 1',
    );
    expect(body).toContain(
      'gradiated_api_dependency_ready{dependency="valkey",service="api"} 0',
    );
    expect(body).not.toContain("request_id=");
  });

  it("counts a server error raised through the HTTP boundary as an exception", async () => {
    captureServiceLogs();
    const metrics = new ApiMetrics({ collectProcessMetrics: false });
    const app = createTestApp({
      metrics,
      services: {
        catalogBilling: { listModels: failWith(new Error("unexpected")) },
      },
    });

    expect((await app.request("/api/v1/models")).status).toBe(500);
    expect((await app.request("/api/v1/me")).status).toBe(401);

    const body = await metrics.render();
    expect(body).toContain(
      'gradiated_api_http_exceptions_total{method="GET",route="/api/v1/models",service="api"} 1',
    );
    expect(body).not.toContain(
      'gradiated_api_http_exceptions_total{method="GET",route="/api/v1/me"',
    );
  });
});
