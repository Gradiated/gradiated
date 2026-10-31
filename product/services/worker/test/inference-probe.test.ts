import { randomUUID } from "node:crypto";
import { getEventListeners } from "node:events";
import { describe, expect, it, vi, afterEach } from "vitest";
import { Registry } from "prom-client";
import type { ModelReplica } from "@gradiated/control";
import { probeModel } from "../src/inference-probe.js";
import {
  InferenceProbeMetrics,
  runInferenceProbes,
} from "../src/inference-probes.js";

const deploymentId = randomUUID();
const options = {
  apiKey: "synthetic-key",
  baseURL: "https://gateway.test",
  modelId: "test/model",
  deploymentId,
  signal: new AbortController().signal,
};
const response = (body: unknown, acknowledged = deploymentId) =>
  Response.json(body, {
    headers: {
      "x-gradiated-verification-deployment": acknowledged,
      "x-gradiated-generation-id": randomUUID(),
    },
  });
const completion = {
  id: "completion",
  model: options.modelId,
  choices: [
    { finish_reason: "length", message: { role: "assistant", content: null } },
  ],
  usage: { completion_tokens: 8, prompt_tokens: 5, total_tokens: 13 },
};
const replica = {
  id: deploymentId,
  modelId: options.modelId,
  release: {},
} as ModelReplica;

afterEach(() => vi.useRealTimers());

describe("public inference probes", () => {
  it("makes one capped completion through the public API and accepts bounded reasoning output", async () => {
    const fetch = vi.fn(async (input: unknown) => {
      const request = input as Request;
      expect(request.url).toBe("https://gateway.test/v1/chat/completions");
      expect(request.headers.get("x-gradiated-verification-deployment")).toBe(
        deploymentId,
      );
      expect(await request.json()).toMatchObject({
        model: options.modelId,
        max_tokens: 8,
      });
      return response(completion);
    });
    await probeModel({ ...options, fetch });
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("checks System One with a tiny decision", async () => {
    await probeModel({
      ...options,
      protocol: "system_one",
      fetch: async () =>
        response({
          model: options.modelId,
          usage: { input_tokens: 10, output_tokens: 0 },
          answers: { category: { type: "choice", choice: "billing" } },
        }),
    });
  });

  it("rejects a response from a different deployment", async () => {
    await expect(
      probeModel({
        ...options,
        fetch: async () => response(completion, randomUUID()),
      }),
    ).rejects.toThrow();
  });

  it.each([undefined, "system_one"] as const)(
    "uses normal gateway routing for the %s model probe",
    async (protocol) => {
      const fetch = vi.fn(async (input: unknown) => {
        expect(
          (input as Request).headers.has("x-gradiated-verification-deployment"),
        ).toBe(false);
        return Response.json(
          protocol === "system_one"
            ? {
                model: options.modelId,
                usage: { input_tokens: 10, output_tokens: 0 },
                answers: { category: { type: "choice", choice: "billing" } },
              }
            : completion,
          { headers: { "x-gradiated-generation-id": randomUUID() } },
        );
      });
      const { deploymentId: _, ...routed } = options;
      await probeModel({ ...routed, protocol, fetch });
      expect(fetch).toHaveBeenCalledTimes(1);
    },
  );

  it("randomizes the opening message on every pass to vary content affinity", async () => {
    const prefixes: string[] = [];
    const { deploymentId: _, ...routed } = options;
    const fetch: typeof globalThis.fetch = async (input) => {
      const body = await (input as Request).json();
      prefixes.push(body.messages[0].content);
      return response(completion);
    };
    await probeModel({ ...routed, fetch });
    await probeModel({ ...routed, fetch });
    expect(prefixes[0]).toMatch(/^Probe [0-9a-f-]{36}\nHi$/);
    expect(prefixes[0]).not.toBe(prefixes[1]);
  });

  it("does not retry HTTP failures", async () => {
    const fetch = vi.fn(async () =>
      Response.json({ error: { message: "Failure" } }, { status: 503 }),
    );
    await expect(probeModel({ ...options, fetch })).rejects.toThrow();
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("propagates cancellation to the real HTTP request", async () => {
    const abort = new AbortController();
    abort.abort();
    await expect(
      probeModel({
        ...options,
        signal: abort.signal,
        fetch: async (input) => {
          (input as Request).signal.throwIfAborted();
          return response(completion);
        },
      }),
    ).rejects.toThrow();
  });

  it.each([undefined, "system_one"] as const)(
    "cancels an in-flight %s request through the SDK and releases the caller listener",
    async (protocol) => {
      const abort = new AbortController();
      const reason = new Error("synthetic shutdown");
      await expect(
        probeModel({
          ...options,
          protocol,
          signal: abort.signal,
          fetch: async (input) => {
            const signal = (input as Request).signal;
            abort.abort(reason);
            expect(signal.aborted).toBe(true);
            signal.throwIfAborted();
            return response(completion);
          },
        }),
      ).rejects.toThrow();
      expect(getEventListeners(abort.signal, "abort")).toHaveLength(0);
    },
  );

  it("cleans up a failed pass before releasing the lease", async () => {
    vi.useFakeTimers();
    const abort = new AbortController();
    const failure = new Error("synthetic lease failure");
    const evaluate = vi
      .fn()
      .mockRejectedValueOnce(failure)
      .mockResolvedValue(0);

    await expect(
      runInferenceProbes({
        eval: evaluate,
        replicas: async () => [],
        probe: async () => {},
        metrics: new InferenceProbeMetrics(new Registry()),
        signal: abort.signal,
        onReady: async () => {},
      }),
    ).rejects.toBe(failure);

    expect(evaluate.mock.calls.at(-1)?.[0]).toContain("DEL");
    expect(getEventListeners(abort.signal, "abort")).toHaveLength(0);
    expect(vi.getTimerCount()).toBe(0);
  });

  it.each([undefined, "system_one"] as const)(
    "keeps %s cancellation active while reading the response body",
    async (protocol) => {
      const abort = new AbortController();
      let notifyRead!: () => void;
      const reading = new Promise<void>((resolve) => {
        notifyRead = resolve;
      });
      const probing = probeModel({
        ...options,
        protocol,
        signal: abort.signal,
        fetch: async (input) => {
          const signal = (input as Request).signal;
          const body = new ReadableStream(
            {
              start: (controller) => {
                signal.addEventListener(
                  "abort",
                  () => controller.error(signal.reason),
                  { once: true },
                );
              },
              pull: () => notifyRead(),
            },
            { highWaterMark: 0 },
          );
          return new Response(body, {
            headers: {
              "content-type": "application/json",
              "x-gradiated-verification-deployment": deploymentId,
              "x-gradiated-generation-id": randomUUID(),
            },
          });
        },
      });
      const outcome = expect(probing).rejects.toThrow();
      await reading;
      abort.abort(new Error("synthetic body cancellation"));
      await outcome;

      expect(getEventListeners(abort.signal, "abort")).toHaveLength(0);
    },
  );

  it("probes every five seconds despite failures and cleans up the lease and retired metrics", async () => {
    vi.useFakeTimers();
    const registry = new Registry();
    const metrics = new InferenceProbeMetrics(registry);
    const abort = new AbortController();
    let targeted = 0;
    const probe = vi.fn(async (_replica, _signal, scope) => {
      if (scope === "deployment" && targeted++ === 0)
        throw new Error("synthetic failure");
    });
    const evaluate = vi.fn().mockResolvedValue(1);
    const run = runInferenceProbes({
      eval: evaluate,
      replicas: async () => [replica],
      probe,
      metrics,
      signal: abort.signal,
      onReady: async () => {},
    });
    await vi.advanceTimersByTimeAsync(10_001);
    expect(probe).toHaveBeenCalledTimes(6);
    const rendered = await registry.metrics();
    expect(rendered).toContain(
      'deployment="' + deploymentId + '",result="failure"} 1',
    );
    expect(rendered).toContain(
      'deployment="' + deploymentId + '",result="success"} 2',
    );
    abort.abort();
    await run;
    expect(evaluate.mock.calls.at(-1)?.[0]).toContain("DEL");
    expect(await registry.metrics()).not.toContain(
      'deployment="' + deploymentId + '"',
    );
  });

  it("finishes routed requests before targeting single-slot replicas", async () => {
    const abort = new AbortController();
    let started!: () => void;
    let release!: () => void;
    const routedStarted = new Promise<void>((resolve) => {
      started = resolve;
    });
    const routedComplete = new Promise<void>((resolve) => {
      release = resolve;
    });
    const targeted = vi.fn();
    const run = runInferenceProbes({
      eval: async () => 1,
      replicas: async () => [replica, { ...replica, id: randomUUID() }],
      probe: async (replica, _signal, scope) => {
        if (scope === "model") {
          started();
          await routedComplete;
        } else targeted(replica.id);
      },
      metrics: new InferenceProbeMetrics(new Registry()),
      signal: abort.signal,
      onReady: async () => abort.abort(),
    });
    await routedStarted;
    expect(targeted).not.toHaveBeenCalled();
    release();
    await run;
    expect(targeted).toHaveBeenCalledTimes(2);
  });

  it("gives targeted probes their full deadline after a slow routed phase", async () => {
    vi.useFakeTimers();
    const abort = new AbortController();
    const registry = new Registry();
    let rendered = "";
    const run = runInferenceProbes({
      eval: async () => 1,
      replicas: async () => [replica],
      probe: async (_replica, signal) => {
        await new Promise((resolve) => setTimeout(resolve, 3000));
        signal.throwIfAborted();
      },
      metrics: new InferenceProbeMetrics(registry),
      signal: abort.signal,
      onReady: async () => {
        rendered = await registry.metrics();
        abort.abort();
      },
    });
    await vi.advanceTimersByTimeAsync(6001);
    await run;
    expect(rendered).toContain(
      `deployment="${deploymentId}",result="success"} 1`,
    );
    expect(rendered).toContain(
      'gradiated_inference_routed_probe_requests_total{model="test/model",result="success"} 1',
    );
    expect(vi.getTimerCount()).toBe(0);
    expect(getEventListeners(abort.signal, "abort")).toHaveLength(0);
  });

  it("probes each replica and each distinct model, keeping their failures separate", async () => {
    const registry = new Registry();
    const metrics = new InferenceProbeMetrics(registry);
    const abort = new AbortController();
    const replicas = [
      replica,
      { ...replica, id: randomUUID() },
      {
        ...replica,
        id: randomUUID(),
        modelId: "other/model",
      },
    ];
    const probe = vi.fn(async (_replica, _signal, scope) => {
      if (scope === "deployment") throw new Error("synthetic busy replica");
    });
    let rendered = "";
    await runInferenceProbes({
      eval: async () => 1,
      replicas: async () => replicas,
      probe,
      metrics,
      signal: abort.signal,
      onReady: async () => {
        rendered = await registry.metrics();
        abort.abort();
      },
    });
    expect(
      probe.mock.calls.filter((call) => call[2] === "deployment"),
    ).toHaveLength(3);
    expect(probe.mock.calls.filter((call) => call[2] === "model")).toHaveLength(
      2,
    );
    expect(rendered).toContain(
      `deployment="${deploymentId}",result="failure"} 1`,
    );
    expect(rendered).toContain(
      'gradiated_inference_routed_probe_requests_total{model="test/model",result="success"} 1',
    );
    expect(await registry.metrics()).not.toContain('model="test/model"');
  });

  it("does not discover or probe after cancellation during lease acquisition", async () => {
    const abort = new AbortController();
    const replicas = vi.fn(async () => [replica]);
    const probe = vi.fn();
    await expect(
      runInferenceProbes({
        eval: async () => {
          abort.abort();
          return 1;
        },
        replicas,
        probe,
        metrics: new InferenceProbeMetrics(new Registry()),
        signal: abort.signal,
        onReady: async () => {},
      }),
    ).rejects.toThrow();
    expect(replicas).not.toHaveBeenCalled();
    expect(probe).not.toHaveBeenCalled();
  });

  it("standby workers do not issue requests or keep a fresh inventory", async () => {
    vi.useFakeTimers();
    const registry = new Registry();
    const abort = new AbortController();
    const replicas = vi.fn(async () => [replica]);
    const probe = vi.fn();
    const run = runInferenceProbes({
      eval: async () => 0,
      replicas,
      probe,
      metrics: new InferenceProbeMetrics(registry),
      signal: abort.signal,
      onReady: async () => {},
    });
    await vi.advanceTimersByTimeAsync(5_001);
    expect(replicas).not.toHaveBeenCalled();
    expect(probe).not.toHaveBeenCalled();
    expect(await registry.metrics()).toContain(
      "gradiated_inference_probe_inventory_timestamp_seconds 0",
    );
    expect(getEventListeners(abort.signal, "abort")).toHaveLength(1);
    expect(vi.getTimerCount()).toBe(1);
    abort.abort();
    await run;
    expect(getEventListeners(abort.signal, "abort")).toHaveLength(0);
    expect(vi.getTimerCount()).toBe(0);
  });
});
