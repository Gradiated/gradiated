// Catches drift between the synthetic OpenRouter profile and the live API. The
// gateway's fallback rules belong in openrouter-capacity.test.ts, which is
// deterministic; these only prove that the real service fits them.
import { createHash } from "node:crypto";

import Anthropic from "@anthropic-ai/sdk";
import { afterAll, beforeAll, describe, expect, inject, it } from "vitest";

import { expectRejected } from "./assertions.js";
import { useCases, type Case, type CaseOptions } from "./case.js";
import { chatMessages, chatSdk } from "./chat.js";
import { eventually } from "./eventually.js";
import { GatewayProcess } from "./gateway-process.js";
import { object, type JsonObject } from "./json.js";
import { freePort } from "./ports.js";

const API_KEY = process.env.OPENROUTER_LIVE_API_KEY;
// Several ZDR providers, about $0.00001 a request, and no reasoning to use up
// the small output limits.
const LIVE_MODEL = "meta-llama/llama-3.1-8b-instruct";
const LIMIT = 60_000;
// Nano-USD per token, above every ZDR provider's price for the model, so the
// price cap the gateway sends leaves OpenRouter something to route to.
const PRICES = { prompt: 400, completion: 400 };

const { makeCase } = useCases();

const digest = (model: string): string =>
  `sha256:${createHash("sha256")
    .update(JSON.stringify({ capacity: "openrouter", model }))
    .digest("hex")}`;

// The case's catalog prices; cached prompt tokens keep the test catalog's 2.
const charge = (usage: JsonObject): number => {
  const cached = Number(object(usage.prompt_tokens_details).cached_tokens ?? 0);

  return (
    (Number(usage.prompt_tokens) - cached) * PRICES.prompt +
    cached * 2 +
    Number(usage.completion_tokens) * PRICES.completion
  );
};

const expectNoUpstreamDetail = (body: string): void => {
  expect(body).not.toContain(LIVE_MODEL);
  expect(body).not.toMatch(/openrouter|"provider"|gen-[0-9]/i);
};

describe.skipIf(!API_KEY)("live OpenRouter capacity", () => {
  let gateway: GatewayProcess;

  beforeAll(async () => {
    const stack = inject("stack");
    gateway = await GatewayProcess.start({
      redisUrl: stack.redisUrl,
      databaseUrl: stack.databaseUrl,
      runtimeToken: stack.runtimeToken,
      port: await freePort(),
      generationTimeoutSeconds: 60,
      logName: "gateway-openrouter-live",
      openRouter: { baseUrl: "https://openrouter.ai/api/v1", apiKey: API_KEY! },
    });
  });

  afterAll(async () => {
    await gateway?.stop();
  });

  const mapped = (options: CaseOptions = {}): Promise<Case> =>
    makeCase("vllm", {
      gatewayUrl: gateway.url,
      openRouterModel: LIVE_MODEL,
      prices: PRICES,
      ...options,
    });

  it(
    "serves a mapped model with no deployments at its catalog price",
    async () => {
      const instance = await mapped({ replicas: 0 });

      const response = await instance.post();

      expect(response.status, response.text).toBe(200);
      const body = response.json();
      expect(body.model).toBe(instance.model);
      const [choice] = body.choices as JsonObject[];
      expect(object(choice!.message).content).toEqual(expect.any(String));
      expect(String(object(choice!.message).content).length).toBeGreaterThan(0);
      expectNoUpstreamDetail(response.text);
      const usage = object(body.usage);
      expect(usage.cost).toBeCloseTo(charge(usage) / 1e9, 15);
      await instance.settled(response, {
        charge: charge(usage),
        releaseDigest: digest(LIVE_MODEL),
      });
    },
    LIMIT,
  );

  it(
    "streams through the official SDK with one finish and one usage report",
    async () => {
      const instance = await mapped({ replicas: 0 });

      const stream = await chatSdk(instance).chat.completions.create(
        {
          model: instance.model,
          messages: chatMessages(),
          stream: true,
          stream_options: { include_usage: true },
        },
        { timeout: LIMIT },
      );
      const chunks = [];
      for await (const chunk of stream) chunks.push(chunk);

      const text = chunks
        .map((chunk) => chunk.choices[0]?.delta.content ?? "")
        .join("");
      expect(text.length).toBeGreaterThan(0);
      expect(chunks.every((chunk) => chunk.model === instance.model)).toBe(
        true,
      );
      expect(new Set(chunks.map((chunk) => chunk.id)).size).toBe(1);
      expect(
        chunks.filter((chunk) => chunk.choices[0]?.finish_reason),
      ).toHaveLength(1);
      const final = chunks.at(-1)!;
      expect(final.choices).toEqual([]);
      expectNoUpstreamDetail(JSON.stringify(chunks));
      const settlements = await eventually(
        async () => {
          const rows = await instance.settlements();
          return rows.length > 0 ? rows : undefined;
        },
        5000,
        "no settlement",
      );
      expect(settlements).toHaveLength(1);
      const [settlement] = settlements;
      expect(settlement!.properties.served_release_digest).toBe(
        digest(LIVE_MODEL),
      );
      expect(settlement!.properties.usage).toMatchObject({
        charge: charge(final.usage as unknown as JsonObject),
      });
    },
    LIMIT,
  );

  it.each([false, true])(
    "falls back when our runtime is saturated (stream=%s)",
    async (stream) => {
      const instance = await mapped();
      instance.runtimes[0]!.enqueue({ status: 429 });

      const response = await instance.http.post(instance.path, {
        headers: instance.headers,
        json: instance.body({ stream }),
      });

      expect(response.status, response.text).toBe(200);
      expect(instance.totalCalls()).toBe(1);
      expectNoUpstreamDetail(response.text);
      if (stream) expect(response.text).toContain("data: [DONE]");
      await instance.settled(response, { releaseDigest: digest(LIVE_MODEL) });
    },
    LIMIT,
  );

  it(
    "passes the Anthropic SDK a native message",
    async () => {
      const instance = await mapped({ replicas: 0 });
      const anthropic = new Anthropic({
        apiKey: instance.key,
        baseURL: instance.http.baseUrl.replace(/\/$/, ""),
        maxRetries: 0,
        timeout: LIMIT,
      });

      const message = await anthropic.messages.create({
        model: instance.model,
        max_tokens: 16,
        messages: [{ role: "user", content: "Say hello" }],
      });

      expect(message.model).toBe(instance.model);
      expect(message.content[0]).toMatchObject({ type: "text" });
      expect(message.usage.output_tokens).toBeGreaterThan(0);
    },
    LIMIT,
  );

  it(
    "answers a mapping OpenRouter does not list as our outage, not the caller's mistake",
    async () => {
      const missing = "gradiated-ci/no-such-model";
      const instance = await mapped({ replicas: 0, openRouterModel: missing });

      const response = await instance.post();

      expectRejected(response, { code: "runtime_unavailable" });
      expect(response.text).not.toContain(missing);
      await instance.settled(response, {
        status: "failed",
        charge: 0,
        releaseDigest: digest(missing),
      });
    },
    LIMIT,
  );
  it.each([
    {
      name: "no deployments",
      replicas: 0,
      code: "runtime_unavailable" as const,
    },
    {
      name: "saturated capacity",
      replicas: 1,
      code: "capacity_exceeded" as const,
    },
  ])(
    "answers as our $name would when no provider is under our price",
    async ({ replicas, code }) => {
      const instance = await mapped({
        replicas,
        prices: { prompt: 1, completion: 1 },
      });
      if (replicas > 0) await instance.status({ accepting_requests: false });

      const response = await instance.post();

      expectRejected(response, { code });
      expectNoUpstreamDetail(response.text);
      await instance.settled(response, {
        status: "failed",
        charge: 0,
        releaseDigest: digest(LIVE_MODEL),
      });
    },
    LIMIT,
  );
});
