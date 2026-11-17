// These catch drift between the mocks and real runtimes. Gateway logic and faults
// belong in the synthetic suite, which is deterministic.
import { describe, expect, inject, it } from "vitest";

import { useCases, type Case } from "./case.js";
import { chatChunks } from "./chat.js";
import { isJsonObject, object, type JsonValue } from "./json.js";
import {
  REAL_RUNTIME_PROFILE,
  type ContainerRuntimeKind,
} from "./stack/real-runtimes.js";

// A ceiling, not a target: the runtimes are warmed before any test runs, so these
// should finish in seconds. Set per test, because a file-level config does not
// reach tests that were already collected.
const LIMIT = 60_000;

const runtimes = inject("realRuntimes");

const { makeCase } = useCases();

const count = (value: JsonValue | undefined): number => {
  if (typeof value !== "number") throw new Error(`not a token count: ${value}`);

  return value;
};

/** A case whose successful responses come from the real server, not the profile. */
const realCase = (kind: ContainerRuntimeKind): Promise<Case> =>
  makeCase(REAL_RUNTIME_PROFILE[kind], {
    upstream: { kind: "proxy", ...runtimes[kind]! },
  });

describe.skipIf(!runtimes["sglang-cpu"])("real LLM runtime", () => {
  it(
    "returns an envelope the gateway accepts, and forwards a faithful request",
    async () => {
      const instance = await realCase("sglang-cpu");
      const response = await instance.post({ max_tokens: 4 });
      expect(response.status, response.text).toBe(200);

      expect(response.json()).toMatchObject({
        object: "chat.completion",
        model: instance.model,
        choices: [
          {
            message: { role: "assistant", content: expect.any(String) },
            finish_reason: expect.any(String),
          },
        ],
      });

      // What the gateway actually put on the wire, observed through the proxy.
      const forwarded = instance.runtimes[0]!.calls[0]!;
      expect(forwarded.model).toBe(runtimes["sglang-cpu"]!.model);
      expect(forwarded.max_tokens).toBe(4);
      expect(forwarded).not.toHaveProperty("service_tier");
      expect(forwarded).not.toHaveProperty("session_id");
    },
    LIMIT,
  );

  it(
    "settles billing from the runtime's own token counts",
    async () => {
      const instance = await realCase("sglang-cpu");
      const response = await instance.post({ max_tokens: 4 });
      expect(response.status).toBe(200);

      const usage = object(response.json().usage);
      const prompt = count(usage.prompt_tokens);
      const completion = count(usage.completion_tokens);
      expect(prompt).toBeGreaterThan(0);
      expect(usage.total_tokens).toBe(prompt + completion);

      // Prices come from the model record, token counts from the runtime. Derive the
      // expectation rather than hardcoding one, because real output length varies.
      const details = usage.prompt_tokens_details;
      const cached = details ? count(object(details).cached_tokens) : 0;
      const expected = (prompt - cached) * 10 + cached * 2 + completion * 20;
      const properties = await instance.settled(response, {
        charge: expected,
      });
      expect(properties.usage).toMatchObject({
        input_tokens: prompt,
        output_tokens: completion,
      });
    },
    LIMIT,
  );

  it(
    "streams real SSE frames through to a terminated stream",
    async () => {
      const instance = await realCase("sglang-cpu");
      const response = await instance.http.stream(instance.path, {
        headers: instance.headers,
        json: instance.body({ stream: true, max_tokens: 4 }),
        timeoutMs: 60_000,
      });
      expect(response.status).toBe(200);
      expect(response.headers["content-type"]).toMatch(/^text\/event-stream/);

      const frames = await response.dataFrames();
      expect(frames.at(-1)).toBe("[DONE]");
      const chunks = chatChunks(frames);
      expect(chunks.every((chunk) => chunk.model === instance.model)).toBe(
        true,
      );
      const text = chunks
        .flatMap((chunk) => chunk.choices)
        .map((choice) => choice.delta.content ?? "")
        .join("");
      expect(text.length).toBeGreaterThan(0);
      // The gateway requires authoritative usage before it will settle a stream.
      expect(chunks.some((chunk) => chunk.usage)).toBe(true);
      await instance.settled(response);
    },
    LIMIT,
  );
});

describe.skipIf(!runtimes.kev)("real decision runtime", () => {
  it(
    "answers a decision and forwards the native request shape",
    async () => {
      const instance = await realCase("kev");
      const response = await instance.post();
      expect(response.status, response.text).toBe(200);

      const body = response.json();
      expect(body.model).toBe(instance.model);
      const answer = object(object(body.answers).q);
      expect(answer.type).toBe("noul");
      expect(count(answer.noul)).toBeGreaterThanOrEqual(0);
      expect(count(answer.noul)).toBeLessThanOrEqual(1);

      const forwarded = instance.runtimes[0]!.calls[0]!;
      expect(forwarded.model).toBe(runtimes.kev!.model);
      expect(forwarded).toHaveProperty("state");
      expect(forwarded).toHaveProperty("questions");
      expect(forwarded).not.toHaveProperty("messages");
      expect(forwarded).not.toHaveProperty("session_id");
    },
    LIMIT,
  );

  it(
    "bills prefill only, with no generated output tokens",
    async () => {
      const instance = await realCase("kev");
      const response = await instance.post();
      expect(response.status).toBe(200);

      const reported = response.json().usage;
      const properties = await instance.settled(response);
      const settled = object(properties.usage);
      // The native decision protocol must never settle generated output.
      expect(settled.output_tokens).toBe(0);
      expect(count(settled.input_tokens)).toBeGreaterThan(0);
      if (isJsonObject(reported) && typeof reported.input_tokens === "number") {
        expect(settled.input_tokens).toBe(reported.input_tokens);
      }
    },
    LIMIT,
  );
});
