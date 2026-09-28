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
afterEach(() => vi.unstubAllGlobals());
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
