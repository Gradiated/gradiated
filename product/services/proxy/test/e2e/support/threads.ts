// Conversation histories for thread-continuity tests. Our own turns are real
// gateway output, so the tests follow the translation code instead of a copy of it.
import Anthropic from "@anthropic-ai/sdk";
import OpenAI from "openai";
import { expect } from "vitest";

import type { Case } from "../../../../gateway/test/integration/case.js";
import type { Client } from "../../../../gateway/test/integration/http-client.js";
import {
  object,
  type JsonObject,
  type JsonValue,
} from "../../../../gateway/test/integration/json.js";

export const OUR_REASONING =
  "The user wants a.ts. I will read it before answering.";
export const PROMPT = "Read a.ts and tell me what it exports.";
export const TOOL_OUTPUT = "export const answer = 42;";
export const FOLLOW_UP = "Thanks. Now summarise that in one word.";

export const ANTHROPIC_TOOLS: Anthropic.Tool[] = [
  {
    name: "read_file",
    description: "Read a file from the workspace.",
    input_schema: {
      type: "object",
      properties: { path: { type: "string" } },
      required: ["path"],
    },
  },
];

export const RESPONSES_TOOLS: OpenAI.Responses.FunctionTool[] = [
  {
    type: "function",
    name: "read_file",
    description: "Read a file from the workspace.",
    strict: false,
    parameters: {
      type: "object",
      properties: { path: { type: "string" } },
      required: ["path"],
    },
  },
];

export type Step = "tool loop" | "new turn";
export const STEPS: readonly Step[] = ["tool loop", "new turn"];

const withReasoning = (instance: Case): void => {
  instance.runtimes[0]!.enqueue({
    mutateBody: (body) => {
      const [choice] = body.choices as JsonObject[];
      object(choice!.message).reasoning_content = OUR_REASONING;
    },
  });
};

const withStreamedReasoning = (instance: Case): void => {
  instance.runtimes[0]!.enqueue({
    mutateEvents: (events) => {
      const first = object(events[0]);
      events.splice(1, 0, {
        ...first,
        choices: [
          {
            index: 0,
            delta: { reasoning_content: OUR_REASONING },
            finish_reason: null,
          },
        ],
      });
    },
  });
};

/** One streamed Messages turn, assembled by the official SDK as Claude Code stores it. */
export const ourStreamedMessagesTurn = async (
  baseURL: string,
  instance: Case,
  step: Step,
): Promise<JsonValue[]> => {
  withStreamedReasoning(instance);
  const client = new Anthropic({
    apiKey: instance.key,
    baseURL,
    maxRetries: 0,
  });

  const message = await client.messages
    .stream({
      model: instance.model,
      max_tokens: 64,
      messages: [{ role: "user", content: PROMPT }],
      ...(step === "tool loop" ? { tools: ANTHROPIC_TOOLS } : {}),
    })
    .finalMessage();

  return JSON.parse(JSON.stringify(message.content)) as JsonValue[];
};

/** One streamed Responses turn, assembled from the completed event as Codex stores it. */
export const ourStreamedResponsesTurn = async (
  baseURL: string,
  instance: Case,
  step: Step,
): Promise<JsonValue[]> => {
  withStreamedReasoning(instance);
  const client = new OpenAI({
    apiKey: instance.key,
    baseURL: `${baseURL}/v1`,
    maxRetries: 0,
  });

  const stream = await client.responses.create({
    model: instance.model,
    max_output_tokens: 64,
    store: false,
    stream: true,
    input: [{ role: "user", content: PROMPT }],
    ...(step === "tool loop" ? { tools: RESPONSES_TOOLS } : {}),
  });

  const types: string[] = [];
  let output: JsonValue[] = [];
  for await (const event of stream) {
    types.push(event.type);
    if (event.type === "response.completed")
      output = JSON.parse(JSON.stringify(event.response.output)) as JsonValue[];
  }
  expect(types.filter((type) => type.includes("reasoning"))).toEqual([]);

  return output;
};

/** One assistant turn from our hosted model on Anthropic Messages, as the customer's client received it. */
export const ourMessagesTurn = async (
  client: Client,
  instance: Case,
  step: Step,
): Promise<JsonValue[]> => {
  withReasoning(instance);

  const response = await client.post("/v1/messages", {
    headers: instance.headers,
    json: {
      model: instance.model,
      max_tokens: 64,
      messages: [{ role: "user", content: PROMPT }],
      ...(step === "tool loop" ? { tools: ANTHROPIC_TOOLS } : {}),
    },
  });
  expect(response.status, response.text).toBe(200);

  return response.json().content as JsonValue[];
};

/** One Responses turn from our hosted model, as a Codex-style client received it. */
export const ourResponsesTurn = async (
  client: Client,
  instance: Case,
  step: Step,
): Promise<JsonValue[]> => {
  withReasoning(instance);

  const response = await client.post("/v1/responses", {
    headers: instance.headers,
    json: {
      model: instance.model,
      max_output_tokens: 64,
      store: false,
      input: [{ role: "user", content: PROMPT }],
      ...(step === "tool loop" ? { tools: RESPONSES_TOOLS } : {}),
    },
  });
  expect(response.status, response.text).toBe(200);

  return response.json().output as JsonValue[];
};

const blocks = (content: JsonValue[], type: string): JsonObject[] =>
  content.map((block) => object(block)).filter((block) => block.type === type);

/** The next Messages request a client sends after `assistant`, whoever produced it. */
export const nextMessages = (
  assistant: JsonValue[],
  step: Step,
): JsonValue[] => {
  const history: JsonValue[] = [
    { role: "user", content: PROMPT },
    { role: "assistant", content: assistant },
  ];

  if (step === "new turn")
    return [...history, { role: "user", content: FOLLOW_UP }];

  const [toolUse] = blocks(assistant, "tool_use");
  expect(toolUse, "the assistant turn has no tool_use block").toBeDefined();

  return [
    ...history,
    {
      role: "user",
      content: [
        {
          type: "tool_result",
          tool_use_id: toolUse!.id!,
          content: TOOL_OUTPUT,
        },
      ],
    },
  ];
};

/** The next Responses input a client sends after `output`, whoever produced it. */
export const nextResponsesInput = (
  output: JsonValue[],
  step: Step,
): JsonValue[] => {
  const history: JsonValue[] = [{ role: "user", content: PROMPT }, ...output];

  if (step === "new turn")
    return [...history, { role: "user", content: FOLLOW_UP }];

  const [call] = blocks(output, "function_call");
  expect(call, "the output has no function_call item").toBeDefined();

  return [
    ...history,
    {
      type: "function_call_output",
      call_id: call!.call_id!,
      output: TOOL_OUTPUT,
    },
  ];
};

/**
 * A Claude assistant turn shaped as Claude returns it with thinking display
 * omitted: an empty thinking field whose signature carries the encrypted
 * reasoning, a redacted block, and a tool call.
 */
export const CLAUDE_SIGNATURE = `EqQBCkYIBxgCKkA${"Q".repeat(120)}`;
export const CLAUDE_REDACTED = `EmwKAhgBEgy3va3pzix${"R".repeat(80)}`;

export const claudeTurn = (step: Step): JsonValue[] => [
  { type: "thinking", thinking: "", signature: CLAUDE_SIGNATURE },
  { type: "redacted_thinking", data: CLAUDE_REDACTED },
  ...(step === "tool loop"
    ? [
        {
          type: "tool_use",
          id: "toolu_01A09q90qw90lq917835lq9",
          name: "read_file",
          input: { path: "a.ts" },
        },
      ]
    : [{ type: "text", text: "It exports answer." }]),
];

/** An OpenAI Responses turn as Codex receives it with `store: false`. */
export const OPENAI_ENCRYPTED = `gAAAAABo${"E".repeat(160)}`;

export const openAiTurn = (step: Step): JsonValue[] => [
  {
    type: "reasoning",
    id: "rs_68c1f0d1a2b4819a",
    summary: [],
    encrypted_content: OPENAI_ENCRYPTED,
  },
  step === "tool loop"
    ? {
        type: "function_call",
        id: "fc_68c1f0d1a2b4819a",
        call_id: "call_Xg7Ro2lK",
        name: "read_file",
        arguments: '{"path":"a.ts"}',
        status: "completed",
      }
    : {
        type: "message",
        id: "msg_68c1f0d1a2b4819a",
        role: "assistant",
        status: "completed",
        content: [
          { type: "output_text", text: "It exports answer.", annotations: [] },
        ],
      },
];

export const CHAT_TOOLS: JsonValue[] = [
  {
    type: "function",
    function: {
      name: "read_file",
      description: "Read a file from the workspace.",
      parameters: {
        type: "object",
        properties: { path: { type: "string" } },
        required: ["path"],
      },
    },
  },
];

/** One Chat Completions assistant message from our hosted model, as the client received it. */
export const ourChatTurn = async (
  client: Client,
  instance: Case,
  step: Step,
): Promise<JsonObject> => {
  withReasoning(instance);

  const response = await client.post("/v1/chat/completions", {
    headers: instance.headers,
    json: {
      model: instance.model,
      max_tokens: 64,
      messages: [{ role: "user", content: PROMPT }],
      ...(step === "tool loop" ? { tools: CHAT_TOOLS } : {}),
    },
  });
  expect(response.status, response.text).toBe(200);

  const [choice] = response.json().choices as JsonObject[];
  return object(choice!.message);
};

/** The next Chat Completions messages a client sends after `assistant`. */
export const nextChat = (assistant: JsonObject, step: Step): JsonValue[] => {
  const history: JsonValue[] = [{ role: "user", content: PROMPT }, assistant];

  if (step === "new turn")
    return [...history, { role: "user", content: FOLLOW_UP }];

  const [call] = (assistant.tool_calls ?? []) as JsonObject[];
  expect(call, "the assistant message has no tool call").toBeDefined();

  return [
    ...history,
    { role: "tool", tool_call_id: call!.id!, content: TOOL_OUTPUT },
  ];
};
