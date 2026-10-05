import { randomUUID } from "node:crypto";
import { TypeSafeClient, choice } from "@typesafe-ai/sdk";
import OpenAI from "openai";
import type { ModelVerification } from "./model-verification.js";

export const probeModel = async (
  options: ModelVerification & { readonly deploymentId: string },
): Promise<void> => {
  const targetedFetch: typeof fetch = async (input, init) => {
    const request = new Request(input, init);
    request.headers.set(
      "x-gradiated-verification-deployment",
      options.deploymentId,
    );
    const response = await (options.fetch ?? fetch)(request, {
      signal: AbortSignal.any([request.signal, options.signal]),
    });
    if (
      response.ok &&
      (response.headers.get("x-gradiated-verification-deployment") !==
        options.deploymentId ||
        !response.headers.get("x-gradiated-generation-id"))
    )
      throw new Error("Invalid inference probe identity");

    return response;
  };
  if (options.protocol === "system_one") {
    const client = new TypeSafeClient({
      apiKey: options.apiKey,
      baseURL: options.baseURL,
      defaultModel: options.modelId,
      fetch: targetedFetch,
      retry: { maxRetries: 0 },
      timeout: 4_000,
    });
    const result = await client.systemOne({
      state: { message: "Payment question", probe: randomUUID() },
      questions: {
        category: choice("Choose a department", {
          billing: "Payments",
          technical: "Software",
        }),
      },
    });
    if (
      result.model !== options.modelId ||
      !(result.usage?.input_tokens > 0) ||
      result.answers.category.type !== "choice" ||
      !["billing", "technical"].includes(result.answers.category.choice)
    )
      throw new Error("Invalid inference probe decision");

    return;
  }

  const client = new OpenAI({
    apiKey: options.apiKey,
    baseURL: `${options.baseURL.replace(/\/$/, "")}/v1`,
    fetch: targetedFetch,
    maxRetries: 0,
    timeout: 4_000,
  });
  const result = await client.chat.completions.create({
    model: options.modelId,
    messages: [{ role: "user", content: "Hi" }],
    max_tokens: 8,
    temperature: 0,
  });
  if (
    result.model !== options.modelId ||
    !result.id ||
    !(result.usage?.completion_tokens && result.usage.completion_tokens > 0) ||
    !["stop", "length"].includes(result.choices[0]?.finish_reason ?? "")
  )
    throw new Error("Invalid inference probe completion");
};
