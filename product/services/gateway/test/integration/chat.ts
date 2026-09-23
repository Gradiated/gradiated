import OpenAI from "openai";
import type {
  ChatCompletionChunk,
  ChatCompletionMessageParam,
} from "openai/resources/chat/completions";

import type { Case } from "./case.js";
import { isJsonObject } from "./json.js";

export const CHAT_PROMPT = "Synthetic billing ticket";

export const chatMessages = (): ChatCompletionMessageParam[] => [
  { role: "user", content: CHAT_PROMPT },
];

const isChatCompletionChunk = (value: unknown): value is ChatCompletionChunk =>
  isJsonObject(value) &&
  value.object === "chat.completion.chunk" &&
  typeof value.id === "string" &&
  typeof value.model === "string" &&
  typeof value.created === "number" &&
  Array.isArray(value.choices) &&
  value.choices.every(
    (choice) =>
      isJsonObject(choice) &&
      typeof choice.index === "number" &&
      isJsonObject(choice.delta),
  ) &&
  (value.usage === undefined ||
    value.usage === null ||
    isJsonObject(value.usage));

/** The chunks of a chat completion stream, without its `[DONE]` terminator. */
export const chatChunks = (frames: string[]): ChatCompletionChunk[] =>
  frames
    .filter((frame) => frame !== "[DONE]")
    .map((frame) => {
      const chunk: unknown = JSON.parse(frame);
      if (!isChatCompletionChunk(chunk)) {
        throw new Error(`not a chat completion chunk: ${frame}`);
      }

      return chunk;
    });

export const chatSdk = (instance: Case): OpenAI =>
  new OpenAI({
    apiKey: instance.key,
    baseURL: `${instance.http.baseUrl.replace(/\/$/, "")}/v1`,
    maxRetries: 0,
    timeout: 5000,
  });
