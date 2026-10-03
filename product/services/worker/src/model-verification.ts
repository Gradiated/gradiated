import { TypeSafeClient, choice } from "@typesafe-ai/sdk";
import OpenAI from "openai";
import { randomUUID } from "node:crypto";
import { z } from "zod";

export const ModelVerificationInputSchema = z
  .object({
    modelId: z.string().min(1).max(300),
    stage: z.enum(["canary", "serving"]),
    deploymentIds: z.array(z.guid()).min(1),
    protocol: z.literal("system_one").optional(),
    runtimeRevision: z.string().min(1).max(300),
    replicaRollout: z.boolean().optional(),
  })
  .strict();

export interface ModelVerification {
  readonly apiKey: string;
  readonly baseURL: string;
  readonly modelId: string;
  readonly deploymentId?: string | undefined;
  readonly protocol?: "system_one" | undefined;
  readonly signal: AbortSignal;
  readonly fetch?: typeof fetch;
}

export const verifyModel = async (options: ModelVerification) => {
  const generations: string[] = [];
  const verifiedFetch: typeof fetch = async (input, init) => {
    const request = new Request(input, init);
    if (options.deploymentId)
      request.headers.set(
        "x-gradiated-verification-deployment",
        options.deploymentId,
      );
    const response = await (options.fetch ?? fetch)(request, {
      signal: AbortSignal.any([request.signal, options.signal]),
    });
    if (response.ok) {
      if (
        options.deploymentId &&
        response.headers.get("x-gradiated-verification-deployment") !==
          options.deploymentId
      )
        throw new Error("Gateway did not acknowledge the target allocation");
      const id = response.headers.get("x-gradiated-generation-id");
      if (
        !id ||
        !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(
          id,
        )
      )
        throw new Error("Missing generation identity");
      generations.push(id);
    }
    return response;
  };

  if (options.protocol === "system_one") {
    const client = new TypeSafeClient({
      apiKey: options.apiKey,
      baseURL: options.baseURL,
      defaultModel: options.modelId,
      fetch: verifiedFetch,
      retry: { maxRetries: 0 },
      timeout: 120_000,
    });
    const result = await client.systemOne({
      state: {
        message: "I was charged twice. This is a billing problem.",
        verification: randomUUID(),
      },
      questions: {
        category: choice("Choose the support department", {
          billing: "Payments and charges",
          technical: "Software errors",
        }),
      },
    });
    if (
      result.model !== options.modelId ||
      !(result.usage?.input_tokens > 0) ||
      result.usage?.output_tokens !== 0 ||
      result.answers.category.type !== "choice" ||
      result.answers.category.choice !== "billing"
    )
      throw new Error("Invalid decision result");
  } else {
    const client = new OpenAI({
      apiKey: options.apiKey,
      baseURL: options.baseURL,
      fetch: verifiedFetch,
      maxRetries: 0,
      timeout: 120_000,
    });
    const parameters = {
      model: options.modelId,
      messages: [
        {
          role: "user" as const,
          content: "Reply with exactly the word READY and nothing else.",
        },
      ],
      max_tokens: 256,
      temperature: 0,
    };
    const result = await client.chat.completions.create(parameters);
    if (
      result.model !== options.modelId ||
      !result.id ||
      result.choices[0]?.finish_reason !== "stop" ||
      result.choices[0]?.message.content?.trim() !== "READY" ||
      !result.usage?.completion_tokens
    )
      throw new Error("Invalid completion result");

    const stream = await client.chat.completions.create({
      ...parameters,
      stream: true,
      stream_options: { include_usage: true },
    });
    let completionId: string | undefined;
    let text = "";
    let finished = false;
    let usage = false;
    for await (const chunk of stream) {
      if (
        !chunk.id ||
        chunk.model !== options.modelId ||
        (completionId && completionId !== chunk.id)
      )
        throw new Error("Invalid streamed completion identity");
      completionId = chunk.id;
      text += chunk.choices[0]?.delta?.content ?? "";
      finished ||= chunk.choices[0]?.finish_reason === "stop";
      usage ||= (chunk.usage?.completion_tokens ?? 0) > 0;
    }
    if (text.trim() !== "READY" || !finished || !usage)
      throw new Error("Incomplete streamed completion");
  }

  const expected = options.protocol === "system_one" ? 1 : 2;
  if (generations.length !== expected || new Set(generations).size !== expected)
    throw new Error("Invalid generation identities");
  return {
    modelId: options.modelId,
    deploymentId: options.deploymentId,
    generations,
  };
};
