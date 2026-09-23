import https from "node:https";
import { readFileSync } from "node:fs";

export type Backend = (
  system: "prometheus" | "loki" | "kubernetes",
  path: string,
  params?: Record<string, string>,
) => Promise<unknown>;
const MAX_BYTES = 1_000_000;

export const createBackend = (
  urls: { prometheus: string; loki: string },
  tenant: string,
): Backend => {
  let agent: https.Agent | undefined;

  return async (system, path, params = {}) => {
    const url = new URL(
      path,
      system === "kubernetes" ? "https://kubernetes.default.svc" : urls[system],
    );
    url.search = new URLSearchParams(params).toString();

    if (system === "kubernetes") {
      agent ??= new https.Agent({
        ca: readFileSync(
          "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt",
        ),
      });
      return new Promise((resolve, reject) => {
        const request = https.get(
          url,
          {
            agent,
            headers: {
              authorization: `Bearer ${readFileSync("/var/run/secrets/kubernetes.io/serviceaccount/token", "utf8").trim()}`,
            },
          },
          (response) => {
            const chunks: Buffer[] = [];
            let size = 0;
            response.on("data", (chunk: Buffer) => {
              size += chunk.length;
              if (size > MAX_BYTES) {
                request.destroy(new Error("response_limit"));
                return;
              }
              chunks.push(chunk);
            });
            response.on("error", reject);
            response.on("end", () => {
              if (response.statusCode !== 200) {
                reject(new Error("upstream_failed"));
                return;
              }
              try {
                resolve(JSON.parse(Buffer.concat(chunks).toString()));
              } catch {
                reject(new Error("upstream_invalid"));
              }
            });
          },
        );
        const timeout = setTimeout(
          () => request.destroy(new Error("upstream_timeout")),
          10_000,
        );
        request.on("close", () => clearTimeout(timeout));
        request.on("error", reject);
      });
    }

    const response = await fetch(url, {
      headers: system === "loki" ? { "X-Scope-OrgID": tenant } : {},
      signal: AbortSignal.timeout(10_000),
      redirect: "error",
    });
    if (!response.ok || !response.body) {
      await response.body?.cancel();
      throw new Error("upstream_failed");
    }

    const reader = response.body.getReader();
    const chunks: Uint8Array[] = [];
    let size = 0;
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.length;
        if (size > MAX_BYTES) throw new Error("response_limit");
        chunks.push(value);
      }
    } finally {
      await reader.cancel();
    }

    return JSON.parse(Buffer.concat(chunks).toString());
  };
};
