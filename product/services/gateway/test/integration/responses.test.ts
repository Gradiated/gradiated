import { choice, noul, score, TypeSafeClient } from "@typesafe-ai/sdk";
import { SystemOneResponseSchema } from "@gradiated/contracts";
import { describe, expect, it } from "vitest";

import {
  expectRejected,
  type ErrorCode,
  type Rejection,
} from "./assertions.js";
import { useCases } from "./case.js";
import { chatMessages, chatSdk } from "./chat.js";
import { object, type JsonObject, type JsonValue } from "./json.js";
import { RUNTIME_KINDS } from "./mock-runtimes/server.js";

const { makeCase } = useCases();

const headerRecord = (response: Response): Record<string, string> => {
  const headers: Record<string, string> = {};
  response.headers.forEach((value, key) => (headers[key] = value));
  return headers;
};

describe.each(RUNTIME_KINDS)("%s responses", (kind) => {
  it.each([0, 40, 100])(
    "settles authoritative usage exactly once (cached=%i)",
    async (cached) => {
      const instance = await makeCase(kind);
      instance.runtimes[0]!.enqueue({ cached });

      const response = await instance.post({ session_id: "synthetic-session" });

      expect(response.status, response.text).toBe(200);
      expect(response.headers["x-gradiated-service-tier"]).toBe("default");
      expect(response.json().model).toBe(instance.model);
      if (kind === "kev") {
        expect(SystemOneResponseSchema.safeParse(response.json()).success).toBe(
          true,
        );
      }

      const output = kind === "kev" ? 0 : 3;
      const properties = await instance.settled(response, {
        charge: (100 - cached) * 10 + cached * 2 + output * 20,
      });
      expect(properties.usage).toMatchObject({
        input_tokens: 100,
        cached_input_tokens: cached,
        output_tokens: output,
      });
      expect(instance.runtimes[0]!.calls[0]!.model).toBe(instance.runtimeModel);
      expect(instance.runtimes[0]!.calls[0]).not.toHaveProperty("session_id");
    },
  );

  const usage = kind === "kev" ? "input_tokens" : "prompt_tokens";
  const setUsage = (body: JsonObject, value: number): void => {
    object(body.usage)[usage] = value;
  };

  it.each<{ fault: string; mutateBody: (body: JsonObject) => void }>([
    {
      fault: "model",
      mutateBody: (body) => {
        body.model = "PRIVATE_RUNTIME_DETAIL";
      },
    },
    {
      fault: "missing_usage",
      mutateBody: (body) => {
        delete body.usage;
      },
    },
    {
      fault: "cached_overflow",
      mutateBody: (body) => {
        const counts = object(body.usage);
        if (kind === "kev") counts.cached_input_tokens = 101;
        else object(counts.prompt_tokens_details).cached_tokens = 101;
      },
    },
    { fault: "negative_usage", mutateBody: (body) => setUsage(body, -1) },
    { fault: "fractional_usage", mutateBody: (body) => setUsage(body, 1.5) },
    { fault: "unsafe_integer", mutateBody: (body) => setUsage(body, 2 ** 53) },
    {
      fault: "shape",
      mutateBody: (body) => {
        body[kind === "kev" ? "answers" : "choices"] = {};
      },
    },
  ])(
    "fails closed on an invalid runtime response ($fault)",
    async ({ mutateBody }) => {
      const instance = await makeCase(kind);
      instance.runtimes[0]!.enqueue({ mutateBody });

      const response = await instance.post();

      expectRejected(response, { code: "runtime_unavailable" });
      expect(response.text).not.toContain("PRIVATE_RUNTIME_DETAIL");
      await instance.settled(response, { status: "failed", charge: 0 });
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

    expectRejected(response, { code: "unsupported_parameter", param: "model" });
    await instance.expectNotDispatched();
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
    await instance.settled(response, { charge });
    expect(instance.runtimes[0]!.calls[0]!.priority).toBe(priority);
    expect(instance.runtimes[0]!.calls[0]!.temperature).toBe(0.25);
    expect(instance.runtimes[0]!.calls[0]!.max_tokens).toBe(8);
  });

  it("caps an output limit above the model maximum", async () => {
    const instance = await makeCase("vllm");

    const response = await instance.post({ max_tokens: 875_091 });

    expect(response.status, response.text).toBe(200);
    expect(instance.runtimes[0]!.calls[0]!.max_tokens).toBe(256);
  });

  it.each<{ field: string; value: JsonValue; rejection: Rejection }>([
    {
      field: "max_tokens",
      value: 0,
      rejection: { code: "invalid_request", param: null },
    },
    {
      field: "temperature",
      value: 3,
      rejection: { code: "invalid_request", param: "temperature" },
    },
    {
      field: "temperature",
      value: "hot",
      rejection: { code: "invalid_request", param: "temperature" },
    },
  ])(
    "rejects an invalid advertised parameter ($field=$value)",
    async ({ field, value, rejection }) => {
      const instance = await makeCase("vllm");

      const response = await instance.post({ [field]: value });

      expectRejected(response, rejection);
      await instance.expectNotDispatched();
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
  it.each<{ change: JsonObject; code: ErrorCode; param: string | null }>([
    { change: { stream: true }, code: "invalid_request", param: null },
    {
      change: { max_tokens: 1 },
      code: "invalid_request",
      param: null,
    },
    {
      change: { service_tier: "fast" },
      code: "unsupported_parameter",
      param: "service_tier",
    },
    { change: { questions: {} }, code: "invalid_request", param: "questions" },
    { change: { state: null }, code: "invalid_request", param: "state" },
  ])(
    "rejects the unsupported feature $change",
    async ({ change, code, param }) => {
      const instance = await makeCase("kev");

      const response = await instance.post(change);

      expectRejected(response, { code, param });
      await instance.expectNotDispatched();
    },
  );

  it("never bills serialized answer tokens", async () => {
    const instance = await makeCase("kev");
    instance.runtimes[0]!.enqueue({
      mutateBody: (body) => {
        object(body.usage).output_tokens = 7;
      },
    });

    const response = await instance.post();

    expectRejected(response, { code: "runtime_unavailable" });
    await instance.settled(response, { status: "failed", charge: 0 });
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
      { charge: 1000 },
    );
  });
});

it("returns tool calls through the official chat SDK", async () => {
  const instance = await makeCase("vllm");

  const result = await chatSdk(instance).chat.completions.create({
    model: instance.model,
    messages: chatMessages(),
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
