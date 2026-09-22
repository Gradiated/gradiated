import { choice, noul, score, TypeSafeClient } from "@typesafe-ai/sdk";
import OpenAI from "openai";
import { describe, expect, it } from "vitest";

import type { RuntimeKind } from "./mock-runtimes/server.js";
import { useCases, type JsonObject } from "./support.js";

const { makeCase } = useCases();

const headerRecord = (response: Response): Record<string, string> => {
  const headers: Record<string, string> = {};
  response.headers.forEach((value, key) => (headers[key] = value));
  return headers;
};

describe.each(["kev", "vllm"] as RuntimeKind[])("%s responses", (kind) => {
  it.each([0, 40, 100])(
    "settles authoritative usage exactly once (cached=%i)",
    async (cached) => {
      const instance = await makeCase(kind);
      instance.runtimes[0]!.enqueue({ cached });
      const response = await instance.post({ session_id: "synthetic-session" });
      expect(response.status, response.text).toBe(200);
      expect(response.headers["x-gradiated-service-tier"]).toBe("default");
      expect(response.json().model).toBe(instance.model);
      const output = kind === "kev" ? 0 : 3;
      const properties = await instance.settled(
        response,
        "succeeded",
        (100 - cached) * 10 + cached * 2 + output * 20,
      );
      const usage = properties.usage as JsonObject;
      expect(usage.input_tokens).toBe(100);
      expect(usage.cached_input_tokens).toBe(cached);
      expect(usage.output_tokens).toBe(output);
      expect(instance.runtimes[0]!.calls[0]!.model).toBe(instance.runtimeModel);
      expect(instance.runtimes[0]!.calls[0]).not.toHaveProperty("session_id");
    },
  );

  it.each([
    { fault: "model" },
    { fault: "missing_usage" },
    { fault: "cached_overflow" },
    { fault: "negative_usage" },
    { fault: "fractional_usage" },
    { fault: "unsafe_integer" },
    { fault: "shape" },
  ])(
    "fails closed on an invalid runtime response ($fault)",
    async ({ fault }) => {
      const instance = await makeCase(kind);
      instance.runtimes[0]!.enqueue({
        mutate: (body: any) => {
          if (fault === "model") {
            body.model = "PRIVATE_RUNTIME_DETAIL";
          } else if (fault === "missing_usage") {
            delete body.usage;
          } else if (fault === "shape") {
            body[kind === "kev" ? "answers" : "choices"] = {};
          } else if (fault === "cached_overflow") {
            if (kind === "kev") body.usage.cached_input_tokens = 101;
            else body.usage.prompt_tokens_details.cached_tokens = 101;
          } else {
            const replacement = {
              negative_usage: -1,
              fractional_usage: 1.5,
              unsafe_integer: 2 ** 53,
            }[fault]!;
            body.usage[kind === "kev" ? "input_tokens" : "prompt_tokens"] =
              replacement;
          }
        },
      });
      const response = await instance.post();
      expect(response.status).toBe(503);
      expect(response.text).not.toContain("PRIVATE_RUNTIME_DETAIL");
      await instance.settled(response, "failed", 0);
      expect(instance.runtimes[0]!.calls).toHaveLength(1);
    },
  );

  it("rejects a protocol and model mismatch", async () => {
    const instance = await makeCase(kind);
    const other = kind === "kev" ? "/v1/chat/completions" : "/v1/systemone";
    const body =
      kind === "kev"
        ? { model: instance.model, messages: [{}] }
        : {
            model: instance.model,
            state: "x",
            questions: { q: { type: "noul", instructions: "x" } },
          };
    const response = await instance.http.post(other, {
      headers: instance.headers,
      json: body,
    });
    expect(response.status).toBe(400);
    expect(instance.runtimes[0]!.calls).toEqual([]);
  });
});

describe("vLLM chat parameters", () => {
  it.each([
    { tier: "default", priority: 0, charge: 1060 },
    { tier: "fast", priority: -10, charge: 1590 },
    { tier: "flex", priority: 10, charge: 742 },
  ])("prices the $tier tier", async ({ tier, priority, charge }) => {
    const instance = await makeCase("vllm");
    const response = await instance.post({
      service_tier: tier,
      temperature: 0.25,
      max_tokens: 8,
    });
    expect(response.status).toBe(200);
    expect(response.headers["x-gradiated-service-tier"]).toBe(tier);
    await instance.settled(response, "succeeded", charge);
    expect(instance.runtimes[0]!.calls[0]!.priority).toBe(priority);
    expect(instance.runtimes[0]!.calls[0]!.temperature).toBe(0.25);
    expect(instance.runtimes[0]!.calls[0]!.max_tokens).toBe(8);
  });

  it.each([
    { field: "max_tokens", value: 257 },
    { field: "max_tokens", value: 0 },
    { field: "temperature", value: 3 },
    { field: "temperature", value: "hot" },
  ])(
    "rejects an invalid advertised parameter ($field=$value)",
    async ({ field, value }) => {
      const instance = await makeCase("vllm");
      expect((await instance.post({ [field]: value })).status).toBe(400);
      expect(instance.runtimes[0]!.calls).toEqual([]);
      expect(await instance.settlements()).toEqual([]);
    },
  );

  it("forwards only advertised parameters to the runtime", async () => {
    const instance = await makeCase("vllm");
    const response = await instance.post({
      temperature: 0.1,
      unadvertised_synthetic_flag: "must-not-reach-runtime",
    });
    expect(response.status).toBe(200);
    expect(instance.runtimes[0]!.calls[0]!.temperature).toBe(0.1);
    expect(instance.runtimes[0]!.calls[0]).not.toHaveProperty(
      "unadvertised_synthetic_flag",
    );
    await instance.settled(response);
  });
});

describe("Kev decisions", () => {
  it.each([
    { stream: true },
    { max_tokens: 1 },
    { service_tier: "fast" },
    { questions: {} },
    { state: null },
  ])("rejects the unsupported feature %o", async (change) => {
    const instance = await makeCase("kev");
    expect((await instance.post(change)).status).toBe(400);
    expect(instance.runtimes[0]!.calls).toEqual([]);
    expect(await instance.settlements()).toEqual([]);
  });

  it("never bills serialized answer tokens", async () => {
    const instance = await makeCase("kev");
    instance.runtimes[0]!.enqueue({
      mutate: (body: any) => (body.usage.output_tokens = 7),
    });
    const response = await instance.post();
    expect(response.status).toBe(503);
    await instance.settled(response, "failed", 0);
  });

  it("answers every type through the official TypeSafe SDK", async () => {
    const instance = await makeCase("kev");
    const sdk = new TypeSafeClient({
      apiKey: instance.key,
      baseURL: instance.http.baseUrl.replace(/\/$/, ""),
      defaultModel: instance.model,
      retry: { maxRetries: 0 },
      timeout: 5000,
    });
    const { data, response } = await sdk
      .systemOne({
        state: { ticket: ["synthetic", 1] },
        questions: {
          yes: noul("Is this a ticket?"),
          team: choice("Choose", { billing: null, sales: null }),
          level: score("Urgency", ["low", "high"]),
        },
      })
      .withResponse();
    expect(data.answers.yes.noul).toBe(0.75);
    expect(data.answers.team.choice).toBe("billing");
    expect(data.answers.level.score).toBe(0);
    await instance.settled(
      { headers: headerRecord(response) },
      "succeeded",
      1000,
    );
  });
});

it("returns tool calls through the official chat SDK", async () => {
  const instance = await makeCase("vllm");
  const sdk = new OpenAI({
    apiKey: instance.key,
    baseURL: `${instance.http.baseUrl.replace(/\/$/, "")}/v1`,
    maxRetries: 0,
    timeout: 5000,
  });
  const result = await sdk.chat.completions.create({
    model: instance.model,
    messages: instance.body().messages as any,
    tools: [
      {
        type: "function",
        function: { name: "weather", parameters: { type: "object" } },
      },
    ],
    tool_choice: "auto",
  });
  expect(result.choices[0]!.finish_reason).toBe("tool_calls");
  const call = result.choices[0]!.message.tool_calls![0]!;
  expect(call.type).toBe("function");
  expect(call.type === "function" && call.function.name).toBe("weather");
  expect(result.model).toBe(instance.model);
  expect(await instance.settlements()).toHaveLength(1);
});
