// Independent anchors for the mocks, not an assertion of GPU/model parity.
import { describe, expect, it } from "vitest";

import { Client } from "./http-client.js";
import * as kev from "./mock-runtimes/kev.js";
import { Runtime, type RuntimeKind } from "./mock-runtimes/server.js";
import * as vllm from "./mock-runtimes/vllm.js";

const profiles = [
  { kind: "kev" as RuntimeKind, profile: kev },
  { kind: "vllm" as RuntimeKind, profile: vllm },
];

describe.each(profiles)("$kind mock", ({ kind, profile }) => {
  it("requires runtime auth over real HTTP", async () => {
    const runtime = await Runtime.start(
      kind,
      "fixture/model",
      "synthetic-runtime-key",
    );
    try {
      const http = new Client(runtime.url, 2000);
      expect((await http.get("/health")).status).toBe(200);
      expect((await http.post(profile.PATH, { json: {} })).status).toBe(401);
      expect(runtime.calls).toEqual([]);
      expect(runtime.errors).toEqual([]);
    } finally {
      await runtime.close();
    }
  });

  it("rejects a wrong private model", () => {
    expect(() =>
      profile.validate({ model: "wrong" }, "fixture/model"),
    ).toThrow();
  });
});

it("emits vLLM usage and chunk shapes the official client types accept", () => {
  // The structural check against `ChatCompletion`/`ChatCompletionChunk` lives in
  // mock-runtimes/vllm.ts and is enforced by `tsc`; these are the value anchors.
  const body = {
    model: "fixture/model",
    messages: [{ role: "user", content: "x" }],
  };
  const result = vllm.response(body, 40) as any;
  expect(result.object).toBe("chat.completion");
  expect(result.choices[0].message.role).toBe("assistant");
  expect(result.usage.prompt_tokens_details.cached_tokens).toBe(40);
  expect(result.usage.total_tokens).toBe(103);

  const events = vllm.events(body, 40);
  expect(events.at(-1)).toBe("[DONE]");
  const chunks = events.slice(0, -1) as any[];
  expect(chunks.at(-1).choices).toEqual([]);
  expect(chunks.at(-1).usage.total_tokens).toBe(103);
});

it("gives the Kev mock fixed prefill-only usage and named typed answers", () => {
  const body = {
    model: "fixture/model",
    state: "x",
    priority: 0,
    questions: { q: { type: "noul", instructions: "x" } },
  };
  kev.validate(body, "fixture/model");
  expect(kev.response(body, 40)).toEqual({
    model: "fixture/model",
    answers: { q: { type: "noul", noul: 0.75 } },
    usage: { input_tokens: 100, cached_input_tokens: 40, output_tokens: 0 },
  });
});
