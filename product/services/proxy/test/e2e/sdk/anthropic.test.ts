import Anthropic from "@anthropic-ai/sdk";
import { describe, expect, it } from "vitest";

import {
  useCases,
  type Case,
} from "../../../../gateway/test/integration/case.js";
import { anthropicKey, providerModel, useProxy } from "../support/fixtures.js";
import { anthropic as wire } from "../support/wire.js";

const { makeCase } = useCases();
const fixture = useProxy(makeCase);

const PROMPT = [{ role: "user" as const, content: "Synthetic ticket" }];

/** The documented integration: the customer's own key, our base URL, and the Gradiated key beside it. */
const relayClient = (instance: Case, key = anthropicKey()): Anthropic =>
  new Anthropic({
    apiKey: key,
    baseURL: fixture.proxy.url,
    defaultHeaders: { "x-gradiated-api-key": instance.key },
    maxRetries: 0,
  });

/** A hosted-only customer: the Gradiated key is the SDK's own key. */
const hostedClient = (instance: Case): Anthropic =>
  new Anthropic({
    apiKey: instance.key,
    baseURL: fixture.proxy.url,
    maxRetries: 0,
  });

describe("Anthropic SDK through the relay", () => {
  it("keeps a subscription OAuth token in the Authorization header", async () => {
    const instance = await makeCase("vllm");
    const model = providerModel("anthropic");
    const token = `sk-ant-oat01-${crypto.randomUUID().replaceAll("-", "")}`;
    fixture.provider.reply({ body: wire.message(model, "Relayed answer") });
    const client = new Anthropic({
      apiKey: null,
      authToken: token,
      baseURL: fixture.proxy.url,
      defaultHeaders: {
        "x-gradiated-api-key": instance.key,
        "anthropic-beta": "oauth-2025-04-20",
      },
      maxRetries: 0,
    });

    const message = await client.messages.create({
      model,
      max_tokens: 16,
      messages: PROMPT,
    });

    expect(message.content).toEqual([{ type: "text", text: "Relayed answer" }]);
    const [sent] = fixture.provider.requests;
    expect(sent!.headers.authorization).toBe(`Bearer ${token}`);
    expect(sent!.headers).not.toHaveProperty("x-api-key");
    expect(sent!.headers["anthropic-beta"]).toBe("oauth-2025-04-20");
  });

  it("creates a message with the customer's key", async () => {
    const instance = await makeCase("vllm");
    const model = providerModel("anthropic");
    const key = anthropicKey();
    fixture.provider.reply({ body: wire.message(model, "Relayed answer") });

    const message = await relayClient(instance, key).messages.create({
      model,
      max_tokens: 16,
      messages: PROMPT,
    });

    expect(message.content).toEqual([{ type: "text", text: "Relayed answer" }]);
    expect(message.usage).toMatchObject({ input_tokens: 12, output_tokens: 3 });
    const [sent] = fixture.provider.requests;
    expect(sent!.headers["x-api-key"]).toBe(key);
    expect(sent!.headers["anthropic-version"]).toBeTruthy();
    expect(JSON.parse(sent!.body.toString())).toMatchObject({
      model,
      max_tokens: 16,
      messages: PROMPT,
    });
    await instance.expectNotDispatched();
  });

  it("streams a message event by event", async () => {
    const instance = await makeCase("vllm");
    const model = providerModel("anthropic");
    fixture.provider.reply({
      chunks: wire.stream(model, ["Rel", "ayed ", "stream ✓"]),
    });

    const deltas: string[] = [];
    const stream = relayClient(instance).messages.stream({
      model,
      max_tokens: 16,
      messages: PROMPT,
    });
    stream.on("text", (text) => deltas.push(text));
    const message = await stream.finalMessage();

    expect(deltas).toEqual(["Rel", "ayed ", "stream ✓"]);
    expect(message.content).toMatchObject([
      { type: "text", text: "Relayed stream ✓" },
    ]);
    expect(message.stop_reason).toBe("end_turn");
  });

  it("counts tokens", async () => {
    const instance = await makeCase("vllm");
    fixture.provider.reply({ body: wire.tokenCount(42) });

    const count = await relayClient(instance).messages.countTokens({
      model: providerModel("anthropic"),
      messages: PROMPT,
    });

    expect(count.input_tokens).toBe(42);
    expect(fixture.provider.requests[0]!.path).toBe(
      "/v1/messages/count_tokens",
    );
  });

  it("reaches a beta endpoint with its query and beta header", async () => {
    const instance = await makeCase("vllm");
    const model = providerModel("anthropic");
    fixture.provider.reply({ body: wire.message(model, "Beta") });

    await relayClient(instance).beta.messages.create({
      model,
      max_tokens: 16,
      messages: PROMPT,
      betas: ["context-management-2025-06-27"],
    });

    const [sent] = fixture.provider.requests;
    expect(sent!.path).toBe("/v1/messages?beta=true");
    expect(sent!.headers["anthropic-beta"]).toBe(
      "context-management-2025-06-27",
    );
  });

  it.each([
    {
      status: 400,
      type: "invalid_request_error",
      error: Anthropic.BadRequestError,
    },
    {
      status: 401,
      type: "authentication_error",
      error: Anthropic.AuthenticationError,
    },
    { status: 404, type: "not_found_error", error: Anthropic.NotFoundError },
    { status: 429, type: "rate_limit_error", error: Anthropic.RateLimitError },
    { status: 500, type: "api_error", error: Anthropic.InternalServerError },
    {
      status: 529,
      type: "overloaded_error",
      error: Anthropic.InternalServerError,
    },
  ])(
    "raises the SDK's own error for a provider $status",
    async ({ status, type, error }) => {
      const instance = await makeCase("vllm");
      fixture.provider.reply({
        status,
        body: wire.error(type, "Synthetic provider error"),
      });

      const failure = await relayClient(instance)
        .messages.create({
          model: providerModel("anthropic"),
          max_tokens: 16,
          messages: PROMPT,
        })
        .catch((caught: unknown) => caught);

      expect(failure).toBeInstanceOf(error);
      expect(failure).toMatchObject({
        status,
        error: {
          type: "error",
          error: { type, message: "Synthetic provider error" },
        },
      });
    },
  );

  it.each([
    {
      name: "an unknown Gradiated key",
      gradiated: () => `grad_${"0".repeat(32)}`,
      status: 401,
      error: Anthropic.AuthenticationError,
    },
    {
      name: "an archived workspace",
      gradiated: undefined,
      status: 403,
      error: Anthropic.PermissionDeniedError,
    },
  ])(
    "raises the SDK's own error when the proxy refuses $name",
    async ({ gradiated, status, error }) => {
      const instance = await makeCase("vllm");
      if (!gradiated) await instance.setTenant({ workspaceArchived: true });
      const client = new Anthropic({
        apiKey: anthropicKey(),
        baseURL: fixture.proxy.url,
        defaultHeaders: {
          "x-gradiated-api-key": gradiated ? gradiated() : instance.key,
        },
        maxRetries: 0,
      });

      const failure = await client.messages
        .create({
          model: providerModel("anthropic"),
          max_tokens: 16,
          messages: PROMPT,
        })
        .catch((caught: unknown) => caught);

      expect(failure).toBeInstanceOf(error);
      expect(failure).toMatchObject({ status });
      expect(fixture.provider.requests).toEqual([]);
    },
  );
});

describe("Anthropic SDK against a hosted model", () => {
  it("creates a message served and billed by the gateway", async () => {
    const instance = await fixture.hostedCase();

    const message = await hostedClient(instance).messages.create({
      model: instance.model,
      max_tokens: 16,
      messages: PROMPT,
    });

    expect(message.type).toBe("message");
    expect(message.content[0]).toMatchObject({ type: "text" });
    expect(fixture.provider.requests).toEqual([]);
    expect(await instance.settlements()).toHaveLength(1);
  });

  it("streams a message served by the gateway", async () => {
    const instance = await fixture.hostedCase();

    const stream = hostedClient(instance).messages.stream({
      model: instance.model,
      max_tokens: 16,
      messages: PROMPT,
    });
    const message = await stream.finalMessage();

    expect(message.content.length).toBeGreaterThan(0);
    expect(fixture.provider.requests).toEqual([]);
    expect(await instance.settlements()).toHaveLength(1);
  });

  it("never lets the customer's Anthropic key reach the hosted runtime", async () => {
    const instance = await fixture.hostedCase();
    const key = anthropicKey();

    await relayClient(instance, key).messages.create({
      model: instance.model,
      max_tokens: 16,
      messages: PROMPT,
    });

    expect(fixture.provider.requests).toEqual([]);
    const forwarded = JSON.stringify(instance.runtimes[0]!.headers);
    expect(forwarded).not.toContain(key);
    expect(await instance.settlements()).toHaveLength(1);
  });
});
