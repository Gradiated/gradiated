// Synthetic vLLM OpenAI chat wire profile; no model execution or tokenization.
//
// Responses are built as the official `ChatCompletion`/`ChatCompletionChunk` types,
// so `tsc` is the independent anchor that this mock stays on the real wire shape.
import type {
  ChatCompletion,
  ChatCompletionChunk,
} from "openai/resources/chat/completions";

import type { JsonObject, RuntimeProfile } from "./profile.js";

export const PATH = "/v1/chat/completions";

const isInteger = (value: unknown): value is number =>
  typeof value === "number" && Number.isInteger(value);

export const validate = (body: JsonObject, model: string): void => {
  if (body.model !== model) throw new Error("wrong private model");
  const messages = body.messages;
  if (!Array.isArray(messages) || messages.length === 0)
    throw new Error("messages must be a non-empty list");
  if (
    messages.some(
      (message) =>
        message === null ||
        typeof message !== "object" ||
        Array.isArray(message),
    )
  ) {
    throw new Error("each message must be an object");
  }
  if (typeof body.stream !== "boolean")
    throw new Error("stream must be a boolean");
  const limits = (["max_tokens", "max_completion_tokens"] as const)
    .filter((key) => key in body)
    .map((key) => body[key]);
  if (
    limits.length !== 1 ||
    !isInteger(limits[0]) ||
    (limits[0] as number) <= 0
  ) {
    throw new Error("exactly one positive output limit is required");
  }
  if (
    !isInteger(body.priority) ||
    ![-10, 0, 10].includes(body.priority as number)
  ) {
    throw new Error("priority must be one of -10, 0, 10");
  }
  if ("session_id" in body || "service_tier" in body) {
    throw new Error("gateway-owned fields must not reach the runtime");
  }
  if (body.stream) {
    const options = body.stream_options as JsonObject | undefined;
    if (
      !options ||
      options.include_usage !== true ||
      options.continuous_usage_stats !== true ||
      Object.keys(options).length !== 2
    ) {
      throw new Error("streaming requires usage stream options");
    }
  }
};

export const usage = (
  cached = 0,
  output = 3,
): NonNullable<ChatCompletion["usage"]> => ({
  prompt_tokens: 100,
  completion_tokens: output,
  total_tokens: 100 + output,
  prompt_tokens_details: { cached_tokens: cached },
});

const toolName = (body: JsonObject): string => {
  const tools = body.tools as JsonObject[];
  return (tools[0]!.function as JsonObject).name as string;
};

export const response = (body: JsonObject, cached = 0): JsonObject => {
  const tools = Array.isArray(body.tools) && body.tools.length > 0;
  const message: ChatCompletion.Choice["message"] = tools
    ? {
        role: "assistant",
        content: null,
        refusal: null,
        tool_calls: [
          {
            id: "call_synthetic",
            type: "function",
            function: { name: toolName(body), arguments: '{"city":"Paris"}' },
          },
        ],
      }
    : { role: "assistant", content: "Synthetic answer", refusal: null };
  const completion: ChatCompletion = {
    id: "chatcmpl-synthetic",
    object: "chat.completion",
    created: 1700000000,
    model: body.model as string,
    choices: [
      {
        index: 0,
        message,
        logprobs: null,
        finish_reason: tools ? "tool_calls" : "stop",
      },
    ],
    usage: usage(cached),
  };
  return completion as unknown as JsonObject;
};

export const events = (
  body: JsonObject,
  cached = 0,
): (JsonObject | string)[] => {
  const base = {
    id: "chatcmpl-synthetic",
    object: "chat.completion.chunk",
    created: 1700000000,
    model: body.model as string,
  } satisfies Omit<ChatCompletionChunk, "choices">;
  const tools = Array.isArray(body.tools) && body.tools.length > 0;
  const deltas: ChatCompletionChunk.Choice.Delta[] = tools
    ? [
        { role: "assistant", content: null },
        {
          tool_calls: [
            {
              index: 0,
              id: "call_synthetic",
              type: "function",
              function: { name: toolName(body), arguments: '{"city":' },
            },
          ],
        },
        { tool_calls: [{ index: 0, function: { arguments: '"Paris"}' } }] },
      ]
    : [
        { role: "assistant", content: "" },
        { content: "Hello " },
        { content: "世界" },
      ];
  const chunks: ChatCompletionChunk[] = deltas.map((delta) => ({
    ...base,
    choices: [{ index: 0, delta, finish_reason: null }],
    usage: null,
  }));
  chunks.push({
    ...base,
    choices: [
      { index: 0, delta: {}, finish_reason: tools ? "tool_calls" : "stop" },
    ],
    usage: null,
  });
  chunks.push({ ...base, choices: [], usage: usage(cached) });
  return [...(chunks as unknown as JsonObject[]), "[DONE]"];
};

export const profile: RuntimeProfile = { PATH, validate, response, events };
