#!/usr/bin/env node

import { writeFile } from "node:fs/promises";
import { performance } from "node:perf_hooks";
import { parseArgs } from "node:util";

/**
 * @typedef {{ baseUrl: string; model: string; pairs: number; targetInputTokens: number; maxOutputTokens: number; seed: number; requestTimeoutSeconds: number; timeoutSeconds: number; output: string }} Options
 * @typedef {"cold" | "warm"} Arm
 * @typedef {{ apiKey: string; options: Options; pair: number; arm: Arm; prompt: string; deadline: number }} ProfileRequest
 * @typedef {{ prompt_tokens: number; completion_tokens: number; prompt_tokens_details?: { cached_tokens?: number } }} StreamUsage
 * @typedef {{ delta?: { content?: unknown; reasoning_content?: unknown; reasoning?: unknown; tool_calls?: unknown }; finish_reason?: string | null }} StreamChoice
 * @typedef {{ choices?: StreamChoice[]; usage?: StreamUsage }} StreamChunk
 */

/** @type {Arm[]} */
const arms = ["cold", "warm"];

const printUsage = () => {
  console.log(`Usage:
  GRADIATED_API_KEY=... node product/scripts/profile-chat-cache.mjs [options]

Options:
  --base-url URL
  --model ID
  --pairs COUNT
  --target-input-tokens COUNT
  --max-output-tokens COUNT
  --seed INTEGER
  --request-timeout-seconds COUNT
  --timeout-seconds COUNT
  --output PATH`);
};

/**
 * @param {string} name
 * @param {string | undefined} value
 * @param {number} fallback
 */
const positiveInteger = (name, value, fallback) => {
  if (value === undefined) return fallback;

  const parsed = Number(value);

  if (!Number.isSafeInteger(parsed) || parsed < 1) {
    throw new Error(`--${name} must be a positive integer`);
  }

  return parsed;
};

/** @returns {Options | null} */
const parseOptions = () => {
  const { values } = parseArgs({
    args: process.argv.slice(2),
    options: {
      "base-url": { type: "string" },
      model: { type: "string" },
      pairs: { type: "string" },
      "target-input-tokens": { type: "string" },
      "max-output-tokens": { type: "string" },
      seed: { type: "string" },
      "request-timeout-seconds": { type: "string" },
      "timeout-seconds": { type: "string" },
      output: { type: "string" },
      help: { type: "boolean" },
    },
    strict: true,
  });

  if (values.help) return null;

  const model = values.model ?? "z-ai/glm-5.3-flash";

  return {
    baseUrl: (values["base-url"] ?? "https://api.gradiated.com").replace(
      /\/$/,
      "",
    ),
    model,
    pairs: positiveInteger("pairs", values.pairs, 3),
    targetInputTokens: positiveInteger(
      "target-input-tokens",
      values["target-input-tokens"],
      10_000,
    ),
    maxOutputTokens: positiveInteger(
      "max-output-tokens",
      values["max-output-tokens"],
      16,
    ),
    seed: positiveInteger("seed", values.seed, 20_260_827),
    requestTimeoutSeconds: positiveInteger(
      "request-timeout-seconds",
      values["request-timeout-seconds"],
      120,
    ),
    timeoutSeconds: positiveInteger(
      "timeout-seconds",
      values["timeout-seconds"],
      1_200,
    ),
    output:
      values.output ?? `/tmp/${model.replaceAll("/", "-")}-cache-profile.json`,
  };
};

/**
 * @param {number} seed
 * @param {number} pair
 * @param {number} targetInputTokens
 */
const makePrompt = (seed, pair, targetInputTokens) => {
  const prefix = `cache-profile-${seed}-${pair} `;
  const phrase = "alpha beta gamma delta epsilon zeta eta theta ";
  return prefix + phrase.repeat(Math.ceil(targetInputTokens / 8));
};

/** @param {StreamChunk} chunk */
const hasUsableOutput = (chunk) =>
  chunk.choices?.some(
    ({ delta }) =>
      (typeof delta?.content === "string" && delta.content.length > 0) ||
      (typeof delta?.reasoning_content === "string" &&
        delta.reasoning_content.length > 0) ||
      (typeof delta?.reasoning === "string" && delta.reasoning.length > 0) ||
      (Array.isArray(delta?.tool_calls) && delta.tool_calls.length > 0),
  ) ?? false;

/** @param {ProfileRequest} request */
const openStream = async ({ apiKey, options, pair, prompt, deadline }) => {
  const remainingMilliseconds = deadline - Date.now();

  if (remainingMilliseconds <= 0) throw new Error("profile deadline elapsed");

  const response = await fetch(`${options.baseUrl}/chat/completions`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${apiKey}`,
      "content-type": "application/json",
      "x-gradiated-session-id": `cache-profile-${options.seed}-${pair}`,
    },
    body: JSON.stringify({
      model: options.model,
      messages: [{ role: "user", content: prompt }],
      max_completion_tokens: options.maxOutputTokens,
      temperature: 0,
      stream: true,
    }),
    signal: AbortSignal.timeout(
      Math.min(options.requestTimeoutSeconds * 1_000, remainingMilliseconds),
    ),
  });
  const headersAt = performance.now();

  if (!response.ok || !response.body) {
    const body = (await response.text()).slice(0, 500);
    throw new Error(`request failed with HTTP ${response.status}: ${body}`);
  }

  return { status: response.status, body: response.body, headersAt };
};

/** @param {ReadableStream<Uint8Array>} body */
const readStream = async (body) => {
  /** @type {number | null} */
  let firstTokenAt = null;
  /** @type {StreamUsage | null} */
  let usage = null;
  /** @type {string | null} */
  let finishReason = null;
  let buffer = "";
  const decoder = new TextDecoder();

  for await (const bytes of body) {
    buffer += decoder.decode(bytes, { stream: true }).replaceAll("\r\n", "\n");
    let boundary = buffer.indexOf("\n\n");

    while (boundary !== -1) {
      const event = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);

      for (const line of event.split("\n")) {
        if (!line.startsWith("data:")) continue;

        const data = line.slice(5).trim();

        if (!data || data === "[DONE]") continue;

        /** @type {StreamChunk} */
        const chunk = JSON.parse(data);

        if (firstTokenAt === null && hasUsableOutput(chunk)) {
          firstTokenAt = performance.now();
        }

        if (chunk.usage) usage = chunk.usage;
        finishReason =
          chunk.choices?.find((choice) => choice.finish_reason)
            ?.finish_reason ?? finishReason;
      }

      boundary = buffer.indexOf("\n\n");
    }
  }

  if (!usage || firstTokenAt === null) {
    throw new Error("stream did not contain output and terminal usage");
  }

  return { firstTokenAt, usage, finishReason, completedAt: performance.now() };
};

/** @param {number} milliseconds */
const rounded = (milliseconds) => Number(milliseconds.toFixed(2));

/** @param {ProfileRequest} request */
const runRequest = async (request) => {
  const started = performance.now();
  const { status, body, headersAt } = await openStream(request);
  const { firstTokenAt, usage, finishReason, completedAt } =
    await readStream(body);

  const outputTokens = usage.completion_tokens;
  const generationMilliseconds = completedAt - firstTokenAt;

  return {
    pair: request.pair,
    arm: request.arm,
    status,
    finish_reason: finishReason,
    input_tokens: usage.prompt_tokens,
    cached_input_tokens: usage.prompt_tokens_details?.cached_tokens ?? null,
    output_tokens: outputTokens,
    response_header_ms: rounded(headersAt - started),
    ttft_ms: rounded(firstTokenAt - started),
    total_ms: rounded(completedAt - started),
    tpot_ms:
      outputTokens > 1
        ? rounded(generationMilliseconds / (outputTokens - 1))
        : null,
  };
};

const main = async () => {
  const options = parseOptions();

  if (!options) {
    printUsage();
    return;
  }

  const apiKey = process.env.GRADIATED_API_KEY;

  if (!apiKey) throw new Error("GRADIATED_API_KEY is required");

  const deadline = Date.now() + options.timeoutSeconds * 1_000;
  const results = [];

  for (let pair = 1; pair <= options.pairs; pair += 1) {
    const prompt = makePrompt(options.seed, pair, options.targetInputTokens);

    for (const arm of arms) {
      const result = await runRequest({
        apiKey,
        options,
        pair,
        arm,
        prompt,
        deadline,
      });
      results.push(result);
      console.log(JSON.stringify(result));
    }
  }

  const artifact = {
    schema_version: 1,
    measured_at: new Date().toISOString(),
    model: options.model,
    seed: options.seed,
    pairs: options.pairs,
    target_input_tokens: options.targetInputTokens,
    max_output_tokens: options.maxOutputTokens,
    request_timeout_seconds: options.requestTimeoutSeconds,
    timeout_seconds: options.timeoutSeconds,
    results,
  };
  await writeFile(options.output, `${JSON.stringify(artifact, null, 2)}\n`, {
    mode: 0o600,
  });
  console.log(`wrote ${options.output}`);
};

await main();
