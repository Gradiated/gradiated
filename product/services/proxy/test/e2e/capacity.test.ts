import { connect } from "node:net";

import { describe, expect, it } from "vitest";

import { useCases, type Case } from "../../../gateway/test/integration/case.js";
import {
  deferred,
  eventually,
  type Deferred,
} from "../../../gateway/test/integration/eventually.js";
import type { Response } from "../../../gateway/test/integration/http-client.js";
import type { ProxyProcess } from "./support/proxy-process.js";
import {
  CHAT,
  expectProxyError,
  MESSAGES,
  providerModel,
  relayHeaders,
  useProxy,
} from "./support/fixtures.js";

const { makeCase } = useCases();
const fixture = useProxy(makeCase);

/** A relay whose provider holds the response head until `gate` opens. */
const heldRelay = (
  proxy: ProxyProcess,
  instance: Case,
  gate: Deferred,
  padding = 0,
): Promise<Response> => {
  fixture.provider.reply({ beforeHeaders: gate });

  return proxy.client.post(MESSAGES.path, {
    headers: relayHeaders(instance, "anthropic"),
    json: {
      ...MESSAGES.body(providerModel("anthropic")),
      padding: "x".repeat(padding),
    },
  });
};

/** A hosted request whose runtime holds it until `gate` opens. */
const heldHosted = (
  proxy: ProxyProcess,
  instance: Case,
  gate: Deferred,
): Promise<Response> => {
  instance.runtimes[0]!.enqueue({ gate });

  return proxy.client.post(CHAT.path, {
    headers: instance.headers,
    json: CHAT.body(instance.model),
  });
};

const relayBody = (bytes: number): string => {
  const base = JSON.stringify({
    ...MESSAGES.body(providerModel("anthropic")),
    padding: "",
  });

  return base.replace(
    '"padding":""',
    `"padding":"${"x".repeat(bytes - base.length)}"`,
  );
};

describe("in-flight cap", () => {
  it.each([
    { name: "two relays", hosted: 0 },
    { name: "a relay and a hosted request", hosted: 1 },
  ])("refuses a third request while $name are open", async ({ hosted }) => {
    const proxy = await fixture.startProxy({ PROXY_MAX_IN_FLIGHT: "2" });
    const instance = await fixture.hostedCase();
    const gate = deferred();

    const held = [
      heldRelay(proxy, instance, gate),
      hosted
        ? heldHosted(proxy, instance, gate)
        : heldRelay(proxy, instance, gate),
    ];
    await eventually(
      () =>
        fixture.provider.requests.length +
          instance.runtimes[0]!.calls.length ===
        2,
      5000,
      "the held requests never arrived",
    );

    expectProxyError(
      await proxy.client.post(MESSAGES.path, {
        headers: relayHeaders(instance, "anthropic"),
        json: MESSAGES.body(providerModel("anthropic")),
      }),
      "proxy_overloaded",
      "anthropic",
    );
    expect(
      fixture.provider.requests.length + instance.runtimes[0]!.calls.length,
    ).toBe(2);

    gate.resolve();
    const completed = await Promise.all(held);
    expect(completed.map((response) => response.status)).toEqual([200, 200]);
    if (hosted) await instance.settled(completed[1]!);

    const after = await proxy.client.post(MESSAGES.path, {
      headers: relayHeaders(instance, "anthropic"),
      json: MESSAGES.body(providerModel("anthropic")),
    });
    expect(after.status).toBe(200);
  });
});

describe("request size", () => {
  const LIMIT = 4096;

  it.each([
    { name: "a relay", route: MESSAGES, hosted: false },
    { name: "a hosted request", route: CHAT, hosted: true },
  ])(
    "refuses $name above the byte limit before any upstream sees it",
    async ({ route, hosted }) => {
      const proxy = await fixture.startProxy({
        PROXY_MAX_REQUEST_BYTES: String(LIMIT),
      });
      const instance = await fixture.hostedCase();
      const model = hosted ? instance.model : providerModel(route.provider);
      const headers = hosted
        ? instance.headers
        : relayHeaders(instance, route.provider);
      const gatewayBefore = await proxy.responses("gateway");

      const response = await proxy.client.post(route.path, {
        headers: { ...headers, "content-type": "application/json" },
        content: JSON.stringify({
          ...route.body(model),
          padding: "x".repeat(LIMIT),
        }),
      });

      expectProxyError(response, "payload_too_large", route.provider);
      expect(fixture.provider.requests).toEqual([]);
      expect(await proxy.responses("gateway")).toBe(gatewayBefore);
      await instance.expectNotDispatched();
    },
  );

  it("reads an oversized upload to its end before answering 413", async () => {
    const proxy = await fixture.startProxy({
      PROXY_MAX_REQUEST_BYTES: String(LIMIT),
    });
    const instance = await makeCase("vllm");
    const { hostname, port } = new URL(proxy.url);
    // A load balancer that is still sending when the proxy closes answers 502.
    const total = 4 * 1024 * 1024;
    const chunk = Buffer.alloc(64 * 1024, "x");

    const socket = connect(Number(port), hostname);
    await new Promise<void>((resolve) => socket.once("connect", resolve));
    let received = "";
    let failure: Error | undefined;
    socket.on("data", (data) => (received += data.toString()));
    socket.on("error", (error) => (failure = error));
    const write = (data: string | Buffer) =>
      new Promise<void>((resolve, reject) =>
        socket.write(data, (error) => (error ? reject(error) : resolve())),
      );

    await write(
      [
        `POST ${MESSAGES.path} HTTP/1.1`,
        `host: ${hostname}`,
        "content-type: application/json",
        `content-length: ${total}`,
        ...Object.entries(relayHeaders(instance, "anthropic")).map(
          ([name, value]) => `${name}: ${value}`,
        ),
        "",
        "",
      ].join("\r\n"),
    );
    for (let sent = 0; sent < total; sent += chunk.length) {
      await write(chunk);
      // Give the proxy time to answer and close mid-upload, as a slow client would.
      if (sent < 4 * chunk.length)
        await new Promise((resolve) => setTimeout(resolve, 50));
    }

    await eventually(() => received.includes("payload_too_large"), 5000);
    expect(failure).toBeUndefined();
    expect(received).toMatch(/^HTTP\/1\.1 413 /);
    expect(received.indexOf("HTTP/1.1 413")).toBe(
      received.lastIndexOf("HTTP/1.1 "),
    );
    socket.destroy();
    expect(fixture.provider.requests).toEqual([]);
  });

  it("stops reading an oversized upload past the drain limit", async () => {
    const proxy = await fixture.startProxy({
      PROXY_MAX_REQUEST_BYTES: String(LIMIT),
    });
    const instance = await makeCase("vllm");
    const { hostname, port } = new URL(proxy.url);
    const chunk = Buffer.alloc(1024 * 1024, "x");

    const socket = connect(Number(port), hostname);
    await new Promise<void>((resolve) => socket.once("connect", resolve));
    const closed = new Promise<void>((resolve) => {
      socket.on("close", () => resolve());
      socket.on("error", () => resolve());
    });
    socket.write(
      [
        `POST ${MESSAGES.path} HTTP/1.1`,
        `host: ${hostname}`,
        "content-type: application/json",
        `content-length: ${1024 * 1024 * 1024}`,
        ...Object.entries(relayHeaders(instance, "anthropic")).map(
          ([name, value]) => `${name}: ${value}`,
        ),
        "",
        "",
      ].join("\r\n"),
    );
    // Keep sending until the proxy hangs up; it reads at most the 64 MiB floor.
    let sent = 0;
    while (!socket.destroyed && sent < 512 * 1024 * 1024) {
      if (!socket.write(chunk))
        await Promise.race([
          new Promise((resolve) => socket.once("drain", resolve)),
          closed,
        ]);
      sent += chunk.length;
    }
    await closed;

    expect(sent).toBeLessThan(256 * 1024 * 1024);
    expect(fixture.provider.requests).toEqual([]);
  });

  it("accepts a body of exactly the limit", async () => {
    const proxy = await fixture.startProxy({
      PROXY_MAX_REQUEST_BYTES: String(LIMIT),
    });
    const instance = await makeCase("vllm");
    const body = relayBody(LIMIT);
    expect(Buffer.byteLength(body)).toBe(LIMIT);

    const response = await proxy.client.post(MESSAGES.path, {
      headers: {
        ...relayHeaders(instance, "anthropic"),
        "content-type": "application/json",
      },
      content: body,
    });

    expect(response.status, response.text).toBe(200);
    expect(fixture.provider.requests[0]!.body.toString()).toBe(body);
  });

  it("refuses a body that would exceed the shared byte budget", async () => {
    const proxy = await fixture.startProxy({
      PROXY_MAX_REQUEST_BYTES: String(LIMIT),
      PROXY_REQUEST_BUFFER_BYTES: String(LIMIT + LIMIT / 2),
    });
    const instance = await makeCase("vllm");
    const gate = deferred();

    const held = heldRelay(proxy, instance, gate, LIMIT - 512);
    await eventually(
      () => fixture.provider.requests.length === 1,
      5000,
      "the held relay never arrived",
    );

    const refused = await proxy.client.post(MESSAGES.path, {
      headers: {
        ...relayHeaders(instance, "anthropic"),
        "content-type": "application/json",
      },
      content: relayBody(LIMIT),
    });
    expectProxyError(refused, "proxy_overloaded", "anthropic");

    gate.resolve();
    expect((await held).status).toBe(200);

    const admitted = await proxy.client.post(MESSAGES.path, {
      headers: {
        ...relayHeaders(instance, "anthropic"),
        "content-type": "application/json",
      },
      content: relayBody(LIMIT),
    });
    expect(admitted.status).toBe(200);
  });
});

describe("body read deadline", () => {
  it("answers 408 to a stalled upload and frees its slot", async () => {
    const proxy = await fixture.startProxy({
      PROXY_MAX_IN_FLIGHT: "1",
      PROXY_BODY_READ_SECONDS: "1",
    });
    const instance = await fixture.hostedCase();
    const { hostname, port } = new URL(proxy.url);
    const headers = relayHeaders(instance, "anthropic");

    const socket = connect(Number(port), hostname);
    const reply = new Promise<string>((resolve) => {
      let text = "";
      socket.on("data", (chunk) => {
        text += chunk.toString();
        if (text.includes("\r\n\r\n")) resolve(text);
      });
      socket.on("close", () => resolve(text));
      socket.on("error", () => resolve(text));
    });
    socket.write(
      [
        `POST ${MESSAGES.path} HTTP/1.1`,
        `host: ${hostname}`,
        "content-type: application/json",
        "content-length: 100",
        ...Object.entries(headers).map(([name, value]) => `${name}: ${value}`),
        "",
        '{"model":',
      ].join("\r\n"),
    );

    expect(await reply).toMatch(/^HTTP\/1\.1 408 /);
    socket.destroy();
    expect(fixture.provider.requests).toEqual([]);

    const after = await proxy.client.post(MESSAGES.path, {
      headers,
      json: MESSAGES.body(providerModel("anthropic")),
    });
    expect(after.status, after.text).toBe(200);
  });
});
