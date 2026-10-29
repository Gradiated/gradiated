import { readFileSync } from "node:fs";
import { request } from "node:https";

// get resolves to undefined for a missing object.
export interface Kubernetes {
  get(path: string): Promise<unknown>;
  list(path: string): Promise<unknown[]>;
  create(path: string, body: unknown): Promise<unknown>;
  mergePatch(path: string, body: unknown): Promise<unknown>;
  replace(path: string, body: unknown): Promise<unknown>;
}

export class KubernetesError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

// 409: a stale resourceVersion on update, or an object that already exists.
export const isConflict = (error: unknown) =>
  error instanceof KubernetesError && error.status === 409;

const ACCOUNT = "/var/run/secrets/kubernetes.io/serviceaccount";

export const inClusterKubernetes = (): Kubernetes => {
  const call = (method: string, path: string, body?: unknown) =>
    new Promise<unknown>((resolve, reject) => {
      const payload = body === undefined ? undefined : JSON.stringify(body);
      const req = request(
        {
          hostname: process.env.KUBERNETES_SERVICE_HOST,
          port: process.env.KUBERNETES_SERVICE_PORT_HTTPS ?? "443",
          path,
          method,
          ca: readFileSync(`${ACCOUNT}/ca.crt`),
          headers: {
            accept: "application/json",
            "content-type":
              method === "PATCH"
                ? "application/merge-patch+json"
                : "application/json",
            ...(payload === undefined
              ? {}
              : { "content-length": Buffer.byteLength(payload) }),
            authorization: `Bearer ${readFileSync(`${ACCOUNT}/token`, "utf8").trim()}`,
          },
          signal: AbortSignal.timeout(10_000),
        },
        (response) => {
          let text = "";
          response.setEncoding("utf8");
          response.on("data", (chunk: string) => {
            text += chunk;
            if (text.length > 4 * 1024 * 1024)
              req.destroy(new Error("Kubernetes response exceeded limit"));
          });
          response.on("error", reject);
          response.on("end", () => {
            const status = response.statusCode ?? 0;
            if (status < 200 || status >= 300)
              return reject(
                new KubernetesError(
                  status,
                  `Kubernetes ${method} ${path} returned ${status}`,
                ),
              );
            try {
              resolve(text ? JSON.parse(text) : undefined);
            } catch (error) {
              reject(error);
            }
          });
        },
      );
      req.on("error", reject);
      req.end(payload);
    });

  return {
    get: (path) =>
      call("GET", path).catch((error: unknown) => {
        if (error instanceof KubernetesError && error.status === 404)
          return undefined;
        throw error;
      }),
    list: async (path) =>
      ((await call("GET", path)) as { items?: unknown[] }).items ?? [],
    create: (path, body) => call("POST", path, body),
    mergePatch: (path, body) => call("PATCH", path, body),
    replace: (path, body) => call("PUT", path, body),
  };
};
