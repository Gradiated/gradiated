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
  expect(() =>
    createEvaluationModels({}, send).check("openai/gpt-6.1-sol"),
  ).toThrow("credentials");
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
