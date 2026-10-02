import { expect, it, vi } from "vitest";
import { createEvaluationModels } from "../src/training/evaluation-models.js";

it("uses the selected OpenAI model and counts visible output tokens", async () => {
  const send = vi.fn<typeof fetch>().mockResolvedValue(
    new Response(
      JSON.stringify({
        choices: [{ message: { content: "answer" }, finish_reason: "stop" }],
        usage: {
          completion_tokens: 15,
          completion_tokens_details: { reasoning_tokens: 10 },
        },
      }),
    ),
  );
  const models = createEvaluationModels({ OPENAI_API_KEY: "test" }, send);
  const result = await models.generate(
    "openai/gpt-6.1-sol",
    [{ role: "user", content: "test" }],
    new AbortController().signal,
  );
  expect(JSON.parse(String(send.mock.calls[0]![1]!.body))).toMatchObject({
    model: "gpt-6.1-sol",
    messages: [{ role: "user", content: "test" }],
  });
  expect(result).toMatchObject({ text: "answer", tokens: 5 });
});

it("uses the selected Anthropic model and moves system instructions to its system field", async () => {
  const send = vi.fn<typeof fetch>().mockResolvedValue(
    new Response(
      JSON.stringify({
        content: [{ type: "text", text: "TIE" }],
        stop_reason: "end_turn",
        usage: { output_tokens: 1 },
      }),
    ),
  );
  await createEvaluationModels({ ANTHROPIC_API_KEY: "test" }, send).generate(
    "anthropic/claude-sonnet-5-5",
    [
      { role: "system", content: "judge" },
      { role: "user", content: "pair" },
    ],
    new AbortController().signal,
  );
  expect(JSON.parse(String(send.mock.calls[0]![1]!.body))).toMatchObject({
    model: "claude-sonnet-5-5",
    system: "judge",
    messages: [{ role: "user", content: "pair" }],
  });
});

it("rejects missing credentials before sending data and rejects truncated answers", async () => {
  const send = vi.fn<typeof fetch>();
  const credentials = {
    load: vi
      .fn()
      .mockRejectedValue(new Error("Cannot load provider credential.")),
  };
  await expect(
    createEvaluationModels({}, send, credentials).check("openai/gpt-6.1-sol"),
  ).rejects.toThrow("credential");
  expect(send).not.toHaveBeenCalled();
  send.mockResolvedValue(
    new Response(
      JSON.stringify({
        choices: [{ message: { content: "partial" }, finish_reason: "length" }],
        usage: { completion_tokens: 4096 },
      }),
    ),
  );
  await expect(
    createEvaluationModels({ OPENAI_API_KEY: "test" }, send).generate(
      "openai/gpt-6.1-sol",
      [{ role: "user", content: "test" }],
      new AbortController().signal,
    ),
  ).rejects.toThrow();
});

it("loads production provider credentials and observes key rotation on the next request", async () => {
  const credentials = {
    load: vi
      .fn()
      .mockResolvedValueOnce("first-key")
      .mockResolvedValueOnce("rotated-key"),
  };
  const send = vi.fn<typeof fetch>().mockImplementation(
    async () =>
      new Response(
        JSON.stringify({
          choices: [{ message: { content: "answer" }, finish_reason: "stop" }],
          usage: { completion_tokens: 1 },
        }),
      ),
  );
  const models = createEvaluationModels(
    { NODE_ENV: "production", OPENAI_API_KEY: "stale-environment-key" },
    send,
    credentials,
  );
  for (let i = 0; i < 2; i++)
    await models.generate(
      "openai/gpt-6.1-sol",
      [{ role: "user", content: "test" }],
      new AbortController().signal,
    );
  expect(credentials.load.mock.calls).toEqual([["openai"], ["openai"]]);
  expect(send.mock.calls.map(([, options]) => options?.headers)).toEqual([
    { "Content-Type": "application/json", Authorization: "Bearer first-key" },
    { "Content-Type": "application/json", Authorization: "Bearer rotated-key" },
  ]);
});

it("preflights managed credentials without sending prompts", async () => {
  const credentials = { load: vi.fn().mockResolvedValue("test-key") };
  const send = vi.fn<typeof fetch>();
  const models = createEvaluationModels(
    { NODE_ENV: "production" },
    send,
    credentials,
  );
  await models.check("openai/gpt-6.1-sol");
  await models.check("anthropic/claude-sonnet-5-5");
  expect(credentials.load.mock.calls).toEqual([["openai"], ["anthropic"]]);
  expect(send).not.toHaveBeenCalled();
});
it("retains billable OpenAI output including reasoning and cached-input usage", async () => {
  const send = vi.fn<typeof fetch>().mockResolvedValue(
    new Response(
      JSON.stringify({
        choices: [{ message: { content: "answer" }, finish_reason: "stop" }],
        usage: {
          prompt_tokens: 100,
          prompt_tokens_details: { cached_tokens: 30 },
          completion_tokens: 50,
          completion_tokens_details: { reasoning_tokens: 40 },
        },
      }),
    ),
  );
  const result = await createEvaluationModels(
    { OPENAI_API_KEY: "test" },
    send,
  ).generate(
    "openai/gpt-6.1-sol",
    [{ role: "user", content: "test" }],
    new AbortController().signal,
  );
  expect(result.tokens).toBe(10);
  expect(result.usage).toEqual({
    input_tokens: 100,
    output_tokens: 50,
    cached_input_tokens: 30,
  });
});

it("normalizes Anthropic input usage including cache reads and writes", async () => {
  const send = vi.fn<typeof fetch>().mockResolvedValue(
    new Response(
      JSON.stringify({
        content: [{ type: "text", text: "answer" }],
        stop_reason: "end_turn",
        usage: {
          input_tokens: 10,
          output_tokens: 5,
          cache_read_input_tokens: 20,
          cache_creation_input_tokens: 30,
        },
      }),
    ),
  );
  const result = await createEvaluationModels(
    { ANTHROPIC_API_KEY: "test" },
    send,
  ).generate(
    "anthropic/claude-sonnet-5-5",
    [{ role: "user", content: "test" }],
    new AbortController().signal,
  );
  expect(result.usage).toEqual({
    input_tokens: 60,
    output_tokens: 5,
    cached_input_tokens: 20,
    cache_write_tokens: 30,
  });
});

it.each(["openai/gpt-5.1-codex", "openai/o3-pro"])(
  "uses Responses for %s and retains billing usage",
  async (model) => {
    const send = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          status: "completed",
          output: [
            { type: "reasoning" },
            {
              type: "message",
              content: [{ type: "output_text", text: "answer" }],
            },
          ],
          usage: {
            input_tokens: 100,
            output_tokens: 50,
            input_tokens_details: { cached_tokens: 30 },
            output_tokens_details: { reasoning_tokens: 40 },
          },
        }),
      ),
    );
    const result = await createEvaluationModels(
      { OPENAI_API_KEY: "test" },
      send,
    ).generate(
      model,
      [{ role: "user", content: "test" }],
      new AbortController().signal,
    );
    expect(send.mock.calls[0]?.[0]).toBe("https://api.openai.com/v1/responses");
    expect(JSON.parse(String(send.mock.calls[0]?.[1]?.body))).toMatchObject({
      model: model.slice(7),
      input: [{ role: "user", content: "test" }],
      store: false,
    });
    expect(result).toMatchObject({
      text: "answer",
      tokens: 10,
      usage: { input_tokens: 100, output_tokens: 50, cached_input_tokens: 30 },
    });
  },
);
it("uses Completions for instruct models", async () => {
  const send = vi.fn<typeof fetch>().mockResolvedValue(
    new Response(
      JSON.stringify({
        choices: [{ text: "answer", finish_reason: "stop" }],
        usage: { prompt_tokens: 10, completion_tokens: 2 },
      }),
    ),
  );
  const result = await createEvaluationModels(
    { OPENAI_API_KEY: "test" },
    send,
  ).generate(
    "openai/gpt-3.5-turbo-instruct",
    [{ role: "user", content: "test" }],
    new AbortController().signal,
  );
  expect(send.mock.calls[0]?.[0]).toBe("https://api.openai.com/v1/completions");
  expect(result).toMatchObject({
    text: "answer",
    usage: { input_tokens: 10, output_tokens: 2 },
  });
});
