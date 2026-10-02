import { performance } from "node:perf_hooks";
import { z } from "zod";
import { CredentialLoader } from "@gradiated/credentials";

export type EvaluationMessage = {
  role: "system" | "user" | "assistant";
  content: string;
};
export const predictionSchema = z.object({
  text: z.string().min(1),
  tokens: z.number().int().nonnegative(),
  seconds: z.number().positive(),
  usage: z
    .object({
      input_tokens: z.number().int().nonnegative(),
      output_tokens: z.number().int().nonnegative(),
      cached_input_tokens: z.number().int().nonnegative().optional(),
      cache_write_tokens: z.number().int().nonnegative().optional(),
    })
    .optional(),
});
export type EvaluationModel = {
  check(modelId: string): void | Promise<void>;
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
    prompt_tokens: z.number().int().nonnegative().optional(),
    prompt_tokens_details: z
      .object({ cached_tokens: z.number().int().nonnegative().optional() })
      .optional(),
    completion_tokens: z.number().int().nonnegative(),
    completion_tokens_details: z
      .object({ reasoning_tokens: z.number().int().nonnegative() })
      .optional(),
  }),
});
const claudeResponse = z.object({
  content: z.array(z.object({ type: z.string(), text: z.string().optional() })),
  stop_reason: z.literal("end_turn"),
  usage: z.object({
    output_tokens: z.number().int().nonnegative(),
    input_tokens: z.number().int().nonnegative().optional(),
    cache_read_input_tokens: z.number().int().nonnegative().optional(),
    cache_creation_input_tokens: z.number().int().nonnegative().optional(),
  }),
});

export const createEvaluationModels = (
  environment: NodeJS.ProcessEnv,
  send: typeof fetch = fetch,
  credentials: Pick<CredentialLoader, "load"> = new CredentialLoader(),
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
  const credential = async (modelId: string) => {
    const selected = provider(modelId);
    if (selected.kind === "openai" || selected.kind === "anthropic") {
      if (environment.NODE_ENV !== "production" && selected.key)
        return selected.key;

      return credentials.load(selected.kind);
    }

    if (!selected.key)
      throw new Error(
        `Evaluation credentials are not configured for ${modelId}.`,
      );

    return selected.key;
  };
  const check = async (modelId: string) => {
    await credential(modelId);
  };

  return {
    check,
    async generate(modelId, messages, signal) {
      const key = await credential(modelId);
      const { url, kind } = provider(modelId);
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
          ...(parsed.usage.input_tokens === undefined
            ? {}
            : {
                usage: {
                  input_tokens:
                    parsed.usage.input_tokens +
                    (parsed.usage.cache_read_input_tokens ?? 0) +
                    (parsed.usage.cache_creation_input_tokens ?? 0),
                  output_tokens: parsed.usage.output_tokens,
                  cached_input_tokens:
                    parsed.usage.cache_read_input_tokens ?? 0,
                  cache_write_tokens:
                    parsed.usage.cache_creation_input_tokens ?? 0,
                },
              }),
        });
      }
      const parsed = chatResponse.parse(value);
      return predictionSchema.parse({
        text: parsed.choices[0]!.message.content,
        tokens:
          parsed.usage.completion_tokens -
          (parsed.usage.completion_tokens_details?.reasoning_tokens ?? 0),
        seconds,
        ...(parsed.usage.prompt_tokens === undefined
          ? {}
          : {
              usage: {
                input_tokens: parsed.usage.prompt_tokens,
                output_tokens: parsed.usage.completion_tokens,
                cached_input_tokens:
                  parsed.usage.prompt_tokens_details?.cached_tokens ?? 0,
              },
            }),
      });
    },
  };
};
