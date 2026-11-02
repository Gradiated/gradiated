import { describe, expect, it } from "vitest";

import { useCases } from "./case.js";
import { expectRejected } from "./assertions.js";
import type { JsonObject } from "./json.js";

const { makeCase } = useCases();
const selected = (runtimes: { calls: unknown[] }[], before: number[]): number =>
  runtimes.findIndex((runtime, index) => runtime.calls.length > before[index]!);

const conversation = (opening: string, followup?: string): JsonObject[] => [
  { role: "system", content: "Stable system prompt" },
  { role: "user", content: opening },
  ...(followup
    ? [
        { role: "assistant", content: "Earlier answer" },
        { role: "user", content: followup },
      ]
    : []),
];

describe("content-derived routing fallback", () => {
  it.each(["chat", "messages", "responses"])(
    "%s keeps growing conversations on the same replica and served release without a session key",
    async (protocol) => {
      const instance = await makeCase("vllm", { replicas: 4 });
      for (const deployment of instance.deployments.slice(2))
        deployment.release = {
          ...instance.release,
          runtime_revision: "next-runtime",
        };
      await instance.publish();
      await instance.status();
      const primaries = new Set<number>();
      for (let session = 0; session < 12; session++) {
        let primary = -1;
        for (let turn = 0; turn < 3; turn++) {
          const messages = conversation(
            `Opening question ${session}`,
            turn ? `Follow-up ${turn}` : undefined,
          );
          let path = instance.path;
          let body = instance.body({ messages });
          if (protocol === "messages") {
            path = "/v1/messages";
            body = {
              model: instance.model,
              system: "Stable system prompt",
              max_tokens: 16,
              messages: messages.slice(1),
            };
          } else if (protocol === "responses") {
            path = "/v1/responses";
            body = {
              model: instance.model,
              instructions: "Stable system prompt",
              input: messages.slice(1),
            };
          }
          const before = instance.runtimes.map(
            (runtime) => runtime.calls.length,
          );
          const response = await instance.http.post(path, {
            headers: {
              ...instance.headers,
              "x-codex-turn-metadata": "malformed optional metadata",
            },
            json: body,
          });
          expect(response.status).toBe(200);
          const actual = selected(instance.runtimes, before);
          if (turn === 0) {
            primary = actual;
            primaries.add(primary);
          } else expect(actual).toBe(primary);
        }
      }
      expect(primaries.size).toBeGreaterThan(1);
    },
  );

  it("explicit session keys override content changes", async () => {
    const instance = await makeCase("vllm", { replicas: 4 });
    for (const header of [
      "x-gradiated-session-id",
      "x-claude-code-session-id",
      "x-opencode-session-id",
      "session-id",
    ]) {
      let primary = -1;
      for (let turn = 0; turn < 3; turn++) {
        const before = instance.runtimes.map((runtime) => runtime.calls.length);
        const response = await instance.http.post(instance.path, {
          headers: { ...instance.headers, [header]: `stable-${header}` },
          json: instance.body({
            messages: conversation(`Completely changed opening ${turn}`),
          }),
        });
        expect(response.status).toBe(200);
        const actual = selected(instance.runtimes, before);
        if (turn === 0) primary = actual;
        else expect(actual).toBe(primary);
      }
    }
  });

  it("unrecognized message shapes route using the first 8192 characters and preserve capacity failover", async () => {
    const instance = await makeCase("vllm", { replicas: 4 });
    const body = {
      model: instance.model,
      messages: [{ content: "é".repeat(9000) }],
    };
    let primary = -1;
    for (let turn = 0; turn < 3; turn++) {
      const before = instance.runtimes.map((runtime) => runtime.calls.length);
      const response = await instance.http.post(instance.path, {
        headers: instance.headers,
        json: { ...body, metadata: { turn } },
      });
      expect(response.status).toBe(200);
      const actual = selected(instance.runtimes, before);
      if (turn === 0) primary = actual;
      else expect(actual).toBe(primary);
    }
    instance.runtimes[primary]!.enqueue({ status: 503 });
    const response = await instance.http.post(instance.path, {
      headers: instance.headers,
      json: body,
    });
    expect(response.status).toBe(200);
    expect(
      instance.runtimes.filter(
        (runtime, index) => index !== primary && runtime.calls.length > 0,
      ),
    ).toHaveLength(1);
  });
  it("malformed, oversized and duplicate optional session hints all reach the content fallback", async () => {
    const instance = await makeCase("vllm", { replicas: 4 });
    const baseline = await instance.post();
    expect(baseline.status).toBe(200);
    const primary = instance.runtimes.findIndex(
      (runtime) => runtime.calls.length > 0,
    );
    const cases = [
      { headers: { "x-codex-turn-metadata": "not JSON" } },
      { headers: { "x-codex-turn-metadata": "x".repeat(8193) } },
      { headers: { "x-opencode-session-id": "x".repeat(257) } },
      {
        headers: { "x-claude-code-session-id": ["duplicate-a", "duplicate-b"] },
      },
      { headers: { "x-session-id": ["duplicate-a", "duplicate-b"] } },
      {
        headers: {},
        body: {
          metadata: { user_id: "{broken-json" },
          client_metadata: { session_id: { invalid: true } },
        },
      },
      {
        headers: {},
        body: {
          metadata: {
            user_id: JSON.stringify({ session_id: "x".repeat(257) }),
          },
        },
      },
    ];
    for (const test of cases) {
      const before = instance.runtimes[primary]!.calls.length;
      const response = await instance.http.post(instance.path, {
        headers: { ...instance.headers, ...test.headers },
        json: instance.body(test.body ?? {}),
      });
      expect(response.status).toBe(200);
      expect(instance.runtimes[primary]!.calls).toHaveLength(before + 1);
    }
  });

  it("invalid JSON and invalid explicit keys retain normal errors and do not poison subsequent routing", async () => {
    const instance = await makeCase("vllm", { replicas: 2 });
    for (const content of [
      "{",
      '{"model":',
      '{"model":"a","model":"b"}',
      '{"model":"a"} trailing',
    ]) {
      const response = await instance.http.post(instance.path, {
        headers: { ...instance.headers, "content-type": "application/json" },
        content,
      });
      expectRejected(response, { code: "invalid_request" });
    }
    for (const prompt_cache_key of ["", 123, "x".repeat(257)]) {
      expectRejected(await instance.post({ prompt_cache_key }), {
        code: "invalid_request",
        param: "prompt_cache_key",
      });
    }
    expect(instance.totalCalls()).toBe(0);
    expect((await instance.post()).status).toBe(200);
  });

  it("all replicas rejecting capacity return a bounded error and the next request recovers", async () => {
    const instance = await makeCase("vllm", { replicas: 2 });
    for (const runtime of instance.runtimes) runtime.enqueue({ status: 503 });
    const response = await instance.post();
    expectRejected(response, { code: "capacity_exceeded" });
    expect(instance.totalCalls()).toBe(2);
    await instance.settled(response, { status: "failed", charge: 0 });
    expect((await instance.post()).status).toBe(200);
    expect(instance.totalCalls()).toBe(3);
  });

  it.each([
    {
      name: "unhealthy",
      overrides: { healthy: false },
      code: "runtime_unavailable" as const,
    },
    {
      name: "busy",
      overrides: { accepting_requests: false },
      code: "capacity_exceeded" as const,
    },
  ])(
    "content affinity does not dispatch to $name replicas",
    async ({ overrides, code }) => {
      const instance = await makeCase("vllm", { replicas: 2 });
      await instance.status(overrides);
      expectRejected(await instance.post(), { code });
      expect(instance.totalCalls()).toBe(0);
    },
  );
});
