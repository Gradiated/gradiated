// Independent anchors for the mocks, not an assertion of GPU/model parity.
import { describe, expect, it } from "vitest";

import { Client } from "./http-client.js";
import type { JsonObject } from "./json.js";
import * as kev from "./mock-runtimes/kev.js";
import type { RuntimeProfile } from "./mock-runtimes/profile.js";
import {
  Runtime,
  type PlanOptions,
  type RuntimeKind,
} from "./mock-runtimes/server.js";
import * as vllm from "./mock-runtimes/vllm.js";

const kevBody = {
  model: "fixture/model",
  state: "x",
  priority: 0,
  questions: { q: { type: "noul", instructions: "x" } },
};

const vllmBody = {
  model: "fixture/model",
  messages: [{ role: "user", content: "x" }],
  stream: false,
  max_tokens: 16,
  priority: 0,
};

const vllmStreamBody = {
  ...vllmBody,
  stream: true,
  stream_options: { include_usage: true, continuous_usage_stats: true },
};

const profiles: {
  kind: RuntimeKind;
  profile: RuntimeProfile;
  body: JsonObject;
}[] = [
  { kind: "kev", profile: kev.profile, body: kevBody },
  { kind: "vllm", profile: vllm.profile, body: vllmBody },
];

describe.each(profiles)("$kind mock", ({ kind, profile, body }) => {
  it("requires runtime auth over real HTTP", async () => {
    const runtime = await Runtime.start(
      kind,
      "fixture/model",
      "synthetic-runtime-key",
    );
    try {
      const http = new Client(runtime.url, 2000);
      expect((await http.get("/health")).status).toBe(200);
      expect((await http.post(profile.path, { json: {} })).status).toBe(401);
      expect(runtime.calls).toEqual([]);
      expect(runtime.errors).toEqual([]);
    } finally {
      await runtime.close();
    }
  });

  it("accepts a valid request", () => {
    expect(() => profile.validate(body, "fixture/model")).not.toThrow();
  });

  it("rejects a wrong private model", () => {
    expect(() =>
      profile.validate({ ...body, model: "wrong" }, "fixture/model"),
    ).toThrow("wrong private model");
  });
});

it.each<{ plan: PlanOptions; stream: boolean; ignored: string }>([
  { plan: { fault: "stall" }, stream: false, ignored: "fault stall" },
  { plan: { fault: "oversize" }, stream: true, ignored: "fault oversize" },
  {
    plan: { status: 500, fault: "stall" },
    stream: true,
    ignored: "fault stall",
  },
  { plan: { errorUsage: {} }, stream: false, ignored: "errorUsage" },
  { plan: { mutateEvents: () => {} }, stream: false, ignored: "mutateEvents" },
  { plan: { mutateBody: () => {} }, stream: true, ignored: "mutateBody" },
])(
  "records a plan that does not apply as a contract violation ($ignored, stream: $stream)",
  async ({ plan, stream, ignored }) => {
    const runtime = await Runtime.start("vllm", "fixture/model", "token");
    try {
      runtime.enqueue(plan);
      const http = new Client(runtime.url, 2000);

      const response = await http.post(vllm.profile.path, {
        headers: { Authorization: "Bearer token" },
        json: stream ? vllmStreamBody : vllmBody,
      });

      expect(response.status).toBe(500);
      expect(runtime.errors).toEqual([`the plan does not apply: ${ignored}`]);
    } finally {
      await runtime.close();
    }
  },
);

it("emits vLLM usage and chunk shapes the official client types accept", () => {
  // The structural check against `ChatCompletion`/`ChatCompletionChunk` lives in
  // mock-runtimes/vllm.ts and is enforced by `tsc`; these are the value anchors.
  const body = {
    model: "fixture/model",
    messages: [{ role: "user", content: "x" }],
  };
  expect(vllm.response(body, 40)).toMatchObject({
    object: "chat.completion",
    choices: [{ message: { role: "assistant" } }],
    usage: { total_tokens: 103, prompt_tokens_details: { cached_tokens: 40 } },
  });

  const events = vllm.events(body, 40);
  expect(events.at(-1)).toBe("[DONE]");
  expect(events.at(-2)).toMatchObject({
    choices: [],
    usage: { total_tokens: 103 },
  });
});

it("gives the Kev mock fixed prefill-only usage and named typed answers", () => {
  expect(kev.response(kevBody, 40)).toEqual({
    model: "fixture/model",
    answers: { q: { type: "noul", noul: 0.75 } },
    usage: { input_tokens: 100, cached_input_tokens: 40, output_tokens: 0 },
  });
});

it.each([
  { shape: "a list", questions: [{ type: "noul", instructions: "x" }] },
  { shape: "no type", questions: { q: { instructions: "x" } } },
  { shape: "no instructions", questions: { q: { type: "noul" } } },
])("rejects malformed Kev questions ($shape)", ({ questions }) => {
  expect(() =>
    kev.validate({ ...kevBody, questions }, "fixture/model"),
  ).toThrow();
});
