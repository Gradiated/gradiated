import { afterEach, describe, expect, it } from "vitest";

import { callTool, closeServers, range } from "./support/mcp.js";

afterEach(closeServers);

describe("discovery tools", () => {
  it.each([
    [
      "label_names",
      { source: "metrics", selector: '{job="api"}' },
      "prometheus",
      "/api/v1/labels",
      { "match[]": '{job="api"}' },
    ],
    [
      "label_names",
      { source: "logs", selector: '{workload="api"}' },
      "loki",
      "/loki/api/v1/labels",
      { query: '{workload="api"}' },
    ],
    [
      "label_values",
      { source: "metrics", name: "__name__", selector: '{__name__=~"up"}' },
      "prometheus",
      "/api/v1/label/__name__/values",
      { "match[]": '{__name__=~"up"}' },
    ],
    [
      "label_values",
      { source: "logs", name: "workload" },
      "loki",
      "/loki/api/v1/label/workload/values",
      {},
    ],
    [
      "series",
      { source: "metrics", selector: "up" },
      "prometheus",
      "/api/v1/series",
      { "match[]": "up" },
    ],
    [
      "series",
      { source: "logs", selector: '{workload="api"}' },
      "loki",
      "/loki/api/v1/series",
      { "match[]": '{workload="api"}' },
    ],
  ])("%s with %o reads %s %s", async (name, args, system, path, parameters) => {
    const { backend, isError } = await callTool(name, {
      ...args,
      start: "2026-09-26T23:00:00+02:00",
    });

    expect(isError).toBe(false);
    expect(backend).toHaveBeenCalledWith(system, path, {
      ...parameters,
      start: "2026-09-26T21:00:00.000Z",
    });
  });

  it.each([
    ["label_names", { source: "metrics" }],
    ["label_values", { source: "metrics", name: "job" }],
    ["series", { source: "metrics", selector: "up" }],
  ])(
    "limits %s on metrics to the hour before end when start is omitted",
    async (name, args) => {
      const { backend } = await callTool(name, {
        ...args,
        end: "2026-09-26T21:30:00Z",
      });

      expect(backend).toHaveBeenCalledWith(
        "prometheus",
        expect.any(String),
        expect.objectContaining({
          start: "2026-09-26T20:30:00.000Z",
          end: "2026-09-26T21:30:00.000Z",
        }),
      );
    },
  );

  it("leaves the log default window to Loki", async () => {
    const { backend } = await callTool("label_names", { source: "logs" });

    expect(backend).toHaveBeenCalledWith("loki", "/loki/api/v1/labels", {});
  });

  it("truncates long value lists and reports the total", async () => {
    const { body } = await callTool(
      "label_values",
      { source: "metrics", name: "job", limit: 2 },
      { status: "success", data: ["a", "b", "c"] },
    );

    expect(body).toEqual({ values: ["a", "b"], total: 3, truncated: true });
  });

  it.each([
    ["label_values", { source: "metrics", name: "job/../../admin" }],
    ["label_values", { source: "traces", name: "job" }],
    ["series", { source: "metrics" }],
    ["label_names", { source: "logs", start: range.end, end: range.start }],
  ])("rejects %s with %o", async (name, args) => {
    const { backend, isError } = await callTool(name, args);

    expect(isError).toBe(true);
    expect(backend).not.toHaveBeenCalled();
  });
});
