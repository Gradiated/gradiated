import { createHash } from "node:crypto";

import Anthropic from "@anthropic-ai/sdk";
import {
  afterAll,
  afterEach,
  beforeAll,
  describe,
  expect,
  it,
  inject,
} from "vitest";

import { enable, version } from "./adapter-versions.js";
import { expectRejected } from "./assertions.js";
import { useCases, type Case, type CaseOptions } from "./case.js";
import { chatChunks, chatMessages, chatSdk } from "./chat.js";
import { deferred, eventually } from "./eventually.js";
import {
  GatewayProcess,
  GENERATION_TIMEOUT_SECONDS,
  ORGANIZATION_CONCURRENCY_CAP,
} from "./gateway-process.js";
import { object, type JsonObject } from "./json.js";
import { UPSTREAM_DETAILS } from "./mock-runtimes/openrouter.js";
import { Runtime } from "./mock-runtimes/server.js";
import { freePort } from "./ports.js";

const { makeCase } = useCases();

const OPENROUTER_MODEL = "synthetic-author/openrouter-model";
const PLATFORM_KEY = `sk-or-platform-${crypto.randomUUID()}`;
// The catalog price of 100 prompt and 3 completion tokens; OpenRouter reports $0.50.
const CATALOG_CHARGE = 1060;
const OPENROUTER_DIGEST = `sha256:${createHash("sha256")
  .update(JSON.stringify({ capacity: "openrouter", model: OPENROUTER_MODEL }))
  .digest("hex")}`;

let openRouter: Runtime;
let gateway: GatewayProcess;

beforeAll(async () => {
  const stack = inject("stack");
  openRouter = await Runtime.start(
    "openrouter",
    OPENROUTER_MODEL,
    PLATFORM_KEY,
  );
  gateway = await GatewayProcess.start({
    redisUrl: stack.redisUrl,
    databaseUrl: stack.databaseUrl,
    runtimeToken: stack.runtimeToken,
    port: await freePort(),
    generationTimeoutSeconds: GENERATION_TIMEOUT_SECONDS,
    logName: "gateway-openrouter",
    openRouter: { baseUrl: `${openRouter.url}/api/v1`, apiKey: PLATFORM_KEY },
  });
});

afterAll(async () => {
  await gateway?.stop();
  await openRouter?.close();
});

afterEach(() => {
  expect(openRouter.errors).toEqual([]);
  openRouter.calls.length = 0;
  openRouter.headers.length = 0;
});

const mapped = (options: CaseOptions = {}): Promise<Case> =>
  makeCase("vllm", {
    gatewayUrl: gateway.url,
    openRouterModel: OPENROUTER_MODEL,
    ...options,
  });

const expectNoUpstreamDetail = (body: string): void => {
  for (const detail of UPSTREAM_DETAILS) expect(body).not.toContain(detail);
  expect(body).not.toContain(OPENROUTER_MODEL);
  expect(body).not.toContain('"provider"');
};

const servedByOpenRouter = (
  instance: Case,
  response: { headers: Record<string, string> },
) =>
  instance.settled(response, {
    charge: CATALOG_CHARGE,
    releaseDigest: OPENROUTER_DIGEST,
  });

describe("OpenRouter capacity", () => {
  it("serves a mapped model with no deployments at its catalog price", async () => {
    const instance = await mapped({ replicas: 0 });

    const response = await instance.post();

    expect(response.status, response.text).toBe(200);
    const body = response.json();
    expect(body.model).toBe(instance.model);
    expect(body.id).toBe(
      `chatcmpl-${response.headers["x-gradiated-generation-id"]!.replaceAll("-", "")}`,
    );
    const [choice] = body.choices as JsonObject[];
    expect(object(choice!.message)).toEqual({
      role: "assistant",
      content: "Synthetic answer",
      refusal: null,
      reasoning_content: "Synthetic reasoning",
    });
    expect(body.usage).toEqual({
      prompt_tokens: 100,
      completion_tokens: 3,
      total_tokens: 103,
      prompt_tokens_details: { cached_tokens: 0 },
      completion_tokens_details: { reasoning_tokens: 3 },
      cost: 0.00000106,
    });
    expectNoUpstreamDetail(response.text);
    expect(Object.keys(response.headers).join()).not.toMatch(
      /openrouter|x-generation-id/i,
    );
    await servedByOpenRouter(instance, response);

    expect(openRouter.calls).toHaveLength(1);
    const sent = openRouter.calls[0]!;
    expect(sent.model).toBe(OPENROUTER_MODEL);
    // The catalog's 10 and 20 nano-USD a token, in USD per million tokens.
    expect(object(sent.provider).max_price).toEqual({
      prompt: 0.01,
      completion: 0.02,
    });
    expect(sent.messages).toEqual(instance.body().messages);
    expect(openRouter.headers[0]!.authorization).toBe(`Bearer ${PLATFORM_KEY}`);
    expect(JSON.stringify(openRouter.headers[0])).not.toContain(instance.key);
    expect(JSON.stringify(sent)).not.toContain(instance.workspace);
  });

  it("streams through the official SDK with our identity and one usage report", async () => {
    const instance = await mapped({ replicas: 0 });

    const stream = await chatSdk(instance).chat.completions.create({
      model: instance.model,
      messages: chatMessages(),
      stream: true,
      stream_options: { include_usage: true },
    });
    const chunks = [];
    for await (const chunk of stream) chunks.push(chunk);

    expect(
      chunks.map((chunk) => chunk.choices[0]?.delta.content ?? "").join(""),
    ).toBe("Hello 世界");
    expect(chunks.every((chunk) => chunk.model === instance.model)).toBe(true);
    expect(new Set(chunks.map((chunk) => chunk.id)).size).toBe(1);
    expect(
      chunks.filter((chunk) => chunk.choices[0]?.finish_reason),
    ).toHaveLength(1);
    const final = chunks.at(-1)!;
    expect(final.choices).toEqual([]);
    expect(final.usage).toMatchObject({
      prompt_tokens: 100,
      completion_tokens: 3,
      cost: 0.00000106,
    });
    expectNoUpstreamDetail(JSON.stringify(chunks));
    const raw = await instance.settlements();
    expect(raw).toHaveLength(1);
    expect(raw[0]!.properties.served_release_digest).toBe(OPENROUTER_DIGEST);
    expect(raw[0]!.properties.usage).toMatchObject({ charge: CATALOG_CHARGE });
  });

  it.each([false, true])(
    "keeps the Messages and Responses translations (stream=%s)",
    async (stream) => {
      const instance = await mapped({ replicas: 0 });

      const messages = await instance.http.post("/v1/messages", {
        headers: instance.headers,
        json: {
          model: instance.model,
          stream,
          max_tokens: 16,
          messages: [{ role: "user", content: "Synthetic ticket" }],
        },
      });
      const responses = await instance.http.post("/v1/responses", {
        headers: instance.headers,
        json: {
          model: instance.model,
          stream,
          input: "Synthetic ticket",
          store: false,
        },
      });

      for (const response of [messages, responses]) {
        expect(response.status, response.text).toBe(200);
        expectNoUpstreamDetail(response.text);
        expect(response.text).not.toContain("Synthetic reasoning");
        await servedByOpenRouter(instance, response);
      }
      if (stream) {
        expect(messages.text).toContain("event: message_stop");
        expect(responses.text).toContain("event: response.completed");
      } else {
        for (const response of [messages, responses]) {
          expect(response.json().model).toBe(instance.model);
          expect(object(response.json().usage).cost).toBe(0.00000106);
        }
      }
    },
  );

  it("passes the Anthropic SDK a native message", async () => {
    const instance = await mapped({ replicas: 0 });
    const anthropic = new Anthropic({
      apiKey: instance.key,
      baseURL: instance.http.baseUrl.replace(/\/$/, ""),
      maxRetries: 0,
      timeout: 5000,
    });

    const message = await anthropic.messages.create({
      model: instance.model,
      max_tokens: 16,
      messages: [{ role: "user", content: "Synthetic ticket" }],
    });

    expect(message.model).toBe(instance.model);
    expect(message.content).toMatchObject([
      { type: "text", text: "Synthetic answer" },
    ]);
    expect(message.usage).toMatchObject({
      input_tokens: 100,
      output_tokens: 3,
    });
  });

  it.each([
    { name: "unhealthy", status: { healthy: false } },
    { name: "saturated", status: { accepting_requests: false } },
  ])(
    "goes straight to OpenRouter when local capacity is $name",
    async ({ status }) => {
      const instance = await mapped();
      await instance.status(status);

      const response = await instance.post();

      expect(response.status, response.text).toBe(200);
      expect(instance.totalCalls()).toBe(0);
      expect(openRouter.calls).toHaveLength(1);
      await servedByOpenRouter(instance, response);
    },
  );

  it("serves from local capacity whenever it can", async () => {
    const instance = await mapped({ replicas: 2 });

    const response = await instance.post();

    expect(response.status).toBe(200);
    expect(response.json().id).toBe("chatcmpl-synthetic");
    expect(openRouter.calls).toEqual([]);
    await instance.settled(response, { charge: CATALOG_CHARGE });
  });

  it.each([false, true])(
    "falls back after a local failure before any output (stream=%s)",
    async (stream) => {
      const instance = await mapped();
      instance.runtimes[0]!.enqueue({ status: 500 });

      const response = stream
        ? await instance.http.post(instance.path, {
            headers: instance.headers,
            json: instance.body({ stream: true }),
          })
        : await instance.post();

      expect(response.status, response.text).toBe(200);
      expect(instance.totalCalls()).toBe(1);
      expect(openRouter.calls).toHaveLength(1);
      expect(response.text).not.toContain("PRIVATE_RUNTIME_DETAIL");
      if (stream) {
        const chunks = chatChunks(
          response.text
            .split("\n")
            .filter((line) => line.startsWith("data:"))
            .map((line) => line.slice(5).trim()),
        );
        expect(
          chunks.map((chunk) => chunk.choices[0]?.delta.content ?? "").join(""),
        ).toBe("Hello 世界");
      }
      await servedByOpenRouter(instance, response);
    },
  );

  it("returns our own error, settled once, when OpenRouter also fails", async () => {
    const instance = await mapped();
    instance.runtimes[0]!.enqueue({ status: 500 });
    openRouter.enqueue({ status: 402 });

    const response = await instance.post();

    expectRejected(response, { code: "runtime_unavailable" });
    expect(response.text).not.toContain("PRIVATE_RUNTIME_DETAIL");
    await instance.settled(response, {
      status: "failed",
      charge: 0,
      releaseDigest: OPENROUTER_DIGEST,
    });
  });

  it("answers as our saturated capacity would when OpenRouter has no provider", async () => {
    const instance = await mapped();
    await instance.status({ accepting_requests: false });
    // OpenRouter's answer when no endpoint matches the routing preferences.
    openRouter.enqueue({ status: 404 });

    const response = await instance.post();

    expectRejected(response, { code: "capacity_exceeded" });
    expectNoUpstreamDetail(response.text);
    await instance.settled(response, {
      status: "failed",
      charge: 0,
      releaseDigest: OPENROUTER_DIGEST,
    });
  });

  it("keeps a partial local stream failure without splicing OpenRouter output", async () => {
    const instance = await mapped();
    instance.runtimes[0]!.enqueue({ fault: "partial_disconnect" });

    const response = await instance.http.stream(instance.path, {
      headers: instance.headers,
      json: instance.body({ stream: true }),
    });
    const frames = await response.dataFrames();

    expect(frames.at(-1)).toContain('"error"');
    expect(frames.join()).not.toContain("世界");
    expect(openRouter.calls).toEqual([]);
    await instance.settled(response, { status: "failed" });
  });

  it("cancels OpenRouter work and settles once when the client leaves", async () => {
    const instance = await mapped({ replicas: 0 });
    openRouter.enqueue({ fault: "stall" });

    const response = await instance.http.stream(instance.path, {
      headers: instance.headers,
      json: instance.body({ stream: true }),
    });
    // The stall follows OpenRouter's keepalive and first reasoning frame.
    for await (const line of response.lines()) {
      if (line.includes("reasoning_content")) break;
    }

    const properties = await instance.settled(response, {
      status: "cancelled",
      releaseDigest: OPENROUTER_DIGEST,
    });
    expect(properties.outcome).toMatchObject({ cancellation_owner: "client" });
  });

  it("shares one deadline across both attempts", async () => {
    const instance = await mapped();
    const gate = deferred();
    instance.runtimes[0]!.enqueue({ status: 503, gate });
    const pending = instance.post();
    await eventually(
      async () => instance.totalCalls() === 1,
      2000,
      "local attempt",
    );
    // Hold the local attempt until less than the fallback budget remains.
    await new Promise((resolve) =>
      setTimeout(resolve, (GENERATION_TIMEOUT_SECONDS - 0.7) * 1000),
    );
    gate.resolve();

    const response = await pending;

    expectRejected(response, { code: "capacity_exceeded" });
    expect(openRouter.calls).toEqual([]);
    await instance.settled(response, { status: "failed", charge: 0 });
  });
});

describe("OpenRouter wire handling", () => {
  it.each([1, 7])(
    "reassembles OpenRouter frames split at arbitrary bytes (fragment=%i)",
    async (fragment) => {
      const instance = await mapped({ replicas: 0 });
      openRouter.enqueue({ fragment });

      const response = await instance.http.stream(instance.path, {
        headers: instance.headers,
        json: instance.body({ stream: true }),
      });
      const chunks = chatChunks(await response.dataFrames());

      expect(
        chunks.map((chunk) => chunk.choices[0]?.delta.content ?? "").join(""),
      ).toBe("Hello 世界");
      expect(chunks.at(-1)?.usage).toMatchObject({ completion_tokens: 3 });
      await servedByOpenRouter(instance, response);
    },
  );

  it("answers an error in OpenRouter's first event with our own status", async () => {
    const instance = await mapped({ replicas: 0 });
    openRouter.enqueue({
      mutateEvents: (events) => {
        events.splice(1, events.length - 1, {
          ...object(events[1]),
          error: { code: 429, message: "PRIVATE_UPSTREAM_DETAIL" },
        });
      },
    });

    const response = await instance.http.post(instance.path, {
      headers: instance.headers,
      json: instance.body({ stream: true }),
    });

    // With no deployment of ours, the model is unavailable whatever OpenRouter said.
    expectRejected(response, { code: "runtime_unavailable" });
    expect(response.text).not.toContain("PRIVATE_UPSTREAM_DETAIL");
    await instance.settled(response, {
      status: "failed",
      charge: 0,
      releaseDigest: OPENROUTER_DIGEST,
    });
  });

  it("keeps the organization's concurrency cap while OpenRouter serves", async () => {
    const instance = await mapped({ replicas: 0 });
    const gates = Array.from({ length: ORGANIZATION_CONCURRENCY_CAP }, () =>
      deferred(),
    );
    const plans = gates.map((gate) => openRouter.enqueue({ gate }));
    const held = plans.map(() => instance.post());
    for (const plan of plans) await plan.entered.promise;

    const refused = await instance.post();

    expectRejected(refused, { code: "concurrency_exceeded" });
    expect(openRouter.calls).toHaveLength(ORGANIZATION_CONCURRENCY_CAP);
    for (const gate of gates) gate.resolve();
    for (const response of await Promise.all(held)) {
      expect(response.status, response.text).toBe(200);
      await servedByOpenRouter(instance, response);
    }
  });
});

describe("what OpenRouter capacity does not change", () => {
  it("leaves an unmapped model with its own failure", async () => {
    const instance = await makeCase("vllm", { gatewayUrl: gateway.url });
    await instance.status({ accepting_requests: false });

    const response = await instance.post();

    expectRejected(response, { code: "capacity_exceeded" });
    expect(openRouter.calls).toEqual([]);
    await instance.expectNotDispatched();
  });

  it.each(["unavailable", "retired"] as const)(
    "does not serve a %s model",
    async (status) => {
      const instance = await mapped({ replicas: 0 });
      instance.record.status = status;
      await instance.publish();

      const response = await instance.post();

      expectRejected(response, { code: "model_unavailable" });
      expect(openRouter.calls).toEqual([]);
    },
  );

  it("still requires a funded balance", async () => {
    const instance = await mapped({ replicas: 0 });
    await instance.setTenant({ balance: 0 });

    const response = await instance.post();

    expectRejected(response, { code: "insufficient_balance" });
    expect(openRouter.calls).toEqual([]);
  });

  it("keeps a request pinned to its deployment", async () => {
    const instance = await mapped();
    await instance.status({ healthy: false });

    const response = await instance.http.post(instance.path, {
      headers: {
        ...instance.headers,
        "x-gradiated-deployment-id": instance.deployments[0]!.id,
      },
      json: instance.body(),
    });

    expectRejected(response, { code: "runtime_unavailable" });
    expect(openRouter.calls).toEqual([]);
  });

  it("never sends OpenRouter's own traffic back to OpenRouter", async () => {
    const instance = await mapped({
      replicas: 0,
      organizationKind: "distribution_channel",
      organizationName: "OpenRouter",
    });

    const response = await instance.post();
    const catalog = await instance.http.get("/v1/models", {
      headers: instance.headers,
    });

    expectRejected(response, { code: "runtime_unavailable" });
    expect(openRouter.calls).toEqual([]);
    const listed = (catalog.json().data as JsonObject[]).map(
      (model) => model.id,
    );
    expect(listed).not.toContain(instance.model);
  });

  it("serves another distribution channel like a customer", async () => {
    const instance = await mapped({
      replicas: 0,
      organizationKind: "distribution_channel",
    });

    const response = await instance.post();

    expect(response.status, response.text).toBe(200);
    await servedByOpenRouter(instance, response);
  });

  it("lists a mapped model as ready without a residency claim", async () => {
    const instance = await mapped({ replicas: 0 });

    const entry = await instance.ready();

    expect(entry.datacenters).toEqual([]);
    expect(entry.deployment_region).toBeUndefined();
    expectNoUpstreamDetail(JSON.stringify(entry));
  });
});

describe("private adapters", () => {
  it("degrade to the mapped base model on OpenRouter when no deployment can serve", async () => {
    const instance = await mapped();
    await enable(instance);
    const selected = await version(instance);
    await instance.status({ healthy: false });

    const response = await instance.post({ model: selected.selector });

    expect(response.status, response.text).toBe(200);
    expect(response.json().model).toBe(selected.selector);
    expect(instance.totalCalls()).toBe(0);
    expect(openRouter.calls[0]!.model).toBe(OPENROUTER_MODEL);
    const stored = (await instance.settlements())[0]!.properties;
    expect(stored.model_id).toBe(selected.selector);
    expect(stored.served_release_digest).toBe(OPENROUTER_DIGEST);
    expect(stored.usage).toMatchObject({ charge: CATALOG_CHARGE });
  });
});
