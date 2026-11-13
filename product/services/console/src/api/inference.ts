import { api } from "./client";
import type { components } from "./schema";

export type ChatCompletionRequest =
  components["schemas"]["ChatCompletionRequest"];
export type ChatCompletionParameters = Pick<
  ChatCompletionRequest,
  | "model"
  | "messages"
  | "max_completion_tokens"
  | "temperature"
  | "top_p"
  | "service_tier"
  | "reasoning_effort"
  | "seed"
  | "frequency_penalty"
  | "presence_penalty"
  | "stop"
  | "response_format"
  | "tools"
  | "session_id"
>;
export type ChatCompletionUsage = NonNullable<
  components["schemas"]["ChatCompletionResponse"]["usage"]
>;

export interface ToolCallDelta {
  index: number;
  id?: string;
  name?: string;
  arguments?: string;
}

export interface ChatCompletionDelta {
  content: string;
  reasoning: string;
  toolCalls: ToolCallDelta[];
  usage: ChatCompletionUsage | undefined;
}

interface ChatCompletionChunk {
  choices?: {
    delta?: {
      content?: string | null;
      reasoning_content?: string | null;
      reasoning?: string | null;
      tool_calls?: {
        index?: number;
        id?: string;
        function?: { name?: string; arguments?: string };
      }[];
    };
  }[];
  usage?: ChatCompletionUsage | null;
  error?: { message?: string };
}

export class InferenceError extends Error {
  readonly status: number | undefined;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "InferenceError";
    this.status = status;
  }
}

const STATUS_MESSAGES: Partial<Record<number, string>> = {
  401: "The gateway rejected the credential. It may have expired or been revoked.",
  402: "The organization balance is too low. Top up in Billing to continue.",
  429: "The model or organization is at capacity. Try again in a moment.",
};

export const streamChatCompletion = async ({
  apiKey,
  request,
  signal,
  onDelta,
}: {
  apiKey: string;
  request: ChatCompletionParameters;
  signal: AbortSignal;
  onDelta: (delta: ChatCompletionDelta) => void;
}): Promise<void> => {
  const { error, response } = await api.POST("/v1/chat/completions", {
    body: { ...request, stream: true, stream_options: { include_usage: true } },
    headers: { Authorization: `Bearer ${apiKey}` },
    // The gateway authenticates the bearer key and does not accept credentialed CORS.
    credentials: "omit",
    parseAs: "stream",
    signal,
  });

  if (!response.ok || !response.body) {
    throw new InferenceError(
      STATUS_MESSAGES[response.status] ??
        envelopeMessage(error) ??
        `Request failed with status ${response.status}.`,
      response.status,
    );
  }

  const events = response.body
    .pipeThrough(new TextDecoderStream())
    .pipeThrough(serverSentEventData())
    .getReader();

  for (;;) {
    const { value, done } = await events.read();
    if (value === "[DONE]") return;
    if (done) {
      throw new InferenceError("The response ended before the model finished.");
    }

    const chunk = JSON.parse(value) as ChatCompletionChunk;
    if (chunk.error) {
      throw new InferenceError(
        chunk.error.message ?? "The model stopped with an error.",
      );
    }

    const delta = chunk.choices?.[0]?.delta;
    onDelta({
      content: delta?.content ?? "",
      reasoning: delta?.reasoning_content ?? delta?.reasoning ?? "",
      toolCalls: (delta?.tool_calls ?? []).map((call, position) => ({
        index: call.index ?? position,
        ...(call.id ? { id: call.id } : {}),
        ...(call.function?.name ? { name: call.function.name } : {}),
        ...(call.function?.arguments
          ? { arguments: call.function.arguments }
          : {}),
      })),
      usage: chunk.usage ?? undefined,
    });
  }
};

export const serverSentEventData = () => {
  let buffer = "";

  const enqueue = (
    event: string,
    controller: TransformStreamDefaultController<string>,
  ) => {
    const lines = event
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).replace(/^ /, ""));

    if (lines.length) controller.enqueue(lines.join("\n"));
  };

  return new TransformStream<string, string>({
    transform: (text, controller) => {
      buffer = (buffer + text).replaceAll("\r\n", "\n");
      const events = buffer.split("\n\n");
      buffer = events.pop() ?? "";

      for (const event of events) enqueue(event, controller);
    },
    flush: (controller) => enqueue(buffer, controller),
  });
};

const envelopeMessage = (body: unknown): string | undefined => {
  if (typeof body !== "object" || body === null) return undefined;

  const error: unknown = Reflect.get(body, "error");
  const message: unknown =
    typeof error === "object" && error !== null
      ? Reflect.get(error, "message")
      : Reflect.get(body, "detail");

  return typeof message === "string" && message ? message : undefined;
};
