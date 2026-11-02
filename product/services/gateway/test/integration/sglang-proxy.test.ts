import { createServer, type Server } from "node:http";

import { expect, inject, it } from "vitest";

import { expectRejected } from "./assertions.js";
import { useCases } from "./case.js";
import { deferred, eventually, within } from "./eventually.js";
import { GatewayProcess } from "./gateway-process.js";
import { freePort } from "./ports.js";
import { response as chatResponse } from "./mock-runtimes/vllm.js";
import { sglangEvents } from "./sglang-wire.js";

const { makeCase } = useCases();
const model = "fixture/sglang";
const start = async (server: Server): Promise<string> => {
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  if (address === null || typeof address === "string")
    throw new Error("not listening");

  return `http://127.0.0.1:${address.port}`;
};
const close = async (server: Server): Promise<void> => {
  server.closeAllConnections();
  await new Promise<void>((resolve) => server.close(() => resolve()));
};

it("waits for a new deployment sharing a cached release before inference", async () => {
  const source = createServer((_request, response) => {
    response.writeHead(200, { "Content-Type": "application/json" });
    response.end(JSON.stringify(chatResponse({ model })));
  });
  const baseUrl = await start(source);
  const options = {
    upstream: { kind: "proxy" as const, baseUrl, model },
    gatewayUrl: inject("stack").gatewayUrl,
    runtimeRevision: "shared-runtime",
    modelRevision: "shared-checkpoint",
  };
  try {
    const first = await makeCase("vllm", options);
    await first.ready();
    const second = await makeCase("vllm", options);
    expect(second.digest).toBe(first.digest);
    expect(second.deployments[0]!.id).not.toBe(first.deployments[0]!.id);
    await second.ready();
    expect(second.totalCalls()).toBe(0);
    const response = await second.post();
    expect(response.status, response.text).toBe(200);
    expect(second.totalCalls()).toBe(1);
    await second.settled(response, { charge: 1060 });
  } finally {
    await close(source);
  }
});

it("starts public headers and keepalives while upstream HTTP headers remain pending", async () => {
  const release = deferred();
  const source = createServer((_request, response) => {
    void release.promise.then(() => {
      response.writeHead(200, { "Content-Type": "text/event-stream" });
      response.end(
        sglangEvents(model)
          .map(
            (frame) =>
              `data: ${typeof frame === "string" ? frame : JSON.stringify(frame)}\n\n`,
          )
          .join(""),
      );
    });
  });
  const baseUrl = await start(source);
  const stack = inject("stack");
  const gateway = await GatewayProcess.start({
    redisUrl: stack.redisUrl,
    databaseUrl: stack.databaseUrl,
    runtimeToken: stack.runtimeToken,
    port: await freePort(),
    generationTimeoutSeconds: 60,
    logName: `sglang-delayed-headers-${crypto.randomUUID()}`,
  });
  try {
    const instance = await makeCase("vllm", {
      upstream: { kind: "proxy", baseUrl, model },
      gatewayUrl: gateway.url,
    });
    const before = performance.now();
    const response = await instance.http.stream(instance.path, {
      headers: instance.headers,
      json: instance.body({ stream: true }),
      timeoutMs: 25_000,
    });
    expect(performance.now() - before).toBeLessThan(5000);
    expect(instance.runtimes[0]!.upstreamResponses).toBe(0);
    const lines = response.lines();
    const first = await lines.next();
    expect(first.value).toContain("keep-alive");
    expect(instance.runtimes[0]!.upstreamResponses).toBe(0);
    release.resolve();
    const frames: string[] = [];
    for await (const line of lines) {
      if (line.startsWith("data:")) frames.push(line.slice(5).trim());
    }
    expect(frames.at(-1)).toBe("[DONE]");
    await instance.settled(response, { charge: 740 });
  } finally {
    release.resolve();
    await gateway.stop();
    await close(source);
  }
}, 30_000);

it("carries local gateway cancellation through the proxy to the upstream socket", async () => {
  const closed = deferred();
  const source = createServer((_request, response) => {
    response.writeHead(200, { "Content-Type": "text/event-stream" });
    response.write(`data: ${JSON.stringify(sglangEvents(model)[0])}\n\n`);
    response.once("close", () => closed.resolve());
  });
  const baseUrl = await start(source);
  try {
    const instance = await makeCase("vllm", {
      upstream: { kind: "proxy", baseUrl, model },
      gatewayUrl: inject("stack").gatewayUrl,
    });
    const response = await instance.http.stream(instance.path, {
      headers: instance.headers,
      json: instance.body({ stream: true }),
    });
    for await (const line of response.lines()) {
      if (line.startsWith("data:")) break;
    }
    await instance.settled(response, { status: "cancelled" });
    expect((await within(closed.promise, 2000)).settled).toBe(true);
    await eventually(
      async () => instance.runtimes[0]!.upstreamCancelled === 1,
      2000,
      "proxy did not abort upstream",
    );
  } finally {
    await close(source);
  }
});

it.each([false, true])(
  "relays actual upstream429 faithfully for stream=%s",
  async (stream) => {
    let upstreamCalls = 0;
    const source = createServer((_request, response) => {
      upstreamCalls += 1;
      response.writeHead(429, { "Content-Type": "application/json" });
      response.end(
        JSON.stringify({ error: { message: "PRIVATE_UPSTREAM_QUEUE" } }),
      );
    });
    const baseUrl = await start(source);
    try {
      const instance = await makeCase("vllm", {
        replicas: 3,
        upstream: { kind: "proxy", baseUrl, model },
        gatewayUrl: inject("stack").gatewayUrl,
      });
      const response = await instance.post({ stream });
      expectRejected(response, { code: "capacity_exceeded" });
      expect(response.text).not.toContain("PRIVATE_UPSTREAM_QUEUE");
      expect(upstreamCalls).toBe(2);
      expect(instance.runtimes.map((r) => r.calls.length).sort()).toEqual([
        0, 1, 1,
      ]);
      await instance.settled(response, { status: "failed", charge: 0 });
    } finally {
      await close(source);
    }
  },
);
