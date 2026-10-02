import { performance } from "node:perf_hooks";
import { z } from "zod";

export type EvaluationMessage = {
  role: "system" | "user" | "assistant";
  content: string;
};
export const predictionSchema = z.object({
  text: z.string().min(1),
  tokens: z.number().int().nonnegative(),
  seconds: z.number().positive(),
});
export type EvaluationModel = {
  check(modelId: string): void;
  generate(
    modelId: string,
    messages: EvaluationMessage[],
    signal: AbortSignal,
  ): Promise<z.infer<typeof predictionSchema>>;
};

const chatResponse = z.object({
  choices: z
    .array(
      z.object({
        message: z.object({ content: z.string().min(1) }),
        finish_reason: z.literal("stop"),
      }),
    )
    .min(1),
  usage: z.object({
    completion_tokens: z.number().int().nonnegative(),
    completion_tokens_details: z
      .object({ reasoning_tokens: z.number().int().nonnegative() })
      .optional(),
  }),
});
const claudeResponse = z.object({
  content: z.array(z.object({ type: z.string(), text: z.string().optional() })),
  stop_reason: z.literal("end_turn"),
  usage: z.object({ output_tokens: z.number().int().nonnegative() }),
});

export const createEvaluationModels = (
  environment: NodeJS.ProcessEnv,
  send: typeof fetch = fetch,
): EvaluationModel => {
  const provider = (modelId: string) => {
    if (modelId.startsWith("openai/"))
      return {
        key: environment.OPENAI_API_KEY,
        url: "https://api.openai.com/v1/chat/completions",
        kind: "openai",
      };
    if (modelId.startsWith("anthropic/"))
      return {
        key: environment.ANTHROPIC_API_KEY,
        url: "https://api.anthropic.com/v1/messages",
        kind: "anthropic",
      };
    return {
      key: environment.TRAINING_INFERENCE_API_KEY,
      url: "https://api.gradiated.com/v1/chat/completions",
      kind: "hosted",
    };
  };
  const check = (modelId: string) => {
    if (!provider(modelId).key)
      throw new Error(
        `Evaluation credentials are not configured for ${modelId}.`,
      );
  };

  return {
    check,
    async generate(modelId, messages, signal) {
      check(modelId);
      const { key, url, kind } = provider(modelId);
      const model =
        kind === "hosted" ? modelId : modelId.slice(modelId.indexOf("/") + 1);
      const body =
        kind === "anthropic"
          ? {
              model,
              max_tokens: 4096,
              system: messages
                .filter((message) => message.role === "system")
                .map((message) => message.content)
                .join("\n"),
              messages: messages.filter((message) => message.role !== "system"),
            }
          : {
              model,
              messages,
              ...(kind === "openai"
                ? { max_completion_tokens: 4096 }
                : { max_tokens: 256 }),
              stream: false,
            };
      const headers =
        kind === "anthropic"
          ? { "x-api-key": key!, "anthropic-version": "2023-06-01" }
          : { Authorization: `Bearer ${key!}` };
      const started = performance.now();
      const response = await send(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify(body),
        signal: AbortSignal.any([signal, AbortSignal.timeout(180_000)]),
        redirect: "error",
      });
      if (!response.ok)
        throw new Error(
          `Evaluation request for ${modelId} failed (${response.status}).`,
        );
      const value: unknown = await response.json();
      const seconds = Math.max(0.001, (performance.now() - started) / 1000);
      if (kind === "anthropic") {
        const parsed = claudeResponse.parse(value);
        return predictionSchema.parse({
          text: parsed.content
            .filter((block) => block.type === "text")
            .map((block) => block.text ?? "")
            .join(""),
          tokens: parsed.usage.output_tokens,
          seconds,
        });
      }
      const parsed = chatResponse.parse(value);
      return predictionSchema.parse({
        text: parsed.choices[0]!.message.content,
        tokens:
          parsed.usage.completion_tokens -
          (parsed.usage.completion_tokens_details?.reasoning_tokens ?? 0),
        seconds,
      });
    },
  };
};
