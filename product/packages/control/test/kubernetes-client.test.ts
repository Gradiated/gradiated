import { createServer } from "node:http";
import { afterEach, expect, it, vi } from "vitest";
import { createKubernetesRequest } from "../src/deployments/kubernetes-client.js";

// Exercise Node's real HTTP framing against a local API fixture; TLS is not under test.
vi.mock("node:https", async () => ({
  request: (await import("node:http")).request,
}));
vi.mock("node:fs", () => ({
  readFileSync: () => "synthetic-service-account-token",
}));
afterEach(() => vi.unstubAllEnvs());

it("delivers foreground deletion options to the Kubernetes API", async () => {
  let received: unknown;
  const server = createServer((request, response) => {
    let body = "";
    request.on("data", (chunk) => {
      body += chunk;
    });
    request.on("end", () => {
      received = body ? JSON.parse(body) : undefined;
      response.writeHead(200, { "content-type": "application/json" });
      response.end("{}");
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  if (!address || typeof address === "string")
    throw new Error("Missing fixture address");
  vi.stubEnv("KUBERNETES_SERVICE_HOST", "127.0.0.1");
  vi.stubEnv("KUBERNETES_SERVICE_PORT_HTTPS", String(address.port));
  const options = {
    apiVersion: "v1",
    kind: "DeleteOptions",
    propagationPolicy: "Foreground",
  };
  try {
    await createKubernetesRequest(AbortSignal.timeout(5000))(
      "/apis/batch/v1/jobs",
      "DELETE",
      options,
    );
    expect(received).toEqual(options);
  } finally {
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});
