/**
 * Fidelity checks against real runtimes on CPU: one ordinary LLM and one native
 * decision server, which is enough to route both protocols the gateway speaks.
 *
 * These do not re-test gateway logic — the synthetic suite owns that, deterministically,
 * and covers every fault. Their only job is to catch drift between what our mocks
 * pretend a runtime does and what one actually does: request shape on the wire,
 * response envelope, usage accounting, SSE framing, and that billing settles from
 * token counts the gateway did not choose.
 *
 * Each runtime is independently skipped when unavailable; see the integration README.
 */
import { describe, expect, inject, it } from "vitest";

import type { RuntimeKind } from "./mock-runtimes/server.js";
import { useCases, type JsonObject, type MakeCase } from "./support.js";

// A ceiling, not a target: the runtimes are warmed before any test runs, so these
// should finish in seconds. Set per test, because a file-level config does not
// reach tests that were already collected.
const LIMIT = 60_000;

const runtimes = inject("realRuntimes");

const { makeCase } = useCases();

/** A case whose successful responses come from the real server, not the profile. */
const realCase = (kind: RuntimeKind, make: MakeCase) => {
  const runtime = runtimes[kind]!;
  return make(kind, {
    upstream: { kind: "proxy", baseUrl: runtime.baseUrl },
    runtimeModel: runtime.model,
  });
};

describe.skipIf(!runtimes.vllm)("real LLM runtime", () => {
  it(
    "returns an envelope the gateway accepts, and forwards a faithful request",
    async () => {
      const instance = await realCase("vllm", makeCase);
      const response = await instance.post({ max_tokens: 4 });
      expect(response.status, response.text).toBe(200);

      const body = response.json();
      expect(body.object).toBe("chat.completion");
      expect(body.model).toBe(instance.model);
      expect(body.choices[0].message.role).toBe("assistant");
      expect(typeof body.choices[0].message.content).toBe("string");
      expect(typeof body.choices[0].finish_reason).toBe("string");

      // What the gateway actually put on the wire, observed through the proxy.
      const forwarded = instance.runtimes[0]!.calls[0]!;
      expect(forwarded.model).toBe(runtimes.vllm!.model);
      expect(forwarded.max_tokens).toBe(4);
      expect(forwarded).not.toHaveProperty("service_tier");
      expect(forwarded).not.toHaveProperty("session_id");
    },
    LIMIT,
  );

  it(
    "settles billing from the runtime's own token counts",
    async () => {
      const instance = await realCase("vllm", makeCase);
      const response = await instance.post({ max_tokens: 4 });
      expect(response.status).toBe(200);

      const usage = response.json().usage;
      expect(usage.prompt_tokens).toBeGreaterThan(0);
      expect(usage.total_tokens).toBe(
        usage.prompt_tokens + usage.completion_tokens,
      );

      // Prices come from the model record, token counts from the runtime. Derive the
      // expectation rather than hardcoding one, because real output length varies.
      const cached = usage.prompt_tokens_details?.cached_tokens ?? 0;
      const expected =
        (usage.prompt_tokens - cached) * 10 +
        cached * 2 +
        usage.completion_tokens * 20;
      const properties = await instance.settled(
        response,
        "succeeded",
        expected,
      );
      const settled = properties.usage as JsonObject;
      expect(settled.input_tokens).toBe(usage.prompt_tokens);
      expect(settled.output_tokens).toBe(usage.completion_tokens);
    },
    LIMIT,
  );

  it(
    "streams real SSE frames through to a terminated stream",
    async () => {
      const instance = await realCase("vllm", makeCase);
      const response = await instance.http.stream("POST", instance.path, {
        headers: instance.headers,
        json: instance.body({ stream: true, max_tokens: 4 }),
        timeoutMs: 60_000,
      });
      expect(response.status).toBe(200);
      expect(response.headers["content-type"]).toMatch(/^text\/event-stream/);

      const frames = await response.dataFrames();
      expect(frames.at(-1)).toBe("[DONE]");
      const chunks = frames.slice(0, -1).map((frame) => JSON.parse(frame));
      expect(chunks.every((chunk) => chunk.model === instance.model)).toBe(
        true,
      );
      const text = chunks
        .flatMap((chunk: any) => chunk.choices ?? [])
        .map((choice: any) => choice.delta?.content ?? "")
        .join("");
      expect(text.length).toBeGreaterThan(0);
      // The gateway requires authoritative usage before it will settle a stream.
      expect(chunks.some((chunk: any) => chunk.usage)).toBe(true);
      await instance.settled(response);
    },
    LIMIT,
  );
});

describe.skipIf(!runtimes.kev)("real decision runtime", () => {
  it(
    "answers a decision and forwards the native request shape",
    async () => {
      const instance = await realCase("kev", makeCase);
      const response = await instance.post();
      expect(response.status, response.text).toBe(200);

      const body = response.json();
      expect(body.model).toBe(instance.model);
      expect(body.answers.q.type).toBe("noul");
      expect(body.answers.q.noul).toBeGreaterThanOrEqual(0);
      expect(body.answers.q.noul).toBeLessThanOrEqual(1);

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
      const instance = await realCase("kev", makeCase);
      const response = await instance.post();
      expect(response.status).toBe(200);

      const usage = response.json().usage ?? {};
      const properties = await instance.settled(response);
      const settled = properties.usage as JsonObject;
      // The native decision protocol must never settle generated output.
      expect(settled.output_tokens).toBe(0);
      expect(Number(settled.input_tokens)).toBeGreaterThan(0);
      if (typeof usage.input_tokens === "number") {
        expect(settled.input_tokens).toBe(usage.input_tokens);
      }
    },
    LIMIT,
  );
});
