import { describe, expect, it } from "vitest";

import { expectRejected } from "./assertions.js";
import { useCases } from "./case.js";
import { chatChunks, chatMessages, chatSdk } from "./chat.js";
import { eventually } from "./eventually.js";
import { object } from "./json.js";
import type { StreamEvents } from "./mock-runtimes/profile.js";
import type { Fault } from "./mock-runtimes/server.js";

const { makeCase } = useCases();

const INVALID_FRAMES: Record<string, (events: StreamEvents) => void> = {
  wrong_model: (events) => {
    object(events[2]).model = "private/wrong";
  },
  changed_id: (events) => {
    object(events[2]).id = "other-id";
  },
  decreasing_usage: (events) => {
    object(events[0]).usage = {
      prompt_tokens: 100,
      completion_tokens: 4,
      total_tokens: 104,
    };
  },
  invalid_json: (events) => {
    events[2] = "INVALID_PRIVATE_RUNTIME_DETAIL";
  },
  early_done: (events) => {
    events.splice(2, 0, "[DONE]");
  },
};

describe("server-sent events", () => {
  it.each([0, 1, 7])(
    "survives arbitrary byte boundaries (fragment=%i)",
    async (fragment) => {
      const instance = await makeCase("vllm");
      instance.runtimes[0]!.enqueue({ fragment, cached: 40 });

      const response = await instance.http.stream(instance.path, {
        headers: instance.headers,
        json: instance.body({ stream: true }),
      });

      expect(response.status).toBe(200);
      expect(response.headers["content-type"]).toMatch(/^text\/event-stream/);

      const frames: string[] = [];
      for await (const line of response.lines()) {
        if (!line.startsWith("data:")) continue;

        const value = line.slice(5).trim();
        frames.push(value);
        // Settlement must already be durable by the time the client sees the terminator.
        if (value === "[DONE]") {
          expect(await instance.settlements()).toHaveLength(1);
        }
      }

      expect(frames.at(-1)).toBe("[DONE]");
      expect(frames.filter((frame) => frame === "[DONE]")).toHaveLength(1);
      const chunks = chatChunks(frames);
      expect(chunks.every((chunk) => chunk.model === instance.model)).toBe(
        true,
      );

      const text = chunks
        .flatMap((chunk) => chunk.choices)
        .map((choice) => choice.delta.content ?? "")
        .join("");
      expect(text).toBe("Hello 世界");
      expect(chunks.at(-1)?.usage).toMatchObject({
        prompt_tokens_details: { cached_tokens: 40 },
      });
      await instance.settled(response, { charge: 740 });
    },
  );

  it.each<Fault>([
    "missing_usage",
    "missing_done",
    "partial_disconnect",
    "stall",
  ])(
    "never turns an incomplete stream (%s) into success or a retry",
    async (fault) => {
      const instance = await makeCase("vllm", { replicas: 2 });
      for (const runtime of instance.runtimes) runtime.enqueue({ fault });

      const response = await instance.http.stream(instance.path, {
        headers: instance.headers,
        json: instance.body({ stream: true }),
      });

      // Headers precede the runtime stream failure.
      expect(response.status).toBe(200);
      const frames = await response.dataFrames();
      expect(frames).not.toContain("[DONE]");
      expect(object(JSON.parse(frames.at(-1)!)).error).toMatchObject({
        code: "runtime_unavailable",
      });
      await instance.settled(response, {
        status: fault === "stall" ? "cancelled" : "failed",
      });
      expect(instance.totalCalls()).toBe(1);
    },
  );

  it.each(Object.entries(INVALID_FRAMES))(
    "fails closed on an invalid stream frame (%s)",
    async (_, mutateEvents) => {
      const instance = await makeCase("vllm");
      instance.runtimes[0]!.enqueue({ mutateEvents });

      const response = await instance.http.stream(instance.path, {
        headers: instance.headers,
        json: instance.body({ stream: true }),
      });
      const frames = await response.dataFrames();

      expect(frames).not.toContain("[DONE]");
      expect(frames.join("")).not.toContain("INVALID_PRIVATE_RUNTIME_DETAIL");
      await instance.settled(response, { status: "failed" });
    },
  );

  it("rejects a wrong stream content type", async () => {
    const instance = await makeCase("vllm");
    instance.runtimes[0]!.enqueue({ fault: "wrong_content_type" });

    const response = await instance.post({ stream: true });

    expectRejected(response, { code: "runtime_unavailable" });
    await instance.settled(response, { status: "failed", charge: 0 });
  });

  it("cancels the stream and releases the lease when the client disconnects", async () => {
    const instance = await makeCase("vllm");
    instance.runtimes[0]!.enqueue({ fault: "stall" });

    const response = await instance.http.stream(instance.path, {
      headers: instance.headers,
      json: instance.body({ stream: true }),
    });
    // Abandoning the iterator destroys the socket.
    for await (const line of response.lines()) {
      if (line.includes("Hello")) break;
    }

    const properties = await instance.settled(response, {
      status: "cancelled",
    });
    expect(properties.outcome).toMatchObject({ cancellation_owner: "client" });

    await eventually(
      async () => (await instance.redis.zCard(instance.inflightKey)) === 0,
      5000,
      "admission lease was never released",
    );
    expect((await instance.post()).status).toBe(200);
  });

  it("preserves tool arguments across frames", async () => {
    const instance = await makeCase("vllm");
    instance.runtimes[0]!.enqueue({ fragment: 3 });

    const response = await instance.http.stream(instance.path, {
      headers: instance.headers,
      json: instance.body({
        stream: true,
        tools: [{ type: "function", function: { name: "weather" } }],
      }),
    });
    const frames = await response.dataFrames();

    expect(frames.at(-1)).toBe("[DONE]");

    const chunks = chatChunks(frames);
    const calls = chunks
      .flatMap((chunk) => chunk.choices)
      .flatMap((choice) => choice.delta.tool_calls ?? []);
    expect(calls[0]).toMatchObject({
      id: "call_synthetic",
      function: { name: "weather" },
    });
    expect(
      JSON.parse(calls.map((call) => call.function?.arguments ?? "").join("")),
    ).toEqual({ city: "Paris" });
    expect(chunks.at(-2)?.choices[0]?.finish_reason).toBe("tool_calls");
    await instance.settled(response, { charge: 1060 });
  });

  it("streams through the official chat SDK", async () => {
    const instance = await makeCase("vllm");

    const stream = await chatSdk(instance).chat.completions.create({
      model: instance.model,
      messages: chatMessages(),
      stream: true,
      stream_options: { include_usage: true },
    });
    const chunks = [];
    for await (const chunk of stream) chunks.push(chunk);

    const text = chunks
      .flatMap((chunk) => chunk.choices)
      .map((choice) => choice.delta.content ?? "")
      .join("");
    expect(text).toBe("Hello 世界");
    expect(chunks.at(-1)!.usage!.total_tokens).toBe(103);
    expect(await instance.settlements()).toHaveLength(1);
  });
});
