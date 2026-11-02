import { describe, expect, it } from "vitest";

import { expectRejected } from "./assertions.js";
import { useCases } from "./case.js";
import { chatChunks } from "./chat.js";
import { object, toJsonObject } from "./json.js";
import { externalSglang } from "./stack/real-runtimes.js";
import { sglangEvents, sglangQueueError } from "./sglang-wire.js";
import { smgAdmission, smgAdmissionSample } from "./smg-admission.js";

const { makeCase } = useCases();

describe("native SMG admission metrics", () => {
  it("reads explicit gauges without clamping a capacity violation", () => {
    expect(
      smgAdmission("smg_admission_inflight 16\nsmg_admission_queue_depth 2\n"),
    ).toEqual({ inflight: 16, queued: 2 });
    expect(
      smgAdmission("smg_admission_inflight 17\nsmg_admission_queue_depth 3\n"),
    ).toEqual({ inflight: 17, queued: 3 });
  });

  it("distinguishes missing metrics from explicit zero", () => {
    expect(smgAdmissionSample("smg_admission_inflight 0\n")).toEqual({
      inflight: 0,
      queued: null,
    });
    expect(
      smgAdmission("smg_admission_inflight 0\nsmg_admission_queue_depth 0\n"),
    ).toEqual({ inflight: 0, queued: 0 });
    expect(() => smgAdmission("smg_admission_inflight 0\n")).toThrow(
      "unavailable",
    );
    expect(() =>
      smgAdmission("smg_admission_inflight -1\nsmg_admission_queue_depth 0\n"),
    ).toThrow("invalid");
  });
});

describe("SGLang OpenAI wire through the local gateway", () => {
  it("preserves streamed reasoning and settles cached usage without double-counting reasoning", async () => {
    const instance = await makeCase("vllm");
    instance.runtimes[0]!.enqueue({
      fragment: 1,
      mutateEvents: (events) =>
        events.splice(0, events.length, ...sglangEvents(instance.runtimeModel)),
    });
    const response = await instance.http.stream(instance.path, {
      headers: instance.headers,
      json: instance.body({ stream: true }),
    });
    const frames = await response.dataFrames();
    expect(frames.at(-1)).toBe("[DONE]");
    const chunks = chatChunks(frames);
    expect(
      chunks
        .flatMap((c) => c.choices)
        .map((c) => c.delta.content ?? "")
        .join(""),
    ).toBe("1517");
    expect(
      chunks
        .flatMap((c) => c.choices)
        .map((c) => toJsonObject(c.delta).reasoning_content ?? "")
        .join(""),
    ).toBe("先核对乘法。");
    expect(chunks.at(-1)?.usage).toMatchObject({
      prompt_tokens: 100,
      completion_tokens: 3,
      total_tokens: 103,
      prompt_tokens_details: { cached_tokens: 40 },
      completion_tokens_details: { reasoning_tokens: 2 },
    });
    await instance.settled(response, { charge: 740 });
  });

  it("preserves SGLang nullable tool deltas and fragmented arguments", async () => {
    const instance = await makeCase("vllm");
    instance.runtimes[0]!.enqueue({
      fragment: 3,
      mutateEvents: (events) =>
        events.splice(
          0,
          events.length,
          ...sglangEvents(instance.runtimeModel, "weather"),
        ),
    });
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
      .flatMap((c) => c.choices)
      .flatMap((c) => c.delta.tool_calls ?? []);
    expect(calls[0]?.function?.name).toBe("weather");
    expect(
      JSON.parse(calls.map((c) => c.function?.arguments ?? "").join("")),
    ).toEqual({ city: "Paris" });
    await instance.settled(response, { charge: 780 });
  });

  it("retries a first-event SGLang queue rejection before exposing output", async () => {
    const instance = await makeCase("vllm", { replicas: 2 });
    const warm = await instance.post({ session_id: "sglang-queue" });
    await instance.settled(warm);
    const selected = instance.runtimes.find((r) => r.calls.length === 1)!;
    selected.enqueue({
      mutateEvents: (events) =>
        events.splice(0, events.length, sglangQueueError()),
    });
    const response = await instance.http.stream(instance.path, {
      headers: instance.headers,
      json: instance.body({ stream: true, session_id: "sglang-queue" }),
    });
    const frames = await response.dataFrames();
    expect(frames.at(-1)).toBe("[DONE]");
    expect(frames.join("")).not.toContain("PRIVATE_QUEUE_DETAIL");
    expect(instance.totalCalls()).toBe(3);
    await instance.settled(response);
  });

  it("returns public429 after primary and backup reject in their first SSE event", async () => {
    const instance = await makeCase("vllm", { replicas: 3 });
    for (const runtime of instance.runtimes) {
      runtime.enqueue({
        mutateEvents: (events) =>
          events.splice(0, events.length, sglangQueueError()),
      });
    }
    const response = await instance.post({ stream: true });
    expectRejected(response, { code: "capacity_exceeded" });
    expect(instance.runtimes.map((r) => r.calls.length).sort()).toEqual([
      0, 1, 1,
    ]);
    expect(response.text).not.toContain("PRIVATE_QUEUE_DETAIL");
    await instance.settled(response, { status: "failed", charge: 0 });
  });

  it("never replays after reasoning output followed by an SSE error", async () => {
    const instance = await makeCase("vllm", { replicas: 2 });
    for (const runtime of instance.runtimes) {
      runtime.enqueue({
        mutateEvents: (events) =>
          events.splice(
            0,
            events.length,
            ...sglangEvents(instance.runtimeModel).slice(0, 2),
            sglangQueueError(),
          ),
      });
    }
    const response = await instance.http.stream(instance.path, {
      headers: instance.headers,
      json: instance.body({ stream: true }),
    });
    const frames = await response.dataFrames();
    expect(frames).not.toContain("[DONE]");
    expect(object(JSON.parse(frames.at(-1)!)).error).toMatchObject({
      code: "runtime_unavailable",
    });
    expect(instance.totalCalls()).toBe(1);
    expect(frames.join("")).not.toContain("PRIVATE_QUEUE_DETAIL");
    await instance.settled(response, { status: "failed", charge: 720 });
  });
});

describe("external SGLang integration boundary", () => {
  it.each([
    "https://127.0.0.1:8000",
    "http://inference.example:8000",
    "http://127.0.0.1:8000/v1",
    "http://user:secret@127.0.0.1:8000",
  ])("refuses non-loopback origins and credentials in URL: %s", (url) => {
    expect(() =>
      externalSglang({
        GATEWAY_REAL_RUNTIME_URL_SGLANG: url,
        GATEWAY_REAL_SGLANG_MODEL: "test/model",
        GATEWAY_REAL_SGLANG_RUNTIME_REVISION: "runtime-source",
        GATEWAY_REAL_SGLANG_MODEL_REVISION: "checkpoint",
      }),
    ).toThrow();
  });

  it("requires explicit endpoint and model, without selecting a GPU or downloading weights", () => {
    expect(() => externalSglang({})).toThrow("requires");
    expect(
      externalSglang({
        GATEWAY_REAL_RUNTIME_URL_SGLANG: "http://127.0.0.1:28590/",
        GATEWAY_REAL_SGLANG_MODEL: "test/model",
        GATEWAY_REAL_SGLANG_RUNTIME_REVISION: "sglang-f171-smg-1.13",
        GATEWAY_REAL_SGLANG_MODEL_REVISION: "checkpoint-sha",
      }),
    ).toEqual({
      baseUrl: "http://127.0.0.1:28590",
      model: "test/model",
      runtimeRevision: "sglang-f171-smg-1.13",
      modelRevision: "checkpoint-sha",
    });
  });
});
