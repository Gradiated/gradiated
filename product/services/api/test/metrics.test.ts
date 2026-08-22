import { describe, expect, it } from "vitest";

import { createApp } from "../src/app.js";
import { ApiMetrics } from "../src/metrics.js";

describe("API metrics", () => {
  it("records route templates, statuses, latency, and dependency health", async () => {
    const metrics = new ApiMetrics({ collectProcessMetrics: false });
    const app = createApp({
      checkDependencies: async () => ({ postgres: "up", valkey: "down" }),
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
});
