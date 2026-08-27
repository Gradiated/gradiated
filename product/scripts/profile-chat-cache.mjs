#!/usr/bin/env node

import { writeFile } from "node:fs/promises";
import { performance } from "node:perf_hooks";

const defaults = {
  baseUrl: "https://api.gradiated.com/openai/v1",
  model: "z-ai/glm-5.3-flash",
  pairs: 3,
  targetInputTokens: 10_000,
  maxOutputTokens: 16,
  seed: 20_260_827,
  requestTimeoutSeconds: 120,
  timeoutSeconds: 1_200,
  output: "/tmp/glm-5.3-flash-cache-profile.json",
};

const usage = () => {
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

const positiveInteger = (name, value) => {
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < 1) {
    throw new Error(`${name} must be a positive integer`);
  }
  return parsed;
};

const parseArguments = (arguments_) => {
  const options = { ...defaults };
  for (let index = 0; index < arguments_.length; index += 2) {
    const name = arguments_[index];
    if (name === "--help") {
      usage();
      process.exit(0);
    }
    const value = arguments_[index + 1];
    if (!value) {
      throw new Error(`${name ?? "argument"} requires a value`);
    }
    switch (name) {
      case "--base-url":
        options.baseUrl = value.replace(/\/$/, "");
        break;
      case "--model":
        options.model = value;
        break;
      case "--pairs":
        options.pairs = positiveInteger(name, value);
        break;
      case "--target-input-tokens":
        options.targetInputTokens = positiveInteger(name, value);
        break;
      case "--max-output-tokens":
        options.maxOutputTokens = positiveInteger(name, value);
        break;
      case "--seed":
        options.seed = positiveInteger(name, value);
        break;
      case "--request-timeout-seconds":
        options.requestTimeoutSeconds = positiveInteger(name, value);
        break;
      case "--timeout-seconds":
        options.timeoutSeconds = positiveInteger(name, value);
        break;
      case "--output":
        options.output = value;
        break;
      default:
        throw new Error(`unknown option: ${name}`);
    }
  }
  return options;
};

const makePrompt = (seed, pair, targetInputTokens) => {
  const prefix = `cache-profile-${seed}-${pair} `;
  const phrase = "alpha beta gamma delta epsilon zeta eta theta ";
  return prefix + phrase.repeat(Math.ceil(targetInputTokens / 8));
};

const hasUsableOutput = (chunk) =>
  chunk?.choices?.some((choice) => {
    const delta = choice?.delta;
    return (
      (typeof delta?.content === "string" && delta.content.length > 0) ||
      (typeof delta?.reasoning_content === "string" &&
        delta.reasoning_content.length > 0) ||
      (typeof delta?.reasoning === "string" && delta.reasoning.length > 0) ||
      (Array.isArray(delta?.tool_calls) && delta.tool_calls.length > 0)
    );
  }) ?? false;

const runRequest = async ({ apiKey, options, pair, arm, prompt, deadline }) => {
  const started = performance.now();
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

  let firstTokenAt = null;
  let usageValue = null;
  let finishReason = null;
  let buffer = "";
  const decoder = new TextDecoder();
  for await (const bytes of response.body) {
    buffer += decoder.decode(bytes, { stream: true }).replaceAll("\r\n", "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const event = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      for (const line of event.split("\n")) {
        if (!line.startsWith("data:")) continue;
        const data = line.slice(5).trim();
        if (!data || data === "[DONE]") continue;
        const chunk = JSON.parse(data);
        if (firstTokenAt === null && hasUsableOutput(chunk)) {
          firstTokenAt = performance.now();
        }
        if (chunk.usage) usageValue = chunk.usage;
        const reason = chunk?.choices?.find(
          (choice) => choice?.finish_reason,
        )?.finish_reason;
        if (reason) finishReason = reason;
      }
      boundary = buffer.indexOf("\n\n");
    }
  }
  const completed = performance.now();
  if (!usageValue || firstTokenAt === null) {
    throw new Error("stream did not contain output and terminal usage");
  }

  const outputTokens = usageValue.completion_tokens;
  const generationMilliseconds = completed - firstTokenAt;
  return {
    pair,
    arm,
    status: response.status,
    finish_reason: finishReason,
    input_tokens: usageValue.prompt_tokens,
    cached_input_tokens:
      usageValue.prompt_tokens_details?.cached_tokens ?? null,
    output_tokens: outputTokens,
    response_header_ms: Number((headersAt - started).toFixed(2)),
    ttft_ms: Number((firstTokenAt - started).toFixed(2)),
    total_ms: Number((completed - started).toFixed(2)),
    tpot_ms:
      outputTokens > 1
        ? Number((generationMilliseconds / (outputTokens - 1)).toFixed(2))
        : null,
  };
};

const main = async () => {
  const options = parseArguments(process.argv.slice(2));
  const apiKey = process.env.GRADIATED_API_KEY;
  if (!apiKey) throw new Error("GRADIATED_API_KEY is required");

  const deadline = Date.now() + options.timeoutSeconds * 1_000;
  const results = [];
  for (let pair = 1; pair <= options.pairs; pair += 1) {
    const prompt = makePrompt(options.seed, pair, options.targetInputTokens);
    for (const arm of ["cold", "warm"]) {
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
