// Synthetic OpenRouter Chat Completions wire profile, shaped like responses
// measured from the live API on 2026-11-05. It adds every field OpenRouter adds
// to the OpenAI shape, so tests can prove the gateway never forwards them.
import {
  isJsonObject,
  text,
  type JsonObject,
  type JsonValue,
} from "../json.js";
import type { RuntimeProfile, StreamEvents } from "./profile.js";

const PATH = "/api/v1/chat/completions";
const HASH = /^[0-9a-f]{64}$/;
const OUTPUT_LIMITS = ["max_tokens", "max_completion_tokens"];
const RUNTIME_FIELDS = ["priority", "stream_options", "service_tier"];

export const UPSTREAM_DETAILS = [
  "gen-synthetic",
  "SyntheticProvider",
  "reasoning_details",
  "native_finish_reason",
  "is_byok",
  "cost_details",
] as const;

/** OpenRouter's charge to Gradiated in USD, far above any catalog price used here. */
export const UPSTREAM_COST_USD = 0.5;

const same = (left: JsonValue | undefined, right: JsonValue): boolean =>
  JSON.stringify(left) === JSON.stringify(right);

export const validate = (body: JsonObject, model: string): void => {
  if (body.model !== model) throw new Error("wrong OpenRouter model");

  const messages = body.messages;
  if (!Array.isArray(messages) || messages.length === 0) {
    throw new Error("messages must be a non-empty list");
  }
  if (typeof body.stream !== "boolean") {
    throw new Error("stream must be a boolean");
  }

  const limits = OUTPUT_LIMITS.filter((key) => key in body);
  const limit = limits.length === 1 ? body[limits[0]!] : undefined;
  if (typeof limit !== "number" || !Number.isInteger(limit) || limit <= 0) {
    throw new Error("exactly one positive output limit is required");
  }

  if (
    !same(body.provider, {
      data_collection: "deny",
      require_parameters: true,
      zdr: true,
    })
  ) {
    throw new Error("privacy routing preferences are required");
  }
  if (!same(body.plugins, [{ id: "context-compression", enabled: false }])) {
    throw new Error("context compression must be disabled");
  }
  if (typeof body.user !== "string" || !HASH.test(body.user)) {
    throw new Error("user must be an opaque hash");
  }
  if (
    body.session_id !== undefined &&
    (typeof body.session_id !== "string" || !HASH.test(body.session_id))
  ) {
    throw new Error("session_id must be an opaque hash");
  }
  if (RUNTIME_FIELDS.some((field) => field in body)) {
    throw new Error("runtime-only fields must not reach OpenRouter");
  }
};

const usage = (cached: number, output: number): JsonObject => ({
  prompt_tokens: 100,
  completion_tokens: output,
  total_tokens: 100 + output,
  cost: UPSTREAM_COST_USD,
  is_byok: false,
  prompt_tokens_details: {
    cached_tokens: cached,
    cache_write_tokens: 0,
    audio_tokens: 0,
  },
  cost_details: { upstream_inference_cost: UPSTREAM_COST_USD },
  // OpenRouter can report more reasoning than completion tokens.
  completion_tokens_details: { reasoning_tokens: output + 2, image_tokens: 0 },
});

const toolName = (body: JsonObject): string | undefined => {
  const [tool] = Array.isArray(body.tools) ? body.tools : [];
  const definition = isJsonObject(tool) ? tool.function : undefined;

  return isJsonObject(definition) ? text(definition.name) : undefined;
};

export const response = (body: JsonObject, cached = 0): JsonObject => {
  const tool = toolName(body);
  const finish = tool ? "tool_calls" : "stop";

  return {
    id: "gen-synthetic",
    object: "chat.completion",
    created: 1_793_892_348,
    model: text(body.model),
    provider: "SyntheticProvider",
    system_fingerprint: null,
    service_tier: null,
    choices: [
      {
        index: 0,
        logprobs: null,
        finish_reason: finish,
        native_finish_reason: finish,
        message: {
          role: "assistant",
          content: tool ? null : "Synthetic answer",
          refusal: null,
          reasoning: "Synthetic reasoning",
          reasoning_details: [
            { type: "reasoning.text", text: "Synthetic reasoning" },
          ],
          ...(tool
            ? {
                tool_calls: [
                  {
                    id: "call_synthetic",
                    type: "function",
                    function: { name: tool, arguments: '{"city":"Paris"}' },
                  },
                ],
              }
            : {}),
        },
      },
    ],
    usage: usage(cached, 3),
  };
};

export const events = (body: JsonObject, cached = 0): StreamEvents => {
  const frame = (delta: JsonObject, finish: string | null): JsonObject => ({
    id: "gen-synthetic",
    object: "chat.completion.chunk",
    created: 1_793_892_348,
    model: text(body.model),
    provider: "SyntheticProvider",
    choices: [
      {
        index: 0,
        delta,
        finish_reason: finish,
        native_finish_reason: finish,
      },
    ],
  });
  const tool = toolName(body);
  const finish = tool ? "tool_calls" : "stop";
  const deltas: JsonObject[] = tool
    ? [
        {
          role: "assistant",
          content: null,
          tool_calls: [
            {
              index: 0,
              id: "call_synthetic",
              type: "function",
              function: { name: tool, arguments: '{"city":' },
            },
          ],
        },
        {
          role: "assistant",
          content: null,
          tool_calls: [{ index: 0, function: { arguments: '"Paris"}' } }],
        },
      ]
    : [
        {
          role: "assistant",
          content: "",
          reasoning: "Synthetic",
          reasoning_details: [{ type: "reasoning.text", text: "Synthetic" }],
        },
        { role: "assistant", content: "Hello ", reasoning: null },
        { role: "assistant", content: "世界", reasoning: null },
      ];

  const accounting = {
    ...frame({ role: "assistant", content: "" }, finish),
    service_tier: null,
    usage: usage(cached, 3),
  };

  return [
    ": OPENROUTER PROCESSING",
    ...deltas.map((delta) => frame(delta, null)),
    frame({ role: "assistant", content: "" }, finish),
    accounting,
    "[DONE]",
  ];
};

export const profile: RuntimeProfile = {
  path: PATH,
  validate,
  response,
  events,
};
