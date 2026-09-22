import { describe, expect, it } from "vitest";

import type { Fault, RuntimeKind } from "./mock-runtimes/server.js";
import { useCases } from "./support.js";

const { makeCase } = useCases();

const callCounts = (runtimes: { calls: unknown[] }[]): number[] =>
  runtimes.map((runtime) => runtime.calls.length).sort((a, b) => a - b);

describe.each(["kev", "vllm"] as RuntimeKind[])("%s routing", (kind) => {
  it.each([
    { status: 400, unwrapped: 400 },
    { status: 401, unwrapped: 503 },
    { status: 429, unwrapped: 429 },
    { status: 500, unwrapped: 503 },
    { status: 503, unwrapped: 429 },
    { status: 307, unwrapped: 503 },
  ])(
    "sanitizes and settles a runtime $status",
    async ({ status, unwrapped }) => {
      const instance = await makeCase(kind);
      instance.runtimes[0]!.enqueue({ status });
      const response = await instance.post();
      expect(response.status).toBe(unwrapped);
      expect(response.text).not.toContain("PRIVATE_RUNTIME_DETAIL");
      await instance.settled(response, "failed", 0);
      expect(instance.runtimes[0]!.calls).toHaveLength(1);
    },
  );

  it.each(["invalid_json", "oversize", "disconnect"] as Fault[])(
    "releases admission after a %s transport fault",
    async (fault) => {
      const instance = await makeCase(kind);
      instance.runtimes[0]!.enqueue({ fault });
      const response = await instance.post();
      expect(response.status).toBe(503);
      await instance.settled(response, "failed", 0);
      // Recovery uses the same tenant and runtime.
      expect((await instance.post()).status).toBe(200);
    },
  );

  it.each([429, 503])(
    "bounds retries and moves to another replica after %s",
    async (status) => {
      const instance = await makeCase(kind, { replicas: 3 });
      for (const runtime of instance.runtimes) runtime.enqueue({ status });
      const response = await instance.post();
      // The runtime contract treats both 429 and 503 as capacity exhaustion.
      expect(response.status).toBe(429);
      expect(callCounts(instance.runtimes)).toEqual([0, 1, 1]);
      await instance.settled(response, "failed", 0);
    },
  );

  it("keeps session affinity and retries into success", async () => {
    const instance = await makeCase(kind, { replicas: 2 });
    const first = await instance.post({ session_id: "sticky" });
    expect(first.status).toBe(200);
    const selected = instance.runtimes.find(
      (runtime) => runtime.calls.length > 0,
    )!;
    expect((await instance.post({ session_id: "sticky" })).status).toBe(200);
    expect(selected.calls).toHaveLength(2);
    selected.enqueue({ status: 503 });
    const response = await instance.post({ session_id: "sticky" });
    expect(response.status).toBe(200);
    expect(callCounts(instance.runtimes)).toEqual([1, 3]);
    await instance.settled(response);
    // Two attempts, plus one terminal event for the last request.
    expect(await instance.settlements()).toHaveLength(3);
  });
});

it("keys Kev state affinity without the questions", async () => {
  const instance = await makeCase("kev", { replicas: 2 });
  expect((await instance.post()).status).toBe(200);
  const response = await instance.post({
    questions: { other: { type: "noul", instructions: "Different question" } },
  });
  expect(response.status).toBe(200);
  expect(callCounts(instance.runtimes)).toEqual([0, 2]);
});

it("does not retry a billed runtime failure", async () => {
  const instance = await makeCase("vllm", { replicas: 2 });
  for (const runtime of instance.runtimes) {
    runtime.enqueue({
      status: 500,
      errorUsage: {
        prompt_tokens: 100,
        completion_tokens: 3,
        total_tokens: 103,
      },
    });
  }
  const response = await instance.post();
  expect(response.status).toBe(503);
  await instance.settled(response, "failed", 1060);
  expect(
    instance.runtimes.reduce(
      (total, runtime) => total + runtime.calls.length,
      0,
    ),
  ).toBe(1);
});

it("cannot use a release mismatch for a retry", async () => {
  const instance = await makeCase("vllm", { replicas: 2 });
  instance.deployments[1]!.release = {
    ...instance.release,
    model_revision: "different-weights",
  };
  await instance.publish();
  instance.runtimes[0]!.enqueue({ status: 503 });
  const response = await instance.post();
  expect(response.status).toBe(429);
  expect(instance.runtimes[0]!.calls).toHaveLength(1);
  expect(instance.runtimes[1]!.calls).toEqual([]);
  await instance.settled(response, "failed", 0);
});
