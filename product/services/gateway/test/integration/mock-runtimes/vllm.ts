// Synthetic vLLM OpenAI chat wire profile; no model execution or tokenization.
//
// Responses are built as the official `ChatCompletion`/`ChatCompletionChunk` types,
// so `tsc` is the independent anchor that this mock stays on the real wire shape.
import type {
  ChatCompletion,
  ChatCompletionChunk,
} from "openai/resources/chat/completions";

import {
  isJsonObject,
  text,
  toJsonObject,
  type JsonObject,
  type JsonValue,
} from "../json.js";
import type { RuntimeProfile, StreamEvents } from "./profile.js";

const PATH = "/v1/chat/completions";

const PRIORITIES = [-10, 0, 10];
const OUTPUT_LIMITS = ["max_tokens", "max_completion_tokens"];
const GATEWAY_OWNED_FIELDS = ["session_id", "service_tier"];

const isInteger = (value: JsonValue | undefined): value is number =>
  typeof value === "number" && Number.isInteger(value);

const validateStreamOptions = (options: JsonValue | undefined): void => {
  if (
    !isJsonObject(options) ||
    options.include_usage !== true ||
    options.continuous_usage_stats !== true ||
    Object.keys(options).length !== 2
  ) {
    throw new Error("streaming requires usage stream options");
  }
};

export const validate = (body: JsonObject, model: string): void => {
  if (body.model !== model) throw new Error("wrong private model");

  const messages = body.messages;
  if (!Array.isArray(messages) || messages.length === 0) {
    throw new Error("messages must be a non-empty list");
  }
  if (!messages.every(isJsonObject)) {
    throw new Error("each message must be an object");
  }
  if (typeof body.stream !== "boolean") {
    throw new Error("stream must be a boolean");
  }

  const [limit, ...extraLimits] = OUTPUT_LIMITS.filter((key) => key in body);
  const limitValue = limit === undefined ? undefined : body[limit];
  if (extraLimits.length > 0 || !isInteger(limitValue) || limitValue <= 0) {
    throw new Error("exactly one positive output limit is required");
  }

  const priority = body.priority;
  if (!isInteger(priority) || !PRIORITIES.includes(priority)) {
    throw new Error("priority must be one of -10, 0, 10");
  }
  if (GATEWAY_OWNED_FIELDS.some((field) => field in body)) {
    throw new Error("gateway-owned fields must not reach the runtime");
  }

  if (body.stream) validateStreamOptions(body.stream_options);
};

const usage = (
  cached = 0,
  output = 3,
): NonNullable<ChatCompletion["usage"]> => ({
  prompt_tokens: 100,
  completion_tokens: output,
  total_tokens: 100 + output,
  prompt_tokens_details: { cached_tokens: cached },
});

const hasTools = (body: JsonObject): boolean =>
  Array.isArray(body.tools) && body.tools.length > 0;

const toolName = (body: JsonObject): string => {
  const [tool] = Array.isArray(body.tools) ? body.tools : [];
  const definition = isJsonObject(tool) ? tool.function : undefined;

  if (!isJsonObject(definition)) {
    throw new Error("a tool must define a function");
  }

  return text(definition.name);
};

export const response = (body: JsonObject, cached = 0): JsonObject => {
  const tools = hasTools(body);
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
    model: text(body.model),
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

  return toJsonObject(completion);
};

export const events = (body: JsonObject, cached = 0): StreamEvents => {
  const base = {
    id: "chatcmpl-synthetic",
    object: "chat.completion.chunk",
    created: 1700000000,
    model: text(body.model),
  } satisfies Omit<ChatCompletionChunk, "choices">;
  const tools = hasTools(body);
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

  return [...chunks.map(toJsonObject), "[DONE]"];
};

export const profile: RuntimeProfile = {
  path: PATH,
  validate,
  response,
  events,
};
