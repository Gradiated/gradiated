import { describe, expect, it } from "vitest";

import { useCases, type Case } from "../../../gateway/test/integration/case.js";
import { eventually } from "../../../gateway/test/integration/eventually.js";
import type { LinkState } from "./support/link.js";
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
const fixture = useProxy(makeCase, { databaseLink: true, gatewayLink: true });

/** Two seconds of query timeout plus scheduling margin. */
const OUTAGE_ANSWER_MS = 4000;

const relay = (instance: Case, proxy: ProxyProcess = fixture.proxy) =>
  proxy.client.post(MESSAGES.path, {
    headers: relayHeaders(instance, "anthropic"),
    json: MESSAGES.body(providerModel("anthropic")),
  });

const timed = async <T>(
  work: () => Promise<T>,
): Promise<{ value: T; elapsed: number }> => {
  const started = Date.now();
  const value = await work();

  return { value, elapsed: Date.now() - started };
};

const OUTAGES: LinkState[] = ["refusing", "silent"];

describe("database outage", () => {
  it.each(OUTAGES)(
    "keeps relaying for a key it has already seen while the database is %s",
    async (state) => {
      const instance = await makeCase("vllm");
      expect((await relay(instance)).status).toBe(200);
      const staleBefore = await fixture.proxy.count(
        "proxy_identity_lookups_total",
        'result="stale"',
      );

      fixture.database.set(state);

      // Only a lookup past the fresh lifetime proves the stale path, so relay until one is recorded.
      await eventually(
        async () => {
          const { value, elapsed } = await timed(() => relay(instance));
          expect(value.status, value.text).toBe(200);
          expect(elapsed).toBeLessThan(OUTAGE_ANSWER_MS);
          return (
            (await fixture.proxy.count(
              "proxy_identity_lookups_total",
              'result="stale"',
            )) > staleBefore
          );
        },
        10_000,
        "no stale identity was served",
      );
    },
  );

  it.each(OUTAGES)(
    "refuses an unseen key quickly while the database is %s",
    async (state) => {
      const instance = await makeCase("vllm");
      fixture.database.set(state);

      const { value: response, elapsed } = await timed(() => relay(instance));

      expectProxyError(response, "serving_state_unavailable", "anthropic");
      expect(elapsed).toBeLessThan(OUTAGE_ANSWER_MS);
      expect(fixture.provider.requests).toEqual([]);
    },
  );

  it("stops serving a stale key once the grace ends", async () => {
    const instance = await makeCase("vllm");
    const proxy = await fixture.startProxy(
      { PROXY_IDENTITY_STALE_GRACE_SECONDS: "2" },
      { database: fixture.database },
    );
    expect((await relay(instance, proxy)).status).toBe(200);

    fixture.database.set("refusing");

    const refused = await eventually(
      async () => {
        const response = await relay(instance, proxy);
        return response.status === 503 ? response : undefined;
      },
      6000,
      "the stale key was served past its grace",
    );
    expectProxyError(refused, "serving_state_unavailable", "anthropic");
  });

  it("authenticates unseen keys again once the database recovers", async () => {
    const instance = await makeCase("vllm");
    fixture.database.set("refusing");
    expect((await relay(instance)).status).toBe(503);

    fixture.database.set("up");

    await eventually(
      async () => (await relay(instance)).status === 200,
      5000,
      "the key never authenticated",
    );
  });

  it("serves hosted traffic and stays ready without its database", async () => {
    const instance = await fixture.hostedCase();
    fixture.database.set("refusing");

    const response = await fixture.proxy.client.post(CHAT.path, {
      headers: instance.headers,
      json: CHAT.body(instance.model),
    });

    expect(response.status, response.text).toBe(200);
    await instance.settled(response);
    expect(await fixture.proxy.readiness()).toBe(200);
  });

  it("keeps routing hosted models to the gateway after a failed catalog refresh", async () => {
    const instance = await fixture.hostedCase();
    const failures = await fixture.proxy.count(
      "proxy_catalog_refresh_failures_total",
    );

    fixture.database.set("refusing");
    await eventually(
      async () =>
        (await fixture.proxy.count("proxy_catalog_refresh_failures_total")) >
        failures,
      5000,
      "no catalog refresh failed",
    );

    const response = await fixture.proxy.client.post(MESSAGES.path, {
      headers: relayHeaders(instance, "anthropic"),
      json: MESSAGES.body(instance.model),
    });

    expect(response.status, response.text).toBe(200);
    await instance.settled(response);
    expect(fixture.provider.requests).toEqual([]);
  });

  it("stays unready until its first catalog load succeeds", async () => {
    fixture.database.set("refusing");
    const proxy = await fixture.startProxy(
      {},
      { database: fixture.database, ready: false },
    );

    await eventually(
      async () =>
        (await proxy.count("proxy_catalog_refresh_failures_total")) >= 2,
      8000,
    );
    expect(await proxy.readiness()).toBe(503);

    fixture.database.set("up");
    await proxy.ready();
  });
});

describe("gateway outage", () => {
  it.each([
    {
      name: "with only a Gradiated key",
      provider: undefined,
      format: "openai" as const,
    },
    {
      name: "with an Anthropic key",
      provider: "anthropic" as const,
      format: "anthropic" as const,
    },
    {
      name: "with an OpenAI key",
      provider: "openai" as const,
      format: "openai" as const,
    },
  ])(
    "answers a hosted request $name with gateway_unavailable in the key's format",
    async ({ provider, format }) => {
      const instance = await fixture.hostedCase();
      fixture.gateway.set("refusing");

      const response = await fixture.proxy.client.post(MESSAGES.path, {
        headers: provider ? relayHeaders(instance, provider) : instance.headers,
        json: MESSAGES.body(instance.model),
      });

      expectProxyError(response, "gateway_unavailable", format);
      await instance.expectNotDispatched();
    },
  );

  it.each(OUTAGES)("keeps relaying while the gateway is %s", async (state) => {
    const instance = await makeCase("vllm");
    fixture.gateway.set(state);

    const response = await relay(instance);

    expect(response.status, response.text).toBe(200);
    expect(fixture.provider.requests).toHaveLength(1);
  });

  it("times out a hung gateway at the header deadline", async () => {
    const instance = await fixture.hostedCase();
    const proxy = await fixture.startProxy(
      { PROXY_GATEWAY_HEADER_SECONDS: "1" },
      { gateway: fixture.gateway },
    );
    fixture.gateway.set("silent");

    const { value: response, elapsed } = await timed(() =>
      proxy.client.post(CHAT.path, {
        headers: instance.headers,
        json: CHAT.body(instance.model),
      }),
    );

    expectProxyError(response, "gateway_timeout");
    expect(elapsed).toBeLessThan(3000);
  });

  it("ends a hosted stream abnormally when the gateway dies mid-stream", async () => {
    const instance = await fixture.hostedCase();
    instance.runtimes[0]!.enqueue({ fault: "stall" });

    const response = await fixture.proxy.client.stream(CHAT.path, {
      headers: instance.headers,
      json: { ...CHAT.body(instance.model), stream: true },
    });
    const ended = new Promise<"end" | "aborted">((resolve) => {
      response.message.on("end", () => resolve("end"));
      response.message.on("aborted", () => resolve("aborted"));
      response.message.on("error", () => resolve("aborted"));
    });
    response.message.once("data", () => fixture.gateway.set("refusing"));
    response.message.resume();

    // A clean end would tell the SDK the answer was complete.
    expect(await ended).toBe("aborted");
    await instance.settled(response, { status: "cancelled" });
  });
});
