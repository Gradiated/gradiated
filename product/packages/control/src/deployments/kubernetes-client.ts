import { readFileSync } from "node:fs";
import { request } from "node:https";

export const createKubernetesRequest = (signal: AbortSignal) => {
  const directory = "/var/run/secrets/kubernetes.io/serviceaccount";
  return (path: string, method = "GET", body?: unknown): Promise<unknown> =>
    new Promise((resolve, reject) => {
      const payload = body === undefined ? undefined : JSON.stringify(body);
      const req = request(
        {
          hostname: process.env.KUBERNETES_SERVICE_HOST,
          port: process.env.KUBERNETES_SERVICE_PORT_HTTPS ?? "443",
          path,
          method,
          ca: readFileSync(`${directory}/ca.crt`),
          headers: {
            "content-type":
              method === "PATCH"
                ? "application/json-patch+json"
                : "application/json",
            ...(payload === undefined
              ? {}
              : { "content-length": Buffer.byteLength(payload) }),
            authorization: `Bearer ${readFileSync(`${directory}/token`, "utf8").trim()}`,
          },
          signal: AbortSignal.any([signal, AbortSignal.timeout(10_000)]),
        },
        (response) => {
          let body = "";
          response.on("data", (chunk) => {
            body += chunk;
            if (body.length > 4 * 1024 * 1024)
              req.destroy(new Error("Kubernetes response exceeded limit"));
          });
          response.on("error", reject);
          response.on("end", () => {
            if (
              !response.statusCode ||
              response.statusCode < 200 ||
              response.statusCode >= 300
            )
              return reject(
                Object.assign(
                  new Error(
                    `Kubernetes request returned ${response.statusCode}`,
                  ),
                  { code: String(response.statusCode) },
                ),
              );
            try {
              resolve(body ? JSON.parse(body) : undefined);
            } catch (error) {
              reject(error);
            }
          });
        },
      );
      req.on("error", reject);
      req.end(payload);
    });
};
