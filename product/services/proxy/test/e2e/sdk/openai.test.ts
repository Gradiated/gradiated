import OpenAI from "openai";
import { describe, expect, it } from "vitest";

import {
  useCases,
  type Case,
} from "../../../../gateway/test/integration/case.js";
import { openAiKey, providerModel, useProxy } from "../support/fixtures.js";
import { openai as wire } from "../support/wire.js";

const { makeCase } = useCases();
const fixture = useProxy(makeCase);

const PROMPT = [{ role: "user" as const, content: "Synthetic ticket" }];

/** The documented integration: the customer's own key, our base URL, and the Gradiated key beside it. */
const relayClient = (instance: Case, key = openAiKey()): OpenAI =>
  new OpenAI({
    apiKey: key,
    baseURL: `${fixture.proxy.url}/v1`,
    defaultHeaders: { "x-gradiated-api-key": instance.key },
    maxRetries: 0,
  });

/** A hosted-only customer: the Gradiated key is the SDK's own key. */
const hostedClient = (instance: Case): OpenAI =>
  new OpenAI({
    apiKey: instance.key,
    baseURL: `${fixture.proxy.url}/v1`,
    maxRetries: 0,
  });

const responseEvents = (model: string, parts: readonly string[]): string[] => {
  const event = (type: string, data: object, sequence: number) =>
    `event: ${type}\ndata: ${JSON.stringify({ type, sequence_number: sequence, ...data })}\n\n`;
  const completed = JSON.parse(wire.response(model, parts.join(""))) as object;

  return [
    event(
      "response.created",
      { response: { ...completed, status: "in_progress", output: [] } },
      0,
    ),
    ...parts.map((delta, index) =>
      event(
        "response.output_text.delta",
        { item_id: "msg_synthetic", output_index: 0, content_index: 0, delta },
        index + 1,
      ),
    ),
    event("response.completed", { response: completed }, parts.length + 1),
  ];
};

describe("OpenAI SDK through the relay", () => {
  it("creates a chat completion with the customer's key", async () => {
    const instance = await makeCase("vllm");
    const model = providerModel("openai");
    const key = openAiKey();
    fixture.provider.reply({
      body: wire.chatCompletion(model, "Relayed answer"),
    });

    const completion = await relayClient(instance, key).chat.completions.create(
      { model, messages: PROMPT },
    );

    expect(completion.choices[0]!.message.content).toBe("Relayed answer");
    expect(completion.usage).toMatchObject({
      prompt_tokens: 12,
      completion_tokens: 3,
    });
    const [sent] = fixture.provider.requests;
    expect(sent!.path).toBe("/v1/chat/completions");
    expect(sent!.headers.authorization).toBe(`Bearer ${key}`);
    expect(JSON.parse(sent!.body.toString())).toMatchObject({
      model,
      messages: PROMPT,
    });
    await instance.expectNotDispatched();
  });

  it("streams a chat completion chunk by chunk", async () => {
    const instance = await makeCase("vllm");
    const model = providerModel("openai");
    fixture.provider.reply({
      chunks: wire.chatStream(model, ["Rel", "ayed ", "stream ✓"]),
    });

    const stream = await relayClient(instance).chat.completions.create({
      model,
      messages: PROMPT,
      stream: true,
    });
    const deltas: string[] = [];
    let finish: string | null = null;
    for await (const chunk of stream) {
      const [choice] = chunk.choices;
      if (choice?.delta.content) deltas.push(choice.delta.content);
      finish = choice?.finish_reason ?? finish;
    }

    expect(deltas).toEqual(["Rel", "ayed ", "stream ✓"]);
    expect(finish).toBe("stop");
  });

  it("creates a response", async () => {
    const instance = await makeCase("vllm");
    const model = providerModel("openai");
    fixture.provider.reply({ body: wire.response(model, "Relayed response") });

    const response = await relayClient(instance).responses.create({
      model,
      input: "Synthetic ticket",
    });

    expect(response.output_text).toBe("Relayed response");
    expect(fixture.provider.requests[0]!.path).toBe("/v1/responses");
  });

  it("streams a response event by event", async () => {
    const instance = await makeCase("vllm");
    const model = providerModel("openai");
    fixture.provider.reply({ chunks: responseEvents(model, ["Rel", "ayed"]) });

    const stream = await relayClient(instance).responses.create({
      model,
      input: "Synthetic ticket",
      stream: true,
    });
    const types: string[] = [];
    let text = "";
    for await (const event of stream) {
      types.push(event.type);
      if (event.type === "response.output_text.delta") text += event.delta;
    }

    expect(types).toEqual([
      "response.created",
      "response.output_text.delta",
      "response.output_text.delta",
      "response.completed",
    ]);
    expect(text).toBe("Relayed");
  });

  it("sends the organization and project headers the SDK sets", async () => {
    const instance = await makeCase("vllm");
    const model = providerModel("openai");
    fixture.provider.reply({ body: wire.chatCompletion(model, "ok") });
    const client = new OpenAI({
      apiKey: openAiKey(),
      organization: "org_synthetic",
      project: "proj_synthetic",
      baseURL: `${fixture.proxy.url}/v1`,
      defaultHeaders: { "x-gradiated-api-key": instance.key },
      maxRetries: 0,
    });

    await client.chat.completions.create({ model, messages: PROMPT });

    expect(fixture.provider.requests[0]!.headers).toMatchObject({
      "openai-organization": "org_synthetic",
      "openai-project": "proj_synthetic",
    });
  });

  it.each([
    {
      status: 400,
      type: "invalid_request_error",
      code: "invalid_value",
      error: OpenAI.BadRequestError,
    },
    {
      status: 401,
      type: "invalid_request_error",
      code: "invalid_api_key",
      error: OpenAI.AuthenticationError,
    },
    {
      status: 404,
      type: "invalid_request_error",
      code: "model_not_found",
      error: OpenAI.NotFoundError,
    },
    {
      status: 429,
      type: "insufficient_quota",
      code: "insufficient_quota",
      error: OpenAI.RateLimitError,
    },
    {
      status: 500,
      type: "server_error",
      code: "server_error",
      error: OpenAI.InternalServerError,
    },
    {
      status: 503,
      type: "server_error",
      code: "overloaded",
      error: OpenAI.InternalServerError,
    },
  ])(
    "raises the SDK's own error for a provider $status",
    async ({ status, type, code, error }) => {
      const instance = await makeCase("vllm");
      fixture.provider.reply({
        status,
        body: wire.error(type, code, "Synthetic provider error"),
        headers: { "x-request-id": "req_synthetic" },
      });

      const failure = await relayClient(instance)
        .chat.completions.create({
          model: providerModel("openai"),
          messages: PROMPT,
        })
        .catch((caught: unknown) => caught);

      expect(failure).toBeInstanceOf(error);
      expect(failure).toMatchObject({
        status,
        code,
        type,
        requestID: "req_synthetic",
      });
    },
  );

  it.each([
    {
      name: "an unknown Gradiated key",
      suspend: false,
      status: 401,
      code: "invalid_api_key",
      error: OpenAI.AuthenticationError,
    },
    {
      name: "a suspended organization",
      suspend: true,
      status: 403,
      code: "organization_suspended",
      error: OpenAI.PermissionDeniedError,
    },
  ])(
    "raises the SDK's own error when the proxy refuses $name",
    async ({ suspend, status, code, error }) => {
      const instance = await makeCase("vllm");
      if (suspend)
        await instance.setTenant({ organizationStatus: "suspended" });
      const client = new OpenAI({
        apiKey: openAiKey(),
        baseURL: `${fixture.proxy.url}/v1`,
        defaultHeaders: {
          "x-gradiated-api-key": suspend
            ? instance.key
            : `grad_${"0".repeat(32)}`,
        },
        maxRetries: 0,
      });

      const failure = await client.chat.completions
        .create({ model: providerModel("openai"), messages: PROMPT })
        .catch((caught: unknown) => caught);

      expect(failure).toBeInstanceOf(error);
      expect(failure).toMatchObject({ status, code });
      expect(fixture.provider.requests).toEqual([]);
    },
  );
});

describe("OpenAI SDK against a hosted model", () => {
  it("creates a chat completion served and billed by the gateway", async () => {
    const instance = await fixture.hostedCase();

    const completion = await hostedClient(instance).chat.completions.create({
      model: instance.model,
      messages: PROMPT,
    });

    expect(completion.choices[0]!.message.role).toBe("assistant");
    expect(fixture.provider.requests).toEqual([]);
    expect(await instance.settlements()).toHaveLength(1);
  });

  it("streams a chat completion served by the gateway", async () => {
    const instance = await fixture.hostedCase();

    const stream = await hostedClient(instance).chat.completions.create({
      model: instance.model,
      messages: PROMPT,
      stream: true,
    });
    let text = "";
    for await (const chunk of stream)
      text += chunk.choices[0]?.delta.content ?? "";

    expect(text.length).toBeGreaterThan(0);
    expect(fixture.provider.requests).toEqual([]);
    expect(await instance.settlements()).toHaveLength(1);
  });

  it("lists the hosted model", async () => {
    const instance = await fixture.hostedCase();

    const ids: string[] = [];
    for await (const model of hostedClient(instance).models.list())
      ids.push(model.id);

    expect(ids).toContain(instance.model);
  });

  it("never lets the customer's OpenAI key reach the hosted runtime", async () => {
    const instance = await fixture.hostedCase();
    const key = openAiKey();

    await relayClient(instance, key).chat.completions.create({
      model: instance.model,
      messages: PROMPT,
    });

    expect(fixture.provider.requests).toEqual([]);
    expect(JSON.stringify(instance.runtimes[0]!.headers)).not.toContain(key);
    expect(await instance.settlements()).toHaveLength(1);
  });
});
