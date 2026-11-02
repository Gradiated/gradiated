import { readFile } from "node:fs/promises";

import { describe, expect, inject, it } from "vitest";

import { expectRejected } from "./assertions.js";
import { useCases, type Case } from "./case.js";
import { chatChunks } from "./chat.js";
import { eventually } from "./eventually.js";
import { Response } from "./http-client.js";
import { checkQualificationIsolation } from "./qualification-isolation.js";
import { matchesWholeAnswer } from "./whole-answer.js";
import { smgAdmissionSample } from "./smg-admission.js";
import {
  object,
  toJsonObject,
  type JsonObject,
  type JsonValue,
} from "./json.js";

const runtime = inject("realRuntimes").sglang;
const { makeCase } = useCases();
const LIMIT = 120_000;
const longFixture = process.env.GATEWAY_REAL_SGLANG_LONG_FIXTURE;
const cancelFixture = process.env.GATEWAY_REAL_SGLANG_CANCEL_FIXTURE;
const metricsUrl = process.env.GATEWAY_REAL_SGLANG_METRICS_URL;
const count = (value: JsonValue | undefined): number => {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) {
    throw new Error("runtime did not supply a valid token count");
  }

  return value;
};

const realCase = async (replicas = 1): Promise<Case> => {
  const instance = await makeCase("vllm", {
    replicas,
    upstream: { kind: "proxy", ...runtime! },
    runtimeRevision: runtime!.runtimeRevision!,
    modelRevision: runtime!.modelRevision!,
  });
  const inputs = instance.record.properties.input_modalities;
  const outputs = instance.record.properties.output_modalities;
  if (!Array.isArray(inputs) || !Array.isArray(outputs))
    throw new Error("missing modalities");
  object(object(inputs[0]).supported_inputs).max_prompt_length = {
    value: 16384,
    unit: "token",
  };
  object(object(inputs[0]).supported_inputs).max_context_length = {
    value: 32768,
    unit: "token",
  };
  object(outputs[0]).max_length = { value: 2048, unit: "token" };
  await instance.publish();
  await instance.status();
  await instance.ready();

  return instance;
};

const settleUsage = async (
  instance: Case,
  response: { headers: Record<string, string> },
  usage: JsonObject,
): Promise<void> => {
  const prompt = count(usage.prompt_tokens);
  const output = count(usage.completion_tokens);
  const cached = count(object(usage.prompt_tokens_details).cached_tokens);
  expect(prompt).toBeGreaterThan(0);
  expect(output).toBeGreaterThan(0);
  expect(cached).toBeLessThanOrEqual(prompt);
  expect(usage.total_tokens).toBe(prompt + output);
  const properties = await instance.settled(response, {
    charge: (prompt - cached) * 10 + cached * 2 + output * 20,
  });
  expect(properties.usage).toMatchObject({
    input_tokens: prompt,
    output_tokens: output,
  });
};

const coldFixture = async (
  path: string,
): Promise<{ messages: JsonObject[]; marker: string }> => {
  const fixture = object(JSON.parse(await readFile(path, "utf8")));
  if (
    !Array.isArray(fixture.messages) ||
    fixture.messages.length !== 1 ||
    typeof fixture.marker !== "string"
  ) {
    throw new Error("expected one public synthetic user message and a marker");
  }
  const message = object(fixture.messages[0]);
  if (message.role !== "user" || typeof message.content !== "string") {
    throw new Error("expected a synthetic text user message");
  }

  return {
    messages: [
      {
        role: "user",
        content: `Cold gateway fixture ${crypto.randomUUID()}.\n${message.content}`,
      },
    ],
    marker: fixture.marker,
  };
};

const allowLongContext = async (instance: Case): Promise<void> => {
  const inputs = instance.record.properties.input_modalities;
  if (!Array.isArray(inputs)) throw new Error("missing input modality");
  const supported = object(object(inputs[0]).supported_inputs);
  supported.max_prompt_length = { value: 1048320, unit: "token" };
  supported.max_context_length = { value: 1048576, unit: "token" };
  await instance.publish();
  await instance.status();
  await instance.ready((entry) => {
    const modalities = entry.input_modalities;
    if (!Array.isArray(modalities)) return false;
    const context = object(
      object(modalities[0]).supported_inputs,
    ).max_context_length;
    return object(context).value === 1048576;
  });
};

const runningRequests = async (): Promise<number> => {
  const url = new URL(metricsUrl!);
  if (
    url.protocol !== "http:" ||
    !["127.0.0.1", "localhost", "[::1]"].includes(url.hostname) ||
    url.username ||
    url.password
  ) {
    throw new Error("runtime metrics must use a loopback HTTP forward");
  }
  const response = await fetch(url, { signal: AbortSignal.timeout(3000) });
  if (!response.ok)
    throw new Error(`runtime metrics returned HTTP ${response.status}`);
  const metrics = await response.text();
  const values = [
    ...metrics.matchAll(
      /^sglang:num_running_reqs(?:\{[^\n]*\})?\s+([-+0-9.eE]+)(?:\s+\d+)?$/gm,
    ),
  ].map((m) => Number(m[1]));
  if (values.length === 0 || values.some((v) => !Number.isFinite(v) || v < 0)) {
    throw new Error(
      "native active request gauge unavailable; absence is not zero",
    );
  }

  return values.reduce((sum, value) => sum + value, 0);
};

describe.skipIf(!runtime)(
  "real SGLang via local gateway and disposable billing",
  () => {
    it(
      "routes only restricted verification traffic to an isolated qualified SGLang deployment",
      async () => {
        const instance = await realCase(2);
        const outsider = await makeCase("vllm");
        await checkQualificationIsolation(
          instance,
          outsider,
          instance.body({
            temperature: 0,
            max_tokens: 512,
            messages: [
              {
                role: "user",
                content: "What is 13 times 17? Answer only the number.",
              },
            ],
          }),
          async (response) => {
            const body = response.json();
            const choices = body.choices;
            if (!Array.isArray(choices)) throw new Error("missing choices");
            const visible = object(object(choices[0]).message).content;
            if (typeof visible !== "string")
              throw new Error("missing visible answer");
            expect(matchesWholeAnswer(visible, "221")).toBe(true);
            await settleUsage(instance, response, object(body.usage));
          },
        );
      },
      LIMIT,
    );

    it.skipIf(!longFixture)(
      "keeps cold large prefill alive through public headers and SSE comments",
      async () => {
        const instance = await realCase();
        await allowLongContext(instance);
        const fixture = await coldFixture(longFixture!);
        const before = performance.now();
        const response = await instance.http.stream(instance.path, {
          headers: instance.headers,
          json: instance.body({
            stream: true,
            max_tokens: 256,
            temperature: 0,
            messages: fixture.messages,
          }),
          timeoutMs: LIMIT,
        });
        const headersAt = performance.now();
        expect(response.status).toBe(200);
        expect(headersAt - before).toBeLessThan(5000);
        let firstOutputAt: number | undefined;
        let keepaliveBeforeOutput = false;
        const frames: string[] = [];
        for await (const line of response.lines()) {
          if (line.startsWith(":")) {
            if (firstOutputAt === undefined) keepaliveBeforeOutput = true;
            continue;
          }
          if (!line.startsWith("data:")) continue;
          const frame = line.slice(5).trim();
          frames.push(frame);
          if (frame === "[DONE]") continue;
          const chunks = chatChunks([frame]);
          if (
            chunks.some((c) =>
              c.choices.some((choice) => {
                const delta = toJsonObject(choice.delta);
                return [
                  delta.content,
                  delta.reasoning_content,
                  delta.reasoning,
                ].some((v) => typeof v === "string" && v.length > 0);
              }),
            )
          )
            firstOutputAt ??= performance.now();
        }
        expect(frames.at(-1)).toBe("[DONE]");
        expect(firstOutputAt).toBeDefined();
        if (firstOutputAt! - headersAt > 16_000)
          expect(keepaliveBeforeOutput).toBe(true);
        const chunks = chatChunks(frames);
        const visible = chunks
          .flatMap((c) => c.choices)
          .map((c) => c.delta.content ?? "")
          .join("")
          .trim();
        expect(
          matchesWholeAnswer(visible, fixture.marker),
          JSON.stringify({
            visible,
            usage: chunks.at(-1)!.usage,
            finishReasons: chunks.flatMap((chunk) =>
              chunk.choices.map((choice) => choice.finish_reason),
            ),
          }),
        ).toBe(true);
        const usage = toJsonObject(chunks.at(-1)!.usage!);
        expect(count(usage.prompt_tokens)).toBeGreaterThan(400_000);
        expect(count(object(usage.prompt_tokens_details).cached_tokens)).toBe(
          0,
        );
        console.info("SGLang cold prefill", {
          publicHeadersMs: headersAt - before,
          firstGeneratedOutputMs: firstOutputAt! - before,
          keepaliveBeforeOutput,
          promptTokens: usage.prompt_tokens,
          cachedTokens: object(usage.prompt_tokens_details).cached_tokens,
        });
        await settleUsage(instance, response, usage);
      },
      LIMIT,
    );

    it.skipIf(!cancelFixture)(
      "cancels cold prefill while upstream HTTP headers are pending",
      async () => {
        const instance = await realCase();
        await allowLongContext(instance);
        const fixture = await coldFixture(cancelFixture!);
        const response = await instance.http.stream(instance.path, {
          headers: instance.headers,
          json: instance.body({
            stream: true,
            max_tokens: 2048,
            temperature: 0,
            messages: fixture.messages,
          }),
          timeoutMs: LIMIT,
        });
        expect(response.status).toBe(200);
        expect(instance.runtimes[0]!.upstreamResponses).toBe(0);
        response.message.destroy();
        await instance.settled(response, { status: "cancelled" });
        await eventually(
          async () => instance.runtimes[0]!.upstreamCancelled > 0,
          5000,
          "pending upstream request did not cancel",
        );
        if (metricsUrl) {
          await eventually(
            async () => (await runningRequests()) === 0,
            10_000,
            "native engine remained active after cancellation",
          );
        }
      },
      LIMIT,
    );

    it.skipIf(!longFixture)(
      "serves a short request arriving during cold large prefill",
      async () => {
        const instance = await realCase();
        await allowLongContext(instance);
        const fixture = await coldFixture(longFixture!);
        const started = performance.now();
        const observe = async (label: string, messages: JsonObject[]) => {
          const sentAt = performance.now();
          const response = await instance.http.stream(instance.path, {
            headers: instance.headers,
            json: instance.body({
              stream: true,
              max_tokens: 256,
              temperature: 0,
              messages,
            }),
            timeoutMs: LIMIT,
          });
          const headersMs = performance.now() - sentAt;
          expect(response.status).toBe(200);
          expect(headersMs).toBeLessThan(5000);
          let firstGeneratedMs: number | undefined;
          let firstVisibleMs: number | undefined;
          const frames: string[] = [];
          for await (const line of response.lines()) {
            if (!line.startsWith("data:")) continue;
            const frame = line.slice(5).trim();
            frames.push(frame);
            if (frame === "[DONE]") continue;
            for (const chunk of chatChunks([frame]))
              for (const choice of chunk.choices) {
                const delta = toJsonObject(choice.delta);
                if (
                  [
                    delta.content,
                    delta.reasoning_content,
                    delta.reasoning,
                  ].some((v) => typeof v === "string" && v.length > 0)
                )
                  firstGeneratedMs ??= performance.now() - sentAt;
                if (
                  typeof delta.content === "string" &&
                  delta.content.length > 0
                )
                  firstVisibleMs ??= performance.now() - sentAt;
              }
          }
          expect(frames.at(-1)).toBe("[DONE]");
          const chunks = chatChunks(frames);
          const usage = toJsonObject(chunks.at(-1)!.usage!);
          const visible = chunks
            .flatMap((c) => c.choices)
            .map((c) => c.delta.content ?? "")
            .join("")
            .trim();
          await settleUsage(instance, response, usage);
          console.info("SGLang gateway mixed prefill", {
            label,
            arrivalOffsetMs: sentAt - started,
            headersMs,
            firstGeneratedMs,
            firstVisibleMs,
            elapsedMs: performance.now() - sentAt,
            promptTokens: usage.prompt_tokens,
            outputTokens: usage.completion_tokens,
            cachedTokens: object(usage.prompt_tokens_details).cached_tokens,
          });

          return { usage, visible };
        };
        const long = observe("cold-long", fixture.messages);
        await new Promise((resolve) =>
          setTimeout(
            resolve,
            Math.max(0, 2000 - (performance.now() - started)),
          ),
        );
        const short = observe("new-short", [
          {
            role: "user",
            content: `Fresh arithmetic ${crypto.randomUUID()}. Compute 13 multiplied by 17. Return only the decimal integer.`,
          },
        ]);
        const outcomes = await Promise.allSettled([long, short]);
        expect(
          outcomes
            .filter((r) => r.status === "rejected")
            .map((r) => String(r.reason)),
        ).toEqual([]);
        const [large, small] = outcomes.map((r) => {
          if (r.status !== "fulfilled") throw r.reason;

          return r.value;
        });
        expect(count(large!.usage.prompt_tokens)).toBeGreaterThan(400_000);
        expect(
          count(object(large!.usage.prompt_tokens_details).cached_tokens),
        ).toBe(0);
        expect(matchesWholeAnswer(large!.visible, fixture.marker)).toBe(true);
        expect(matchesWholeAnswer(small!.visible, "221")).toBe(true);
        expect(instance.runtimes[0]!.calls).toHaveLength(2);
      },
      150_000,
    );

    it(
      "accepts buffered chat, runtime revision and authoritative usage",
      async () => {
        const instance = await realCase();
        const response = await instance.post({
          messages: [{ role: "user", content: "Return only the word READY." }],
          max_tokens: 256,
          temperature: 0,
        });
        expect(response.status, response.text).toBe(200);
        const body = response.json();
        expect(body.model).toBe(instance.model);
        expect(body.object).toBe("chat.completion");
        await settleUsage(instance, response, object(body.usage));
        const forwarded = instance.runtimes[0]!.calls[0]!;
        expect(forwarded.model).toBe(runtime!.model);
        expect(forwarded).not.toHaveProperty("session_id");
        expect(forwarded).not.toHaveProperty("service_tier");
        expect(instance.release).toMatchObject({
          runtime_revision: runtime!.runtimeRevision,
          model_revision: runtime!.modelRevision,
          tokenizer_revision: runtime!.modelRevision,
        });
      },
      LIMIT,
    );

    it(
      "streams separated reasoning, visible output and terminal usage",
      async () => {
        const instance = await realCase();
        const response = await instance.http.stream(instance.path, {
          headers: instance.headers,
          json: instance.body({
            stream: true,
            temperature: 0,
            max_tokens: 512,
            messages: [
              {
                role: "user",
                content:
                  "Work through 37 multiplied by 41 carefully, then give the numeric answer.",
              },
            ],
          }),
          timeoutMs: LIMIT,
        });
        expect(response.status).toBe(200);
        const frames = await response.dataFrames();
        expect(frames.at(-1)).toBe("[DONE]");
        const chunks = chatChunks(frames);
        expect(chunks.every((c) => c.model === instance.model)).toBe(true);
        const deltas = chunks
          .flatMap((c) => c.choices)
          .map((c) => toJsonObject(c.delta));
        expect(
          deltas.map((d) => d.reasoning_content ?? d.reasoning ?? "").join("")
            .length,
        ).toBeGreaterThan(0);
        expect(deltas.map((d) => d.content ?? "").join("")).toMatch(
          /\b1,?517\b/,
        );
        expect(instance.runtimes[0]!.calls[0]!.stream_options).toEqual({
          include_usage: true,
          continuous_usage_stats: true,
        });
        await settleUsage(
          instance,
          response,
          toJsonObject(chunks.at(-1)!.usage!),
        );
      },
      LIMIT,
    );

    it(
      "streams a named tool call without losing argument fragments",
      async () => {
        const instance = await realCase();
        const response = await instance.http.stream(instance.path, {
          headers: instance.headers,
          json: instance.body({
            stream: true,
            temperature: 0,
            max_tokens: 1024,
            messages: [
              { role: "user", content: "Call get_weather for Paris." },
            ],
            tools: [
              {
                type: "function",
                function: {
                  name: "get_weather",
                  description: "Look up weather for a city.",
                  parameters: {
                    type: "object",
                    properties: { city: { type: "string" } },
                    required: ["city"],
                    additionalProperties: false,
                  },
                },
              },
            ],
            tool_choice: {
              type: "function",
              function: { name: "get_weather" },
            },
          }),
          timeoutMs: LIMIT,
        });
        expect(response.status).toBe(200);
        const frames = await response.dataFrames();
        expect(frames.at(-1)).toBe("[DONE]");
        const chunks = chatChunks(frames);
        const calls = chunks
          .flatMap((c) => c.choices)
          .flatMap((c) => c.delta.tool_calls ?? []);
        expect(calls.find((c) => c.function?.name)?.function?.name).toBe(
          "get_weather",
        );
        expect(
          JSON.parse(calls.map((c) => c.function?.arguments ?? "").join("")),
        ).toEqual({ city: "Paris" });
        expect(
          chunks.some((c) =>
            c.choices.some((choice) => choice.finish_reason === "tool_calls"),
          ),
        ).toBe(true);
        await settleUsage(
          instance,
          response,
          toJsonObject(chunks.at(-1)!.usage!),
        );
      },
      LIMIT,
    );

    it(
      "reuses a prefix larger than1024tokens and prices actual cache hits",
      async () => {
        const instance = await realCase();
        const content = `Synthetic cache case ${crypto.randomUUID()}.\n${"Public synthetic log: service alpha accepted a request and returned status ok.\n".repeat(128)}\nReturn only READY.`;
        const request = {
          messages: [{ role: "user", content }],
          max_tokens: 64,
          temperature: 0,
        };
        const first = await instance.post(request);
        expect(first.status, first.text).toBe(200);
        const initial = object(first.json().usage);
        expect(count(initial.prompt_tokens)).toBeGreaterThan(1024);
        await settleUsage(instance, first, initial);
        const second = await instance.post(request);
        expect(second.status, second.text).toBe(200);
        const reused = object(second.json().usage);
        expect(reused.prompt_tokens).toBe(initial.prompt_tokens);
        expect(
          count(object(reused.prompt_tokens_details).cached_tokens),
        ).toBeGreaterThan(0);
        await settleUsage(instance, second, reused);
      },
      LIMIT,
    );

    it(
      "propagates client cancellation to the real upstream connection",
      async () => {
        const instance = await realCase();
        const response = await instance.http.stream(instance.path, {
          headers: instance.headers,
          json: instance.body({
            stream: true,
            max_tokens: 256,
            messages: [
              {
                role: "user",
                content:
                  "Write a detailed explanation of distributed inference scheduling.",
              },
            ],
          }),
          timeoutMs: LIMIT,
        });
        expect(response.status).toBe(200);
        for await (const line of response.lines()) {
          if (line.startsWith("data:")) break;
        }
        await instance.settled(response, { status: "cancelled" });
        await eventually(
          async () => instance.runtimes[0]!.upstreamCancelled > 0,
          5000,
          "gateway cancellation did not abort the runtime connection",
        );
      },
      LIMIT,
    );

    it.skipIf(process.env.GATEWAY_REAL_SGLANG_OVERLOAD !== "1")(
      "exercises native SMG admission with 19 gateway streams across ten organizations",
      async () => {
        const metrics = process.env.GATEWAY_REAL_SMG_METRICS_URL;
        if (metrics) {
          const url = new URL(metrics);
          if (
            url.protocol !== "http:" ||
            !["127.0.0.1", "localhost", "[::1]"].includes(url.hostname) ||
            url.username ||
            url.password
          ) {
            throw new Error("SMG metrics must use a loopback HTTP forward");
          }
        }
        const instances: Case[] = [];
        for (let index = 0; index < 10; index += 1)
          instances.push(await realCase());
        expect(
          new Set(instances.map((instance) => instance.organization)).size,
        ).toBe(10);
        await Promise.all(instances.map((instance) => instance.status()));
        await Promise.all(instances.map((instance) => instance.ready()));
        const samples: { inflight: number; queued: number | null }[] = [];
        const metricErrors: string[] = [];
        let monitoring = true;
        const monitor = metrics
          ? (async () => {
              while (monitoring) {
                try {
                  const response = await fetch(metrics, {
                    signal: AbortSignal.timeout(2000),
                  });
                  if (!response.ok)
                    throw new Error(`SMG metrics HTTP ${response.status}`);
                  samples.push(smgAdmissionSample(await response.text()));
                } catch (error) {
                  metricErrors.push(
                    error instanceof Error ? error.message : String(error),
                  );
                }
                if (monitoring)
                  await new Promise((resolve) => setTimeout(resolve, 50));
              }
            })()
          : Promise.resolve();
        const statuses: Record<string, number> = {};
        const started = performance.now();
        let outcomes: PromiseSettledResult<{
          status: number;
          promptTokens: number;
          outputTokens: number;
        }>[];
        try {
          outcomes = await Promise.allSettled(
            Array.from({ length: 19 }, async (_, index) => {
              const instance = instances[Math.floor(index / 2)]!;
              const content = `Public synthetic overload ${crypto.randomUUID()} request ${index}.\n${"Public log: service alpha processed 128 requests and returned status ok.\n".repeat(384)}\nWrite a complete Python log-analysis package with typed functions, CLI, error handling and extensive tests. Include full implementation and documentation exceeding 2000 words.`;
              const response = await instance.http.stream(instance.path, {
                headers: instance.headers,
                json: instance.body({
                  stream: true,
                  max_tokens: 256,
                  temperature: 0,
                  messages: [{ role: "user", content }],
                }),
                timeoutMs: 150_000,
              });
              statuses[String(response.status)] =
                (statuses[String(response.status)] ?? 0) + 1;
              if (response.status === 429) {
                let body = "";
                response.message.setEncoding("utf8");
                for await (const part of response.message) body += String(part);
                const rejected = new Response(
                  response.status,
                  response.headers,
                  body,
                );
                expectRejected(rejected, { code: "capacity_exceeded" });
                await instance.settled(rejected, {
                  status: "failed",
                  charge: 0,
                });

                return { status: 429, promptTokens: 0, outputTokens: 0 };
              }
              expect(
                response.status,
                "SMG overload must not become an HTTP 5xx",
              ).toBe(200);
              const frames = await response.dataFrames();
              expect(
                frames.at(-1),
                "accepted streams must finish without runtime_unavailable",
              ).toBe("[DONE]");
              const chunks = chatChunks(frames);
              const usage = toJsonObject(chunks.at(-1)!.usage!);
              expect(count(usage.prompt_tokens)).toBeGreaterThan(2500);
              expect(count(usage.prompt_tokens)).toBeLessThanOrEqual(16384);
              expect(
                count(object(usage.prompt_tokens_details).cached_tokens),
              ).toBe(0);
              await settleUsage(instance, response, usage);

              return {
                status: 200,
                promptTokens: count(usage.prompt_tokens),
                outputTokens: count(usage.completion_tokens),
              };
            }),
          );
        } finally {
          monitoring = false;
          await monitor;
        }
        const queueSamples = samples.filter(
          (s): s is { inflight: number; queued: number } => s.queued !== null,
        );
        const peakInflight = samples.length
          ? Math.max(...samples.map((s) => s.inflight))
          : null;
        const peakQueued = queueSamples.length
          ? Math.max(...queueSamples.map((s) => s.queued))
          : null;
        const simultaneousPeak = queueSamples.length
          ? Math.max(...queueSamples.map((s) => s.inflight + s.queued))
          : null;
        console.info("SGLang/SMG gateway overload", {
          requests: 19,
          organizations: 10,
          statuses,
          allJoined: outcomes.length === 19,
          elapsedMs: performance.now() - started,
          metricSamples: samples.length,
          queueMetricSamples: queueSamples.length,
          queueMetricCoverage: queueSamples.length
            ? "OBSERVED"
            : "UNKNOWN_not_emitted",
          metricErrors,
          peakInflight,
          peakQueued,
          simultaneousPeak,
          saturationObserved: simultaneousPeak === 18,
          public429Observed: (statuses["429"] ?? 0) > 0,
        });
        expect(outcomes).toHaveLength(19);
        expect(
          outcomes
            .filter((outcome) => outcome.status === "rejected")
            .map((outcome) => String(outcome.reason)),
        ).toEqual([]);
        expect(
          Object.keys(statuses).every(
            (status) => status === "200" || status === "429",
          ),
        ).toBe(true);
        if (metrics) {
          expect(
            samples.length,
            "missing metrics are not zero load",
          ).toBeGreaterThan(0);
          expect(peakInflight).toBeLessThanOrEqual(16);
          if (queueSamples.length) expect(peakQueued).toBeLessThanOrEqual(2);
          if ((statuses["429"] ?? 0) > 0)
            expect(
              queueSamples.length,
              "a real queue rejection requires native queue telemetry",
            ).toBeGreaterThan(0);
          if (simultaneousPeak === 18)
            expect(statuses["429"] ?? 0).toBeGreaterThanOrEqual(1);
        }
        expect(
          instances.map((instance) => instance.runtimes[0]!.calls.length),
        ).toEqual([2, 2, 2, 2, 2, 2, 2, 2, 2, 1]);
      },
      180_000,
    );

    it(
      "fails over from a scripted primary rejection to the resident SGLang backup",
      async () => {
        const instance = await realCase(2);
        const session = `resident-fallback-${crypto.randomUUID()}`;
        const messages = [
          {
            role: "user",
            content:
              "Compute 13 multiplied by 17. Return only the decimal integer.",
          },
        ];
        const warm = await instance.post({
          session_id: session,
          messages,
          max_tokens: 64,
          temperature: 0,
        });
        expect(warm.status, warm.text).toBe(200);
        await settleUsage(instance, warm, object(warm.json().usage));
        const primaryIndex = instance.runtimes.findIndex(
          (proxy) => proxy.calls.length === 1,
        );
        expect(primaryIndex).toBeGreaterThanOrEqual(0);
        const backupIndex = 1 - primaryIndex;
        const primary = instance.runtimes[primaryIndex]!;
        const backup = instance.runtimes[backupIndex]!;
        const before = instance.runtimes.map((proxy) => ({
          calls: proxy.calls.length,
          upstreamResponses: proxy.upstreamResponses,
        }));
        const order: string[] = [];
        const rejected = primary.enqueue({ status: 503 });
        const served = backup.enqueue();
        void rejected.entered.promise.then(() => order.push("primary"));
        void served.entered.promise.then(() => order.push("backup"));
        const response = await instance.http.stream(instance.path, {
          headers: instance.headers,
          json: instance.body({
            stream: true,
            session_id: session,
            messages,
            max_tokens: 256,
            temperature: 0,
          }),
          timeoutMs: LIMIT,
        });
        expect(response.status).toBe(200);
        const frames = await response.dataFrames();
        expect(frames.at(-1)).toBe("[DONE]");
        expect(frames.join("")).not.toContain("PRIVATE_RUNTIME_DETAIL");
        const chunks = chatChunks(frames);
        expect(chunks.every((chunk) => chunk.model === instance.model)).toBe(
          true,
        );
        const visible = chunks
          .flatMap((chunk) => chunk.choices)
          .map((choice) => choice.delta.content ?? "")
          .join("")
          .trim();
        expect(matchesWholeAnswer(visible, "221")).toBe(true);
        expect(order).toEqual(["primary", "backup"]);
        expect(primary.calls.length - before[primaryIndex]!.calls).toBe(1);
        expect(backup.calls.length - before[backupIndex]!.calls).toBe(1);
        expect(
          primary.upstreamResponses - before[primaryIndex]!.upstreamResponses,
        ).toBe(0);
        expect(
          backup.upstreamResponses - before[backupIndex]!.upstreamResponses,
        ).toBe(1);
        await settleUsage(
          instance,
          response,
          toJsonObject(chunks.at(-1)!.usage!),
        );
        expect(await instance.settlements()).toHaveLength(2);
      },
      LIMIT,
    );

    it(
      "bounds primary and backup admission rejection without GPU overload",
      async () => {
        const instance = await makeCase("vllm", {
          replicas: 3,
          upstream: { kind: "proxy", ...runtime! },
          runtimeRevision: runtime!.runtimeRevision!,
          modelRevision: runtime!.modelRevision!,
        });
        for (const proxy of instance.runtimes) proxy.enqueue({ status: 429 });
        await instance.ready();
        const response = await instance.post();
        expectRejected(response, { code: "capacity_exceeded" });
        expect(instance.runtimes.map((r) => r.calls.length).sort()).toEqual([
          0, 1, 1,
        ]);
        await instance.settled(response, { status: "failed", charge: 0 });
      },
      LIMIT,
    );
  },
);
