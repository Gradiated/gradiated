import Anthropic from "@anthropic-ai/sdk";
import { describe, expect, it } from "vitest";

import { useCases, type Case } from "./case.js";
import { chatMessages, chatSdk } from "./chat.js";
import { isJsonObject, object, type JsonObject } from "./json.js";

const { makeCase } = useCases();

const readCost = (usage: unknown): number => {
  if (
    !isJsonObject(usage) ||
    typeof usage.cost !== "number" ||
    !Number.isFinite(usage.cost) ||
    usage.cost < 0
  ) {
    throw new Error("SDK usage must preserve a finite, nonnegative cost");
  }

  return usage.cost;
};

const headerRecord = (response: Response): Record<string, string> => {
  const headers: Record<string, string> = {};
  response.headers.forEach((value, key) => {
    headers[key] = value;
  });

  return headers;
};

const anthropicSdk = (instance: Case): Anthropic =>
  new Anthropic({
    apiKey: instance.key,
    baseURL: instance.http.baseUrl.replace(/\/$/, ""),
    maxRetries: 0,
    timeout: 5000,
  });

const firstModality = (instance: Case, field: string): JsonObject => {
  const modalities = instance.record.properties[field];
  if (!Array.isArray(modalities)) throw new Error("expected modalities");

  return object(modalities[0]);
};

const CASES = [
  { name: "cached input", cached: 40, tier: "default", charge: 740 },
  { name: "flex tier", cached: 100, tier: "flex", charge: 142 },
  { name: "fast tier", cached: 0, tier: "fast", charge: 1590 },
  { name: "free model", cached: 40, tier: "default", charge: 0 },
  {
    name: "cache writes and reasoning",
    cached: 40,
    tier: "default",
    charge: 810,
  },
] as const;

describe.each(CASES)("SDK pricing: $name", (scenario) => {
  const prepare = async (stream: boolean): Promise<Case> => {
    const instance = await makeCase("vllm");
    const input = firstModality(instance, "input_modalities");
    const output = firstModality(instance, "output_modalities");

    if (scenario.name === "free model") {
      input.pricing = [
        { type: "prompt", unit: "token", cost: 0 },
        { type: "cached_prompt", unit: "token", cost: 0 },
      ];
      output.pricing = [{ type: "completion", unit: "token", cost: 0 }];
      await instance.publish();
    }

    if (scenario.name === "cache writes and reasoning") {
      input.pricing = [
        { type: "prompt", unit: "token", cost: 10 },
        { type: "cached_prompt", unit: "token", cost: 2 },
        { type: "cache_write", unit: "token", cost: 3 },
      ];
      output.pricing = [
        { type: "completion", unit: "token", cost: 20 },
        { type: "internal_reasoning", unit: "token", cost: 40 },
      ];
      await instance.publish();
    }

    const details = (body: JsonObject): void => {
      if (scenario.name !== "cache writes and reasoning") return;

      const usage = object(body.usage);
      object(usage.prompt_tokens_details).cache_write_tokens = 10;
      usage.completion_tokens_details = { reasoning_tokens: 2 };
    };
    instance.runtimes[0]!.enqueue({
      cached: scenario.cached,
      ...(stream
        ? {
            mutateEvents: (events) => {
              for (const event of events) {
                if (isJsonObject(event) && isJsonObject(event.usage))
                  details(event);
              }
            },
          }
        : { mutateBody: details }),
    });

    return instance;
  };

  const verify = async (
    instance: Case,
    usage: unknown,
    response: Response,
    protocol: "chat" | "responses" | "messages",
  ): Promise<void> => {
    const writes = scenario.name === "cache writes and reasoning" ? 10 : 0;
    const reasoning = scenario.name === "cache writes and reasoning" ? 2 : 0;
    const expected =
      protocol === "chat"
        ? {
            prompt_tokens: 100,
            completion_tokens: 3,
            total_tokens: 103,
            prompt_tokens_details: {
              cached_tokens: scenario.cached,
              ...(writes ? { cache_write_tokens: writes } : {}),
            },
            completion_tokens_details: { reasoning_tokens: reasoning },
          }
        : protocol === "responses"
          ? {
              input_tokens: 100,
              output_tokens: 3,
              total_tokens: 103,
              input_tokens_details: {
                cached_tokens: scenario.cached,
                ...(writes ? { cache_write_tokens: writes } : {}),
              },
              output_tokens_details: { reasoning_tokens: reasoning },
            }
          : {
              input_tokens: 100 - scenario.cached - writes,
              output_tokens: 3,
              cache_read_input_tokens: scenario.cached,
              ...(writes ? { cache_creation_input_tokens: writes } : {}),
              ...(reasoning
                ? { output_tokens_details: { thinking_tokens: reasoning } }
                : {}),
            };
    expect(usage).toMatchObject(expected);
    expect(readCost(usage)).toBe(scenario.charge / 1_000_000_000);
    const settled = await instance.settled(
      { headers: headerRecord(response) },
      { charge: scenario.charge },
    );
    expect(readCost(usage)).toBe(
      Number(object(settled.usage).charge) / 1_000_000_000,
    );
  };

  it.each([false, true])(
    "OpenAI Chat Completions (stream=%s)",
    async (streaming) => {
      const instance = await prepare(streaming);
      const request = {
        model: instance.model,
        messages: chatMessages(),
        service_tier: scenario.tier,
      };
      if (!streaming) {
        const { data, response } = await chatSdk(instance)
          .chat.completions.create(request)
          .withResponse();
        expect(data.choices[0]!.message.content).toBe("Synthetic answer");
        expect(data.usage?.prompt_tokens).toBe(100);
        await verify(instance, data.usage, response, "chat");
        return;
      }

      const { data: stream, response } = await chatSdk(instance)
        .chat.completions.create({
          ...request,
          stream: true,
          stream_options: { include_usage: true },
        })
        .withResponse();
      const chunks = [];
      for await (const chunk of stream) chunks.push(chunk);

      const terminal = chunks.at(-1)!;
      expect(terminal.choices).toEqual([]);
      expect(terminal.usage?.total_tokens).toBe(103);
      expect(chunks.slice(0, -1).every((chunk) => chunk.usage == null)).toBe(
        true,
      );
      await verify(instance, terminal.usage, response, "chat");
    },
  );

  it.each([false, true])("OpenAI Responses (stream=%s)", async (streaming) => {
    const instance = await prepare(streaming);
    const request = {
      model: instance.model,
      input: "Synthetic billing ticket",
      store: false,
      service_tier: scenario.tier,
    };
    if (!streaming) {
      const { data, response } = await chatSdk(instance)
        .responses.create(request)
        .withResponse();
      expect(data.output_text).toBe("Synthetic answer");
      expect(data.usage?.input_tokens_details.cached_tokens).toBe(
        scenario.cached,
      );
      await verify(instance, data.usage, response, "responses");
      return;
    }

    const { data: stream, response } = await chatSdk(instance)
      .responses.create({ ...request, stream: true })
      .withResponse();
    const events = [];
    for await (const event of stream) events.push(event);

    const terminal = events.at(-1)!;
    expect(terminal.type).toBe("response.completed");
    if (terminal.type !== "response.completed")
      throw new Error("missing final response");

    expect(terminal.response.usage?.total_tokens).toBe(103);
    await verify(instance, terminal.response.usage, response, "responses");
  });

  it.each([false, true])(
    "Anthropic Messages (stream=%s)",
    async (streaming) => {
      const instance = await prepare(streaming);
      const request = {
        model: instance.model,
        messages: [
          { role: "user" as const, content: "Synthetic billing ticket" },
        ],
        max_tokens: 16,
      };
      // The SDK types restrict service_tier to native values; the raw body sends gateway tiers.
      const options = { body: { ...request, service_tier: scenario.tier } };
      if (!streaming) {
        const { data, response } = await anthropicSdk(instance)
          .messages.create(request, options)
          .withResponse();
        expect(data.usage.cache_read_input_tokens).toBe(scenario.cached);
        expect(data.usage.output_tokens).toBe(3);
        await verify(instance, data.usage, response, "messages");
        return;
      }

      const { data: stream, response } = await anthropicSdk(instance)
        .messages.create(
          { ...request, stream: true },
          { body: { ...options.body, stream: true } },
        )
        .withResponse();
      const events = [];
      for await (const event of stream) events.push(event);

      expect(events.at(-1)?.type).toBe("message_stop");
      const terminal = events.find((event) => event.type === "message_delta");
      if (!terminal || terminal.type !== "message_delta")
        throw new Error("missing final usage");

      expect(terminal.usage.output_tokens).toBe(3);
      await verify(instance, terminal.usage, response, "messages");
    },
  );
});

describe("SDK stream helpers", () => {
  it("reads cost from the OpenAI final chat completion", async () => {
    const instance = await makeCase("vllm");
    instance.runtimes[0]!.enqueue({ cached: 40 });
    const stream = chatSdk(instance).chat.completions.stream({
      model: instance.model,
      messages: chatMessages(),
      stream_options: { include_usage: true },
    });

    const final = await stream.finalChatCompletion();
    expect(readCost(final.usage)).toBe(0.00000074);
    const settlements = await instance.settlements();
    expect(settlements).toHaveLength(1);
    expect(object(settlements[0]!.properties.usage).charge).toBe(740);
  });

  it("reads cost from the OpenAI final response", async () => {
    const instance = await makeCase("vllm");
    instance.runtimes[0]!.enqueue({ cached: 40 });
    const stream = chatSdk(instance).responses.stream({
      model: instance.model,
      input: "Synthetic billing ticket",
      store: false,
    });

    const final = await stream.finalResponse();
    expect(readCost(final.usage)).toBe(0.00000074);
    const settlements = await instance.settlements();
    expect(settlements).toHaveLength(1);
    expect(object(settlements[0]!.properties.usage).charge).toBe(740);
  });

  it("reads cost from Anthropic streamEvent when finalMessage keeps only native usage fields", async () => {
    const instance = await makeCase("vllm");
    instance.runtimes[0]!.enqueue({ cached: 40 });
    const stream = anthropicSdk(instance).messages.stream({
      model: instance.model,
      messages: [{ role: "user", content: "Synthetic billing ticket" }],
      max_tokens: 16,
    });
    let terminalUsage: unknown;
    stream.on("streamEvent", (event) => {
      if (event.type === "message_delta") terminalUsage = event.usage;
    });

    const final = await stream.finalMessage();
    expect(final.usage.cache_read_input_tokens).toBe(40);
    expect(final.usage).not.toHaveProperty("cost");
    expect(readCost(terminalUsage)).toBe(0.00000074);
    const { response } = await stream.withResponse();
    await instance.settled(
      { headers: headerRecord(response) },
      { charge: 740 },
    );
  });
});
