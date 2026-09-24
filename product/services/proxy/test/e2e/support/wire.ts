// Provider wire bodies in the shapes the official SDKs parse. The mock provider
// serves these; the SDK tests assert what the SDK made of them.

const sse = (event: string | null, data: unknown): string =>
  `${event ? `event: ${event}\n` : ""}data: ${typeof data === "string" ? data : JSON.stringify(data)}\n\n`;

export const anthropic = {
  message: (model: string, text: string): string =>
    JSON.stringify({
      id: "msg_synthetic",
      type: "message",
      role: "assistant",
      model,
      content: [{ type: "text", text }],
      stop_reason: "end_turn",
      stop_sequence: null,
      usage: { input_tokens: 12, output_tokens: 3 },
    }),

  stream: (model: string, parts: readonly string[]): string[] => [
    sse("message_start", {
      type: "message_start",
      message: {
        id: "msg_synthetic",
        type: "message",
        role: "assistant",
        model,
        content: [],
        stop_reason: null,
        stop_sequence: null,
        usage: { input_tokens: 12, output_tokens: 0 },
      },
    }),
    sse("content_block_start", {
      type: "content_block_start",
      index: 0,
      content_block: { type: "text", text: "" },
    }),
    ...parts.map((text) =>
      sse("content_block_delta", {
        type: "content_block_delta",
        index: 0,
        delta: { type: "text_delta", text },
      }),
    ),
    sse("content_block_stop", { type: "content_block_stop", index: 0 }),
    sse("message_delta", {
      type: "message_delta",
      delta: { stop_reason: "end_turn", stop_sequence: null },
      usage: { output_tokens: parts.length },
    }),
    sse("message_stop", { type: "message_stop" }),
  ],

  tokenCount: (inputTokens: number): string =>
    JSON.stringify({ input_tokens: inputTokens }),

  error: (type: string, message: string): string =>
    JSON.stringify({ type: "error", error: { type, message } }),
};

export const openai = {
  chatCompletion: (model: string, text: string): string =>
    JSON.stringify({
      id: "chatcmpl-synthetic",
      object: "chat.completion",
      created: 1_700_000_000,
      model,
      choices: [
        {
          index: 0,
          message: { role: "assistant", content: text, refusal: null },
          finish_reason: "stop",
          logprobs: null,
        },
      ],
      usage: { prompt_tokens: 12, completion_tokens: 3, total_tokens: 15 },
    }),

  chatStream: (model: string, parts: readonly string[]): string[] => {
    const chunk = (delta: object, finish: string | null) =>
      sse(null, {
        id: "chatcmpl-synthetic",
        object: "chat.completion.chunk",
        created: 1_700_000_000,
        model,
        choices: [{ index: 0, delta, finish_reason: finish, logprobs: null }],
      });

    return [
      chunk({ role: "assistant", content: "" }, null),
      ...parts.map((content) => chunk({ content }, null)),
      chunk({}, "stop"),
      sse(null, "[DONE]"),
    ];
  },

  response: (model: string, text: string): string =>
    JSON.stringify({
      id: "resp_synthetic",
      object: "response",
      created_at: 1_700_000_000,
      status: "completed",
      model,
      output: [
        {
          type: "message",
          id: "msg_synthetic",
          status: "completed",
          role: "assistant",
          content: [{ type: "output_text", text, annotations: [] }],
        },
      ],
      usage: { input_tokens: 12, output_tokens: 3, total_tokens: 15 },
    }),

  error: (type: string, code: string, message: string): string =>
    JSON.stringify({ error: { message, type, code, param: null } }),
};
