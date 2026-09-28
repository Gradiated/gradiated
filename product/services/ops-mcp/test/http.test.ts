import { afterEach, describe, expect, it, vi } from "vitest";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import type { AddressInfo } from "node:net";
import { request as httpRequest } from "node:http";
import { createHttp } from "../src/http.js";
import { logQuery, projectPods } from "../src/tools.js";

const token = "test-only-credential-0123456789abcdef";
const range = {
  start: "2026-09-26T21:00:00Z",
  end: "2026-09-26T21:30:00Z",
};
const open: ReturnType<typeof createHttp>[] = [];
afterEach(async () => {
  for (const app of open.splice(0)) {
    app.server.closeAllConnections();
    await new Promise<void>((resolve) => app.server.close(() => resolve()));
  }
});
const setup = async () => {
  const backend = vi.fn(async (): Promise<unknown> => ({
    status: "success",
    data: [],
  }));
  const audit = vi.fn();
  const options = {
    host: "ops.gradiated.com",
    authenticate: async (supplied: string) =>
      supplied === token
        ? { subject: "test-coder", email: "tester@gradiated.com" }
        : undefined,
    backend,
    audit,
  };
  const app = createHttp(options);
  open.push(app);
  await new Promise<void>((resolve) =>
    app.server.listen(0, "127.0.0.1", resolve),
  );
  const url = new URL(
    `http://127.0.0.1:${(app.server.address() as AddressInfo).port}/mcp`,
  );
  options.host = url.host;
  const headers = {
    host: url.host,
    authorization: `Bearer ${token}`,
    "content-type": "application/json",
    accept: "application/json, text/event-stream",
  };
  return { app, url, backend, audit, headers };
};

describe("production MCP boundary", () => {
  it("supports SDK initialization, discovery and queries, audits caller without token or arguments", async () => {
    const { url, headers, backend, audit } = await setup();
    const client = new Client({ name: "test", version: "1" });
    await client.connect(
      new StreamableHTTPClientTransport(url, { requestInit: { headers } }),
    );
    const list = await client.listTools();
    expect(list.tools).toHaveLength(7);
    expect(list.tools.every((t) => t.annotations?.readOnlyHint)).toBe(true);
    const result = await client.callTool({
      name: "query_logs",
      arguments: {
        service: "gateway",
        workspace_id: "c6390e68-499d-4f28-8243-05e5bbdf224f",
        ...range,
      },
    });
    expect(result.isError).not.toBe(true);
    expect(backend).toHaveBeenCalledWith(
      "loki",
      "/loki/api/v1/query_range",
      expect.objectContaining({
        limit: "100",
        query: expect.stringContaining('workload="gateway"'),
      }),
    );
    expect(audit).toHaveBeenCalledWith(
      expect.objectContaining({
        principal: "test-coder",
        tool: "query_logs",
        outcome: "success",
      }),
    );
    expect(JSON.stringify(audit.mock.calls)).not.toContain(token);
    expect(JSON.stringify(audit.mock.calls)).not.toContain("c6390e68");
    await client.close();
  });
  it("queries the Argo namespace and rejects service names as namespaces", async () => {
    const { url, headers, backend } = await setup();
    backend.mockResolvedValue({ items: [] });
    const client = new Client({ name: "test", version: "1" });
    await client.connect(
      new StreamableHTTPClientTransport(url, { requestInit: { headers } }),
    );
    const result = await client.callTool({
      name: "workload_status",
      arguments: { namespace: "argocd" },
    });
    expect(result.isError).not.toBe(true);
    expect(backend).toHaveBeenCalledWith(
      "kubernetes",
      "/api/v1/namespaces/argocd/pods",
      { limit: "100" },
    );
    backend.mockClear();
    const invalid = await client.callTool({
      name: "workload_status",
      arguments: { namespace: "argocd-server" },
    });
    expect(invalid.isError).toBe(true);
    expect(backend).not.toHaveBeenCalled();
    await client.close();
  });
  it("rejects unauthenticated calls, hostile hosts/origins and oversized bodies before upstream access", async () => {
    const { url, headers, backend } = await setup();
    const wrongHost = await new Promise<number | undefined>(
      (resolve, reject) => {
        const request = httpRequest(
          url,
          { method: "POST", headers: { ...headers, host: "evil.example" } },
          (response) => {
            response.resume();
            resolve(response.statusCode);
          },
        );
        request.on("error", reject);
        request.end("{}");
      },
    );
    expect(wrongHost).toBe(403);
    for (const [overrides, status] of [
      [{ authorization: "Bearer invalid" }, 401],
      [{ origin: "https://evil.example" }, 403],
    ] as const) {
      expect(
        (
          await fetch(url, {
            method: "POST",
            headers: { ...headers, ...overrides },
            body: "{}",
          })
        ).status,
      ).toBe(status);
    }
    expect(
      (
        await fetch(url, {
          method: "POST",
          headers,
          body: JSON.stringify({ value: "x".repeat(70_000) }),
        })
      ).status,
    ).toBe(413);
    expect(backend).not.toHaveBeenCalled();
  });
  it.each([
    ["query_logs", { service: "worker", ...range }],
    ["query_metric_history", { query: "up", ...range }],
  ])("passes an agent-chosen range of any age to %s", async (name, args) => {
    const { url, headers, backend } = await setup();
    const client = new Client({ name: "test", version: "1" });
    await client.connect(
      new StreamableHTTPClientTransport(url, { requestInit: { headers } }),
    );
    const result = await client.callTool({
      name,
      arguments: { ...args, start: "2026-03-01T00:00:00+02:00" },
    });
    expect(result.isError).not.toBe(true);
    expect(backend).toHaveBeenCalledWith(
      expect.any(String),
      expect.stringContaining("query_range"),
      expect.objectContaining({
        start: "2026-02-28T22:00:00.000Z",
        end: "2026-09-26T21:30:00.000Z",
      }),
    );
    await client.close();
  });
  it("evaluates an instant query at an agent-chosen time", async () => {
    const { url, headers, backend } = await setup();
    const client = new Client({ name: "test", version: "1" });
    await client.connect(
      new StreamableHTTPClientTransport(url, { requestInit: { headers } }),
    );
    await client.callTool({
      name: "query_metrics",
      arguments: { query: "up", time: "2026-03-01T00:00:00+02:00" },
    });
    await client.callTool({
      name: "query_metrics",
      arguments: { query: "up" },
    });
    expect(backend).toHaveBeenNthCalledWith(
      1,
      "prometheus",
      "/api/v1/query",
      expect.objectContaining({ time: "2026-02-28T22:00:00.000Z" }),
    );
    expect(backend).toHaveBeenNthCalledWith(
      2,
      "prometheus",
      "/api/v1/query",
      expect.not.objectContaining({ time: expect.anything() }),
    );
    await client.close();
  });
  it("spreads metric history over at most 121 timestamps", async () => {
    const { url, headers, backend } = await setup();
    const client = new Client({ name: "test", version: "1" });
    await client.connect(
      new StreamableHTTPClientTransport(url, { requestInit: { headers } }),
    );
    await client.callTool({
      name: "query_metric_history",
      arguments: { query: "up", ...range },
    });
    expect(backend).toHaveBeenCalledWith(
      "prometheus",
      "/api/v1/query_range",
      expect.objectContaining({ step: "15" }),
    );
    await client.close();
  });
  it("rejects injected log selectors, secrets disguised as IDs and invalid time ranges", async () => {
    const { url, headers, backend } = await setup();
    const client = new Client({ name: "test", version: "1" });
    await client.connect(
      new StreamableHTTPClientTransport(url, { requestInit: { headers } }),
    );
    for (const args of [
      { service: 'gateway"} |= "secret', ...range },
      { service: "api", api_key_id: "secret-key", ...range },
      { service: "worker" },
      { service: "worker", start: "yesterday", end: range.end },
      { service: "worker", start: range.end, end: range.start },
      { service: "worker", start: range.start, end: range.start },
    ]) {
      const result = await client.callTool({
        name: "query_logs",
        arguments: args,
      });
      expect(result.isError).toBe(true);
    }
    expect(backend).not.toHaveBeenCalled();
    await client.close();
  });
  it("does not expose upstream errors or interpret failed queries as healthy", async () => {
    const { url, headers, backend } = await setup();
    backend.mockRejectedValue(new Error("secret backend password"));
    const client = new Client({ name: "test", version: "1" });
    await client.connect(
      new StreamableHTTPClientTransport(url, { requestInit: { headers } }),
    );
    const result = await client.callTool({ name: "active_alerts" });
    expect(result.isError).toBe(true);
    expect(JSON.stringify(result)).not.toContain("password");
    await client.close();
  });
  it("bounds request volume and resets the budget in the next minute", async () => {
    const { url, headers, backend } = await setup();
    const now = vi.spyOn(Date, "now").mockReturnValue(120_000);
    try {
      for (let i = 0; i < 60; i++)
        await fetch(url, { method: "POST", headers, body: "[]" });
      expect(
        (await fetch(url, { method: "POST", headers, body: "[]" })).status,
      ).toBe(429);
      now.mockReturnValue(180_000);
      expect(
        (await fetch(url, { method: "POST", headers, body: "[]" })).status,
      ).toBe(400);
      expect(backend).not.toHaveBeenCalled();
    } finally {
      now.mockRestore();
    }
  });
});

it("preserves diagnostic fields but strips pod environment, messages, annotations and arguments", () => {
  const result = projectPods({
    items: [
      {
        metadata: {
          name: "gateway",
          namespace: "gradiated",
          annotations: { secret: "PRIVATE" },
        },
        spec: {
          nodeName: "node-1",
          containers: [{ env: [{ value: "PRIVATE" }], args: ["PRIVATE"] }],
        },
        status: {
          phase: "Running",
          containerStatuses: [
            {
              name: "gateway",
              ready: false,
              restartCount: 3,
              image: "image@sha256:abc",
              state: {
                waiting: { reason: "CrashLoopBackOff", message: "PRIVATE" },
              },
            },
          ],
        },
      },
    ],
  });
  expect(JSON.stringify(result)).not.toContain("PRIVATE");
  expect(JSON.stringify(result)).toContain("CrashLoopBackOff");
});
it("filters both flat and nested correlation IDs", () => {
  const query = logQuery({
    service: "gateway",
    limit: 10,
    ...range,
    generation_id: "c6390e68-499d-4f28-8243-05e5bbdf224f",
  });
  expect(query).toContain(
    ".root_generation_id .span_generation_id .fields_generation_id",
  );
});

it("uses a bounded severity selector for warning aliases", () => {
  expect(
    logQuery({ service: "api", level: "warn", limit: 10, ...range }),
  ).toContain('level=~"(?i)warn|warning"');
});
