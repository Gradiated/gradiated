import OpenAI from "openai";
import { describe, expect, it } from "vitest";

import type { Fault } from "./mock-runtimes/server.js";
import { eventually, useCases } from "./support.js";

const { makeCase } = useCases();

describe("server-sent events", () => {
  it.each([0, 1, 7])(
    "survives arbitrary byte boundaries (fragment=%i)",
    async (fragment) => {
      const instance = await makeCase("vllm");
      instance.runtimes[0]!.enqueue({ fragment, cached: 40 });
      const response = await instance.http.stream("POST", instance.path, {
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
        if (value === "[DONE]")
          expect(await instance.settlements()).toHaveLength(1);
      }
      expect(frames.at(-1)).toBe("[DONE]");
      expect(frames.filter((frame) => frame === "[DONE]")).toHaveLength(1);
      const chunks = frames.slice(0, -1).map((frame) => JSON.parse(frame));
      expect(chunks.every((chunk) => chunk.model === instance.model)).toBe(
        true,
      );
      const text = chunks
        .flatMap((chunk: any) => chunk.choices)
        .map((choice: any) => choice.delta.content ?? "")
        .join("");
      expect(text).toBe("Hello 世界");
      expect(chunks.at(-1).usage.prompt_tokens_details.cached_tokens).toBe(40);
      await instance.settled(response, "succeeded", 740);
    },
  );

  it.each([
    "missing_usage",
    "missing_done",
    "partial_disconnect",
    "stall",
  ] as Fault[])(
    "never turns an incomplete stream (%s) into success or a retry",
    async (fault) => {
      const instance = await makeCase("vllm", { replicas: 2 });
      for (const runtime of instance.runtimes) runtime.enqueue({ fault });
      const response = await instance.http.stream("POST", instance.path, {
        headers: instance.headers,
        json: instance.body({ stream: true }),
      });
      // Headers precede the runtime stream failure.
      expect(response.status).toBe(200);
      const frames = await response.dataFrames();
      expect(frames).not.toContain("[DONE]");
      expect(frames.some((frame) => frame.includes("error"))).toBe(true);
      await instance.settled(
        response,
        fault === "stall" ? "cancelled" : "failed",
      );
      expect(
        instance.runtimes.reduce(
          (total, runtime) => total + runtime.calls.length,
          0,
        ),
      ).toBe(1);
    },
  );

  it.each([
    "wrong_model",
    "changed_id",
    "decreasing_usage",
    "invalid_json",
    "early_done",
  ])("fails closed on an invalid stream frame (%s)", async (fault) => {
    const instance = await makeCase("vllm");
    instance.runtimes[0]!.enqueue({
      mutate: (events: any[]) => {
        if (fault === "wrong_model") events[2].model = "private/wrong";
        else if (fault === "changed_id") events[2].id = "other-id";
        else if (fault === "decreasing_usage") {
          events[0].usage = {
            prompt_tokens: 100,
            completion_tokens: 4,
            total_tokens: 104,
          };
        } else if (fault === "invalid_json")
          events[2] = "INVALID_PRIVATE_RUNTIME_DETAIL";
        else events.splice(2, 0, "[DONE]");
      },
    });
    const response = await instance.http.stream("POST", instance.path, {
      headers: instance.headers,
      json: instance.body({ stream: true }),
    });
    const frames = await response.dataFrames();
    expect(frames).not.toContain("[DONE]");
    expect(frames.join("")).not.toContain("INVALID_PRIVATE_RUNTIME_DETAIL");
    await instance.settled(response, "failed");
  });

  it("rejects a wrong stream content type", async () => {
    const instance = await makeCase("vllm");
    instance.runtimes[0]!.enqueue({ fault: "wrong_content_type" });
    const response = await instance.post({ stream: true });
    expect(response.status).toBe(503);
    await instance.settled(response, "failed", 0);
  });

  it("cancels the stream and releases the lease when the client disconnects", async () => {
    const instance = await makeCase("vllm");
    instance.runtimes[0]!.enqueue({ fault: "stall" });
    const response = await instance.http.stream("POST", instance.path, {
      headers: instance.headers,
      json: instance.body({ stream: true }),
    });
    for await (const line of response.lines()) {
      if (line.includes("Hello")) break; // Abandoning the iterator destroys the socket.
    }
    const properties = await instance.settled(response, "cancelled");
    expect(
      (properties.outcome as Record<string, unknown>).cancellation_owner,
    ).toBe("client");
    await eventually(
      async () =>
        (await instance.redis.zCard(
          `inflight:{settlement-0}:${instance.organization}`,
        )) === 0,
      5000,
      "admission lease was never released",
    );
    expect((await instance.post()).status).toBe(200);
  });

  it("preserves tool arguments across frames", async () => {
    const instance = await makeCase("vllm");
    instance.runtimes[0]!.enqueue({ fragment: 3 });
    const response = await instance.http.stream("POST", instance.path, {
      headers: instance.headers,
      json: instance.body({
        stream: true,
        tools: [{ type: "function", function: { name: "weather" } }],
      }),
    });
    const frames = await response.dataFrames();
    expect(frames.at(-1)).toBe("[DONE]");
    const chunks = frames.slice(0, -1).map((frame) => JSON.parse(frame));
    const calls = chunks
      .flatMap((chunk: any) => chunk.choices)
      .flatMap((choice: any) => choice.delta.tool_calls ?? []);
    expect(calls[0].id).toBe("call_synthetic");
    expect(calls[0].function.name).toBe("weather");
    expect(
      JSON.parse(calls.map((call: any) => call.function.arguments).join("")),
    ).toEqual({
      city: "Paris",
    });
    expect(chunks.at(-2).choices[0].finish_reason).toBe("tool_calls");
    await instance.settled(response, "succeeded", 1060);
  });

  it("streams through the official chat SDK", async () => {
    const instance = await makeCase("vllm");
    const sdk = new OpenAI({
      apiKey: instance.key,
      baseURL: `${instance.http.baseUrl.replace(/\/$/, "")}/v1`,
      maxRetries: 0,
      timeout: 5000,
    });
    const stream = await sdk.chat.completions.create({
      model: instance.model,
      messages: instance.body().messages as any,
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
