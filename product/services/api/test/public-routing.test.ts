import { describe, expect, it } from "vitest";

import { createTestApp } from "./support.js";

// Production HTTPRoute prefixes for api.gradiated.com live in
// Gradiated/infrastructure (environments/prod/us-east-1/kubernetes/workloads/{public-api,proxy}.yaml).
const PUBLIC_RULES = [
  { prefix: "/api", backend: "api" },
  { prefix: "/health", backend: "api" },
  { prefix: "/docs", backend: "api" },
  { prefix: "/.well-known/oauth-authorization-server", backend: "api" },
  { prefix: "/openai/v1", backend: "proxy" },
  { prefix: "", backend: "proxy" },
] as const;

// Gateway API matches path prefixes element by element, and the longest prefix wins.
const backendFor = (path: string) =>
  PUBLIC_RULES.filter(
    ({ prefix }) =>
      prefix === "" || path === prefix || path.startsWith(`${prefix}/`),
  ).sort((a, b) => b.prefix.length - a.prefix.length)[0]?.backend;

const literalPrefix = (path: string) => {
  const parts = path.split("/");
  const dynamic = parts.findIndex((part) => /[:*{]/.test(part));

  return (dynamic === -1 ? parts : parts.slice(0, dynamic)).join("/");
};

const servedPaths = () => {
  const app = createTestApp();

  return [...new Set(app.routes.map((route) => literalPrefix(route.path)))]
    .filter((path) => path !== "")
    .sort();
};

describe("public routing on api.gradiated.com", () => {
  it.each(servedPaths())("sends %s to the API", (path) => {
    expect(backendFor(path)).toBe("api");
  });

  it.each(["/v1/chat/completions", "/v1/messages", "/v1/audio/speech"])(
    "sends inference path %s to the proxy",
    (path) => {
      expect(backendFor(path)).toBe("proxy");
    },
  );
});
