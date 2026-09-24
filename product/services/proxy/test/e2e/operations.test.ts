import { describe, expect, it } from "vitest";

import { expectPublicError } from "../../../gateway/test/integration/assertions.js";
import { useCases } from "../../../gateway/test/integration/case.js";
import {
  anthropicKey,
  CHAT,
  MESSAGES,
  openAiKey,
  providerKeyHeaders,
  providerModel,
  RELAY_ROUTES,
  relayHeaders,
  useProxy,
} from "./support/fixtures.js";

const { makeCase } = useCases();
const fixture = useProxy(makeCase);

describe("relay kill switch", () => {
  it.each(RELAY_ROUTES)(
    "sends $name to the gateway instead of the provider",
    async (route) => {
      const proxy = await fixture.startProxy({ PROXY_RELAY_ENABLED: "false" });
      const instance = await makeCase("vllm");

      const response = await proxy.client.post(route.path, {
        headers: relayHeaders(instance, route.provider),
        json: route.body(providerModel(route.provider)),
      });

      expectPublicError(response, { code: "model_not_found", param: "model" });
      expect(fixture.provider.requests).toEqual([]);
      expect(await proxy.responses("gateway")).toBe(1);
    },
  );

  it("keeps serving hosted models", async () => {
    const proxy = await fixture.startProxy({ PROXY_RELAY_ENABLED: "false" });
    const instance = await fixture.hostedCase();

    const response = await proxy.client.post(CHAT.path, {
      headers: instance.headers,
      json: CHAT.body(instance.model),
    });

    expect(response.status, response.text).toBe(200);
    await instance.settled(response);
  });
});

describe("telemetry", () => {
  it("never exposes keys, tenants or model names in metrics or logs", async () => {
    const instance = await fixture.hostedCase();
    const secrets = { anthropic: anthropicKey(), openai: openAiKey() };
    const models = {
      anthropic: providerModel("anthropic"),
      openai: providerModel("openai"),
    };

    for (const route of [MESSAGES, CHAT]) {
      await fixture.proxy.client.post(route.path, {
        headers: {
          ...providerKeyHeaders(route.provider, secrets[route.provider]),
          "x-gradiated-api-key": instance.key,
        },
        json: route.body(models[route.provider]),
      });
      await fixture.proxy.client.post(route.path, {
        headers: instance.headers,
        json: route.body(instance.model),
      });
    }
    await instance.settlements();

    const metrics = (await fixture.proxy.admin.get("/metrics")).text;
    const log = await fixture.proxy.log();
    for (const secret of [secrets.anthropic, secrets.openai, instance.key]) {
      expect(metrics).not.toContain(secret);
      expect(log).not.toContain(secret);
    }
    for (const value of [
      models.anthropic,
      models.openai,
      instance.model,
      instance.workspace,
      instance.organization,
    ]) {
      expect(metrics).not.toContain(value);
    }
  });

  it("counts responses by destination and status", async () => {
    const instance = await fixture.hostedCase();
    const series = (destination: string, status: number) =>
      fixture.proxy.count(
        "proxy_requests_total",
        `destination="${destination}",status="${status}"`,
      );
    const before = await Promise.all([
      series("anthropic", 429),
      series("gateway", 200),
      series("local", 401),
    ]);
    fixture.provider.reply({ status: 429, body: "{}" });

    await fixture.proxy.client.post(MESSAGES.path, {
      headers: relayHeaders(instance, "anthropic"),
      json: MESSAGES.body(providerModel("anthropic")),
    });
    await fixture.proxy.client.post(CHAT.path, {
      headers: instance.headers,
      json: CHAT.body(instance.model),
    });
    await fixture.proxy.client.post(MESSAGES.path, {
      headers: providerKeyHeaders("anthropic", anthropicKey()),
      json: MESSAGES.body(providerModel("anthropic")),
    });

    const after = await Promise.all([
      series("anthropic", 429),
      series("gateway", 200),
      series("local", 401),
    ]);
    expect(after.map((value, index) => value - before[index]!)).toEqual([
      1, 1, 1,
    ]);
  });

  it("logs each relay with its tenant and a unique generation ID", async () => {
    const instance = await makeCase("vllm");

    const responses = await Promise.all(
      [0, 1].map(() =>
        fixture.proxy.client.post(MESSAGES.path, {
          headers: relayHeaders(instance, "anthropic"),
          json: MESSAGES.body(providerModel("anthropic")),
        }),
      ),
    );
    const ids = responses.map(
      (response) => response.headers["x-generation-id"],
    );

    expect(new Set(ids).size).toBe(2);
    const relays = (await fixture.proxy.log())
      .split("\n")
      .filter((line) => line.includes('"event":"provider_relay"'))
      .map((line) => JSON.parse(line) as { fields: Record<string, unknown> });
    for (const id of ids) {
      expect(
        relays.find((entry) => entry.fields.generation_id === id)?.fields,
      ).toMatchObject({
        workspace_id: instance.workspace,
        organization_id: instance.organization,
        api_key_id: instance.credential,
        provider: "anthropic",
        provider_status: 200,
      });
    }
  });
});
