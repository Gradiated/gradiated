import { describe, expect, it } from "vitest";

import { useCases, type Case } from "../../../gateway/test/integration/case.js";
import {
  deferred,
  eventually,
} from "../../../gateway/test/integration/eventually.js";
import type { StreamResponse } from "../../../gateway/test/integration/http-client.js";
import type { ProxyProcess } from "./support/proxy-process.js";
import {
  CHAT,
  MESSAGES,
  providerModel,
  relayHeaders,
  useProxy,
} from "./support/fixtures.js";
import { anthropic as wire } from "./support/wire.js";

const { makeCase } = useCases();
const fixture = useProxy(makeCase);

const EVENTS = wire.stream("claude-synthetic", ["one", "two", "three"]);

const relayStream = (
  proxy: ProxyProcess,
  instance: Case,
): Promise<StreamResponse> =>
  proxy.client.stream(MESSAGES.path, {
    headers: relayHeaders(instance, "anthropic"),
    json: { ...MESSAGES.body(providerModel("anthropic")), stream: true },
  });

const hostedStream = (
  proxy: ProxyProcess,
  instance: Case,
): Promise<StreamResponse> =>
  proxy.client.stream(CHAT.path, {
    headers: instance.headers,
    json: { ...CHAT.body(instance.model), stream: true },
  });

const readAll = async (response: StreamResponse): Promise<string> => {
  let text = "";
  for await (const chunk of response.message) text += String(chunk);

  return text;
};

const inFlight = (proxy: ProxyProcess, destination: string): Promise<number> =>
  proxy.count("gradiated_proxy_in_flight", `destination="${destination}"`);

const refusesConnections = async (proxy: ProxyProcess): Promise<boolean> => {
  try {
    await proxy.client.get("/v1/models", { timeoutMs: 1000 });
    return false;
  } catch (error) {
    return String(error).includes("ECONNREFUSED");
  }
};

describe("cancellation", () => {
  it("closes the provider connection when the customer leaves mid-stream", async () => {
    const instance = await makeCase("vllm");
    fixture.provider.reply({
      chunks: EVENTS,
      afterFirstChunk: deferred(),
      stall: true,
    });

    const response = await relayStream(fixture.proxy, instance);
    for await (const _ of response.message) break;

    await fixture.provider.requests[0]!.abandoned.promise;
    await eventually(
      async () => (await inFlight(fixture.proxy, "anthropic")) === 0,
      5000,
      "the relay slot was never released",
    );
  });

  it("closes the provider connection when the customer leaves before the response head", async () => {
    const instance = await makeCase("vllm");
    const head = deferred();
    fixture.provider.reply({ beforeHeaders: head });

    const pending = fixture.proxy.client
      .post(MESSAGES.path, {
        headers: relayHeaders(instance, "anthropic"),
        json: MESSAGES.body(providerModel("anthropic")),
        timeoutMs: 300,
      })
      .catch((error: unknown) => error);
    const provided = await fixture.provider.next();

    expect(String(await pending)).toContain("timed out");
    await provided.abandoned.promise;
    head.resolve();
  });

  it("cancels the hosted generation when the customer leaves mid-stream", async () => {
    const instance = await fixture.hostedCase();
    instance.runtimes[0]!.enqueue({ fault: "stall" });

    const response = await hostedStream(fixture.proxy, instance);
    for await (const line of response.lines()) {
      if (line.startsWith("data:")) break;
    }

    const settled = await instance.settled(response, { status: "cancelled" });
    expect(settled.outcome).toMatchObject({ cancellation_owner: "client" });
    await eventually(
      async () => (await inFlight(fixture.proxy, "gateway")) === 0,
      5000,
      "the gateway slot was never released",
    );
  });
});

describe("draining on SIGTERM", () => {
  it("finishes an open relay stream, refuses new connections and exits cleanly", async () => {
    const proxy = await fixture.startProxy({});
    const instance = await makeCase("vllm");
    const rest = deferred();
    fixture.provider.reply({ chunks: EVENTS, afterFirstChunk: rest });

    const response = await relayStream(proxy, instance);
    const body = readAll(response);
    await fixture.provider.next();

    proxy.signal("SIGTERM");

    await eventually(
      async () => (await proxy.readiness()) === 503,
      3000,
      "readiness never failed",
    );
    await eventually(
      () => refusesConnections(proxy),
      3000,
      "the listener stayed open",
    );
    expect(proxy.running).toBe(true);

    rest.resolve();
    expect(await body).toBe(EVENTS.join(""));
    expect(await proxy.exit(5000)).toEqual({ code: 0, signal: null });
  });

  it("finishes an open hosted request before it exits", async () => {
    const proxy = await fixture.startProxy({});
    const instance = await fixture.hostedCase();
    const gate = deferred();
    instance.runtimes[0]!.enqueue({ gate });

    const pending = proxy.client.post(CHAT.path, {
      headers: instance.headers,
      json: CHAT.body(instance.model),
    });
    await eventually(
      () => instance.runtimes[0]!.calls.length === 1,
      5000,
      "the hosted request never arrived",
    );

    proxy.signal("SIGTERM");
    await eventually(
      () => refusesConnections(proxy),
      3000,
      "the listener stayed open",
    );

    gate.resolve();
    const response = await pending;
    expect(response.status, response.text).toBe(200);
    await instance.settled(response);
    expect(await proxy.exit(5000)).toEqual({ code: 0, signal: null });
  });

  it("exits at once when idle", async () => {
    const proxy = await fixture.startProxy({});
    const started = Date.now();

    proxy.signal("SIGTERM");

    expect(await proxy.exit(3000)).toEqual({ code: 0, signal: null });
    expect(Date.now() - started).toBeLessThan(2000);
  });

  it("ends a live stream at the total deadline, then exits", async () => {
    const proxy = await fixture.startProxy({
      PROXY_TOTAL_SECONDS: "3",
      PROXY_IDLE_SECONDS: "1",
      PROXY_PROVIDER_HEADER_SECONDS: "1",
      PROXY_GATEWAY_HEADER_SECONDS: "1",
    });
    const instance = await makeCase("vllm");
    // Chunks arrive well inside the idle deadline, so only the total deadline can end it.
    fixture.provider.reply({
      chunks: [EVENTS[0]!],
      drip: { chunk: ": ping\n\n", everyMs: 200 },
    });
    const started = Date.now();

    const response = await relayStream(proxy, instance);
    const ended = new Promise<string>((resolve) => {
      response.message.on("end", () => resolve("end"));
      response.message.on("aborted", () => resolve("aborted"));
      response.message.on("error", () => resolve("aborted"));
    });
    response.message.resume();
    proxy.signal("SIGTERM");

    expect(await ended).toBe("aborted");
    const elapsed = Date.now() - started;
    expect(elapsed).toBeGreaterThan(2500);
    expect(elapsed).toBeLessThan(6000);
    expect(await proxy.exit(5000)).toEqual({ code: 0, signal: null });
  });
});
