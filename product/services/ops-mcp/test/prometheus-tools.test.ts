import { afterEach, describe, expect, it } from "vitest";

import { callTool, closeServers } from "./support/mcp.js";

afterEach(closeServers);

const metadata = {
  status: "success",
  data: {
    gradiated_worker_loop_failures_total: [
      { type: "counter", help: "Supervised worker loop failures.", unit: "" },
    ],
    up: [{ type: "gauge", help: "Scrape health.", unit: "" }],
    gradiated_worker_loop_up: [
      { type: "gauge", help: "Whether a loop is running.", unit: "" },
      { type: "gauge", help: "Duplicate from a second target.", unit: "" },
    ],
  },
};

const target = (job: string, health: string) => ({
  scrapePool: `serviceMonitor/${job}`,
  scrapeUrl: `http://${job}:9464/metrics`,
  labels: { job, instance: `${job}:9464` },
  discoveredLabels: { __meta_kubernetes_pod_annotation_secret: "PRIVATE" },
  health,
  lastError: health === "up" ? "" : "connection refused",
  lastScrape: "2026-09-26T21:00:00Z",
  lastScrapeDuration: 0.01,
});

describe("prometheus tools", () => {
  it.each([
    [
      undefined,
      [
        "gradiated_worker_loop_failures_total",
        "gradiated_worker_loop_up",
        "up",
      ],
    ],
    ["worker.*fail", ["gradiated_worker_loop_failures_total"]],
    ["SCRAPE", ["up"]],
  ])("finds metrics matching %s by name or help", async (search, names) => {
    const { body } = await callTool(
      "metric_metadata",
      search ? { search } : {},
      metadata,
    );

    expect(
      (body as { metrics: { name: string }[] }).metrics.map(({ name }) => name),
    ).toEqual(names);
  });

  it("reports the type and help of one entry per metric and truncates", async () => {
    const { body } = await callTool(
      "metric_metadata",
      { search: "loop", limit: 1 },
      metadata,
    );

    expect(body).toEqual({
      metrics: [
        {
          name: "gradiated_worker_loop_failures_total",
          type: "counter",
          help: "Supervised worker loop failures.",
          unit: "",
        },
      ],
      total_matches: 2,
      truncated: true,
    });
  });

  it("filters scrape targets by health and job without discovered labels", async () => {
    const { backend, body } = await callTool(
      "prometheus_targets",
      { health: "down", job: "worker" },
      {
        status: "success",
        data: {
          activeTargets: [
            target("worker", "down"),
            target("worker", "up"),
            target("api", "down"),
          ],
        },
      },
    );

    expect(backend).toHaveBeenCalledWith("prometheus", "/api/v1/targets", {
      state: "active",
    });
    expect(JSON.stringify(body)).not.toContain("PRIVATE");
    expect(body).toEqual({
      targets: [expect.objectContaining({ lastError: "connection refused" })],
    });
  });

  it("passes rule filters as repeated parameters", async () => {
    const { backend } = await callTool("prometheus_rules", {
      type: "alert",
      rule_name: ["WorkerLoopFailing", "WorkerLoopStalled"],
      rule_group: ["worker"],
    });

    expect(backend).toHaveBeenCalledWith("prometheus", "/api/v1/rules", {
      type: "alert",
      "rule_name[]": ["WorkerLoopFailing", "WorkerLoopStalled"],
      "rule_group[]": ["worker"],
    });
  });
});
