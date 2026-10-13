import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";
import { parseAllDocuments } from "yaml";

import { createTestApp } from "./support.js";

const WORKLOADS = new URL(
  "../../../../infra/environments/prod/us-east-1/kubernetes/workloads/",
  import.meta.url,
);
const HOST = "api.gradiated.com";

interface HttpRoute {
  kind: string;
  spec: {
    hostnames?: string[];
    rules?: {
      matches?: { path?: { type: string; value: string } }[];
      backendRefs?: { name: string }[];
    }[];
  };
}

const publicRules = () =>
  ["public-api.yaml", "proxy.yaml"].flatMap((file) =>
    parseAllDocuments(readFileSync(new URL(file, WORKLOADS), "utf8"))
      .map((document) => document.toJS() as HttpRoute | null)
      .filter((route) => route?.kind === "HTTPRoute")
      .filter((route) => route!.spec.hostnames?.includes(HOST))
      .flatMap((route) => route!.spec.rules ?? [])
      .filter((rule) => rule.backendRefs?.length)
      .flatMap((rule) =>
        (rule.matches ?? []).map((match) => {
          expect(match.path?.type).toBe("PathPrefix");

          return {
            prefix: match.path!.value.replace(/\/$/, ""),
            backend: rule.backendRefs![0]!.name,
          };
        }),
      ),
  );

// Gateway API matches path prefixes element by element, and the longest prefix wins.
const backendFor = (path: string) =>
  publicRules()
    .filter(
      ({ prefix }) =>
        prefix === "" || path === prefix || path.startsWith(`${prefix}/`),
    )
    .sort((a, b) => b.prefix.length - a.prefix.length)[0]?.backend;

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
