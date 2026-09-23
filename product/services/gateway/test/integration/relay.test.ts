import { describe, expect, it } from "vitest";

import { expectRejected, type Rejection } from "./assertions.js";
import { useCases, type Case } from "./case.js";
import type { Headers } from "./http-client.js";

const { makeCase } = useCases();

const secret = (prefix: string): string =>
  `${prefix}${crypto.randomUUID().replaceAll("-", "")}`;

const unhostedModel = (): string => `claude-${crypto.randomUUID()}`;

const messagesBody = (model: string) => ({
  model,
  max_tokens: 16,
  messages: [{ role: "user", content: "Synthetic ticket" }],
});

// The shared gateway relays Anthropic traffic to a closed loopback port, so a
// relayed request fails as provider_unavailable without leaving the host.
describe("customer-key relay", () => {
  it.each<{
    request: string;
    path: string;
    headers: (instance: Case) => Promise<Headers>;
    rejection: Rejection;
  }>([
    {
      request: "an Anthropic key for an unhosted model",
      path: "/v1/messages",
      headers: async (instance) => ({
        "x-gradiated-api-key": instance.key,
        "x-api-key": secret("sk-ant-"),
      }),
      rejection: { code: "provider_unavailable" },
    },
    {
      request: "an Anthropic key beside a revoked Gradiated key",
      path: "/v1/messages",
      headers: async (instance) => {
        await instance.setCredential({ revokedAt: new Date() });
        return {
          "x-gradiated-api-key": instance.key,
          "x-api-key": secret("sk-ant-"),
        };
      },
      rejection: { code: "invalid_api_key" },
    },
    {
      request: "an Anthropic key without a Gradiated key",
      path: "/v1/messages",
      headers: async () => ({ "x-api-key": secret("sk-ant-") }),
      rejection: { code: "invalid_api_key" },
    },
    {
      request: "an OpenAI key on the Anthropic route",
      path: "/v1/messages",
      headers: async (instance) => ({
        "x-gradiated-api-key": instance.key,
        "x-api-key": secret("sk-"),
      }),
      rejection: { code: "invalid_api_key" },
    },
    {
      request: "a provider key on a route without a relay",
      path: "/v1/chat/completions",
      headers: async (instance) => ({
        "x-gradiated-api-key": instance.key,
        "x-api-key": secret("sk-"),
      }),
      rejection: { code: "model_not_found", param: "model" },
    },
  ])(
    "rejects $request without hosted dispatch",
    async ({ path, headers, rejection }) => {
      const instance = await makeCase("vllm");

      const response = await instance.http.post(path, {
        headers: await headers(instance),
        json: messagesBody(unhostedModel()),
      });

      expectRejected(response, rejection);
      if (path === "/v1/messages") expect(response.json().type).toBe("error");
      await instance.expectNotDispatched();
    },
  );

  it("serves a hosted model without forwarding the provider key", async () => {
    const instance = await makeCase("vllm");
    const providerKey = secret("sk-ant-");

    const response = await instance.http.post("/v1/messages", {
      headers: {
        "x-gradiated-api-key": instance.key,
        "x-api-key": providerKey,
      },
      json: messagesBody(instance.model),
    });

    expect(response.status, response.text).toBe(200);
    await instance.settled(response, { charge: 1060 });
    expect(await instance.settlements()).toHaveLength(1);
    const forwarded = instance.runtimes[0]!.headers.flatMap((headers) =>
      Object.values(headers).flat(),
    );
    expect(forwarded.length).toBeGreaterThan(0);
    expect(forwarded.filter((value) => value?.includes(providerKey))).toEqual(
      [],
    );
  });
});
