import { EventEmitter } from "node:events";
import https from "node:https";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, expect, it, vi } from "vitest";
import { createBackend } from "../src/backend.js";

const backend = createBackend({
  prometheus: "http://prometheus.invalid",
  loki: "http://loki.invalid",
  lokiTenant: "eks-prod|model-nebius-prod",
  alertmanager: "http://alertmanager.invalid",
  nomad: {
    url: "https://nomad.invalid",
    caFile: "/nonexistent/ca",
    certFile: "/nonexistent/cert",
    keyFile: "/nonexistent/key",
    tokenFile: "/nonexistent/token",
  },
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
it("bounds upstream response bodies instead of buffering arbitrary output", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response("x".repeat(8_000_001))),
  );
  await expect(backend("loki", "/loki/api/v1/query_range")).rejects.toThrow(
    "response_limit",
  );
});
it("fixes the Loki tenant, encodes parameters, disables redirects and sets a timeout", async () => {
  const fetcher = vi.fn(async () => new Response('{"status":"success"}'));
  vi.stubGlobal("fetch", fetcher);
  await expect(
    backend("loki", "/loki/api/v1/query_range", { query: '{workload="api"}' }),
  ).resolves.toEqual({ status: "success" });
  const [url, options] = fetcher.mock.calls[0] as unknown as [URL, RequestInit];
  expect(url.host).toBe("loki.invalid");
  expect(url.searchParams.get("query")).toBe('{workload="api"}');
  expect(options.headers).toEqual({
    "X-Scope-OrgID": "eks-prod|model-nebius-prod",
  });
  expect(options.redirect).toBe("error");
  expect(options.signal).toBeInstanceOf(AbortSignal);
});
it("rejects failing and malformed upstream responses", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response("internal detail", { status: 503 })),
  );
  await expect(backend("prometheus", "/api/v1/alerts")).rejects.toThrow(
    "upstream_failed",
  );
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response("not JSON")),
  );
  await expect(backend("prometheus", "/api/v1/alerts")).rejects.toThrow();
});

it("sends the Nomad token and returns Nomad's next page token", async () => {
  const directory = mkdtempSync(join(tmpdir(), "ops-mcp-nomad-"));
  for (const name of ["ca", "cert", "key"]) {
    writeFileSync(join(directory, name), "test-only-pem");
  }
  writeFileSync(join(directory, "token"), "test-only-token\n");
  const get = vi.spyOn(https, "get").mockImplementation(((
    _url: URL,
    _options: https.RequestOptions,
    callback: (response: EventEmitter) => void,
  ) => {
    const response = Object.assign(new EventEmitter(), {
      statusCode: 200,
      headers: { "x-nomad-nexttoken": "5678.efgh" },
    });
    queueMicrotask(() => {
      callback(response);
      response.emit("data", Buffer.from("[]"));
      response.emit("end");
    });

    return Object.assign(new EventEmitter(), { destroy: vi.fn() });
  }) as unknown as typeof https.get);
  const nomad = createBackend({
    prometheus: "http://prometheus.invalid",
    loki: "http://loki.invalid",
    lokiTenant: "eks-prod",
    alertmanager: "http://alertmanager.invalid",
    nomad: {
      url: "https://nomad.invalid:4646",
      caFile: join(directory, "ca"),
      certFile: join(directory, "cert"),
      keyFile: join(directory, "key"),
      tokenFile: join(directory, "token"),
    },
  });

  await expect(
    nomad("nomad", "/v1/allocations", { filter: 'ClientStatus == "failed"' }),
  ).resolves.toEqual({ data: [], next_token: "5678.efgh" });

  const [url, options] = get.mock.calls[0] as unknown as [
    URL,
    https.RequestOptions,
  ];
  expect(url.href).toBe(
    "https://nomad.invalid:4646/v1/allocations?filter=ClientStatus+%3D%3D+%22failed%22",
  );
  expect(options.headers).toEqual({ "x-nomad-token": "test-only-token" });
});
