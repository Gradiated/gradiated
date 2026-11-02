import type { JsonObject } from "./json.js";
import type { StreamEvents } from "./mock-runtimes/profile.js";

// SGLang f1718592 OpenAI chat: running usage, reasoning deltas and terminal usage.
export const sglangEvents = (model: string, tool?: string): StreamEvents => {
  const base = {
    id: "3564c79a213a471a925cd7db70427e67",
    object: "chat.completion.chunk",
    created: 1793625600,
    model,
  };
  const usage = (output: number): JsonObject => ({
    prompt_tokens: 100,
    completion_tokens: output,
    total_tokens: 100 + output,
    prompt_tokens_details: { cached_tokens: 40 },
    completion_tokens_details: { reasoning_tokens: Math.min(output, 2) },
  });
  const frame = (
    delta: JsonObject,
    output: number,
    finish: string | null = null,
  ): JsonObject => ({
    ...base,
    choices: [{ index: 0, delta, logprobs: null, finish_reason: finish }],
    usage: usage(output),
  });
  const frames: StreamEvents = [
    frame({ role: "assistant", content: "", reasoning_content: null }, 0),
    frame({ content: null, reasoning_content: "先核对乘法。" }, 2),
  ];

  if (tool) {
    frames.push(
      frame(
        {
          content: null,
          tool_calls: [
            {
              index: 0,
              id: "call_sglang",
              type: "function",
              function: { name: tool, arguments: '{"city":' },
            },
          ],
        },
        3,
      ),
      frame(
        {
          content: null,
          tool_calls: [
            {
              index: 0,
              id: null,
              type: null,
              function: { name: null, arguments: '"Paris"}' },
            },
          ],
        },
        5,
      ),
    );
  } else {
    frames.push(frame({ content: "1517", reasoning_content: null }, 3));
  }

  const output = tool ? 5 : 3;
  frames.push(
    frame({}, output, tool ? "tool_calls" : "stop"),
    { ...base, choices: [], usage: usage(output), sglext: null },
    "[DONE]",
  );

  return frames;
};

export const sglangQueueError = (): JsonObject => ({
  error: {
    object: "error",
    message: "PRIVATE_QUEUE_DETAIL",
    type: "SERVICE_UNAVAILABLE",
    param: null,
    code: 503,
  },
});
