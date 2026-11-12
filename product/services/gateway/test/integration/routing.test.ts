import { createHash } from "node:crypto";

import { describe, expect, it } from "vitest";

import { expectRejected, type Rejection } from "./assertions.js";
import { useCases } from "./case.js";
import { RUNTIME_KINDS, type Fault } from "./mock-runtimes/server.js";

const { makeCase } = useCases();

const callCounts = (runtimes: { calls: unknown[] }[]): number[] =>
  runtimes.map((runtime) => runtime.calls.length).sort((a, b) => a - b);

describe.each(RUNTIME_KINDS)("%s routing", (kind) => {
  it.each<{ status: number; rejection: Rejection }>([
    { status: 400, rejection: { code: "invalid_request" } },
    { status: 401, rejection: { code: "runtime_unavailable" } },
    { status: 429, rejection: { code: "capacity_exceeded" } },
    { status: 500, rejection: { code: "runtime_unavailable" } },
    { status: 503, rejection: { code: "capacity_exceeded" } },
    { status: 307, rejection: { code: "runtime_unavailable" } },
  ])(
    "sanitizes and settles a runtime $status",
    async ({ status, rejection }) => {
      const instance = await makeCase(kind);
      instance.runtimes[0]!.enqueue({ status });

      const response = await instance.post();

      expectRejected(response, rejection);
      expect(response.text).not.toContain("PRIVATE_RUNTIME_DETAIL");
      await instance.settled(response, { status: "failed", charge: 0 });
      expect(instance.runtimes[0]!.calls).toHaveLength(1);
    },
  );

  it.each<Fault>(["invalid_json", "oversize", "disconnect"])(
    "releases admission after a %s transport fault",
    async (fault) => {
      const instance = await makeCase(kind);
      instance.runtimes[0]!.enqueue({ fault });

      const response = await instance.post();

      expectRejected(response, { code: "runtime_unavailable" });
      await instance.settled(response, { status: "failed", charge: 0 });
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
      expectRejected(response, { code: "capacity_exceeded" });
      expect(callCounts(instance.runtimes)).toEqual([0, 1, 1]);
      await instance.settled(response, { status: "failed", charge: 0 });
    },
  );

  it("serves both runtime revisions throughout a sequential rollout", async () => {
    const instance = await makeCase(kind, { replicas: 2 });
    instance.deployments[1]!.release = {
      ...instance.release,
      runtime_revision: "next-runtime",
    };
    await instance.publish();
    await instance.status();

    for (let index = 0; index < 24; index += 1) {
      await instance.status();
      const before = instance.runtimes.map((runtime) => runtime.calls.length);
      const session = `rollout-${index}`;
      const first = await instance.post({ session_id: session });
      expect(first.status).toBe(200);
      const selected = instance.runtimes.findIndex(
        (runtime, index) => runtime.calls.length > before[index]!,
      );
      const releaseDigest = `sha256:${createHash("sha256").update(JSON.stringify(instance.deployments[selected]!.release)).digest("hex")}`;
      await instance.settled(first, { releaseDigest });
      const second = await instance.http.post(instance.path, {
        headers: { ...instance.headers, "x-gradiated-session-id": session },
        json: instance.body(),
      });
      expect(second.status).toBe(200);
      await instance.settled(second, { releaseDigest });
      expect(instance.runtimes[selected]!.calls).toHaveLength(
        before[selected]! + 2,
      );
    }
    expect(instance.runtimes.every((runtime) => runtime.calls.length > 0)).toBe(
      true,
    );
  });

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

  // Several sessions, so a header the gateway ignored could not pass by landing
  // on the prompt's own replica every time.
  it("gives the session header the same affinity as the session_id field", async () => {
    const instance = await makeCase(kind, { replicas: 2 });

    for (const session of ["a", "b", "c", "d", "e", "f"]) {
      const before = instance.runtimes.map((runtime) => runtime.calls.length);

      expect((await instance.post({ session_id: session })).status).toBe(200);
      const selected = instance.runtimes.findIndex(
        (runtime, index) => runtime.calls.length > before[index]!,
      );

      const response = await instance.http.post(instance.path, {
        headers: { ...instance.headers, "x-gradiated-session-id": session },
        json: instance.body(),
      });

      expect(response.status).toBe(200);
      expect(instance.runtimes[selected]!.calls).toHaveLength(
        before[selected]! + 2,
      );
    }
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

  expectRejected(response, { code: "runtime_unavailable" });
  await instance.settled(response, { status: "failed", charge: 1060 });
  expect(instance.totalCalls()).toBe(1);
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

  expectRejected(response, { code: "capacity_exceeded" });
  expect(instance.runtimes[0]!.calls).toHaveLength(1);
  expect(instance.runtimes[1]!.calls).toEqual([]);
  await instance.settled(response, { status: "failed", charge: 0 });
});

it("keeps identical sessionless LLM calls cache-local", async () => {
  const instance = await makeCase("vllm", { replicas: 8 });

  for (let index = 0; index < 8; index += 1) {
    expect((await instance.post()).status).toBe(200);
  }

  expect(
    instance.runtimes.filter((runtime) => runtime.calls.length > 0),
  ).toHaveLength(1);
});

it("spreads distinct sessionless conversation openings across the fleet", async () => {
  const instance = await makeCase("vllm", { replicas: 8 });
  for (let index = 0; index < 256; index++) {
    const response = await instance.post({
      messages: [
        { role: "system", content: "Common system instructions" },
        { role: "user", content: `Unique opening question ${index}` },
      ],
    });
    expect(response.status).toBe(200);
  }
  expect(instance.runtimes.every((runtime) => runtime.calls.length > 0)).toBe(
    true,
  );
});

// One large replica beside three small ones, each reporting its active request
// limit, the way a B300 serves beside an H200 pool.
describe("weighted routing by active request limit", () => {
  const sessions = 400;
  const large = (index: number) => (index === 0 ? 16 : 4);

  const firstChoiceShare = async (
    instance: Awaited<ReturnType<typeof makeCase>>,
    each: (index: number) => { active_requests?: number },
  ): Promise<number> => {
    for (let session = 0; session < sessions; session += 1) {
      // Statuses go stale after fifteen seconds; refresh them as Desmond would.
      if (session % 20 === 0) await instance.status({}, each);
      const response = await instance.post({
        session_id: `weighted-${session}`,
      });
      expect(response.status).toBe(200);
    }

    const calls = instance.runtimes.map((runtime) => runtime.calls.length);
    expect(calls.reduce((sum, count) => sum + count, 0)).toBe(sessions);
    expect(calls.every((count) => count > 0)).toBe(true);
    return calls[0]! / sessions;
  };

  // 16 / (16 + 4 + 4 + 4) = 0.571. With 400 sessions one standard deviation is
  // 0.025, so these bounds are about five deviations wide.
  it("sends replicas of one release a share proportional to their limits", async () => {
    const instance = await makeCase("vllm", { replicas: 4 });

    const share = await firstChoiceShare(instance, (index) => ({
      active_requests: large(index),
    }));

    expect(share).toBeGreaterThan(0.45);
    expect(share).toBeLessThan(0.7);
  });

  it("weights the choice between releases of the same model", async () => {
    const instance = await makeCase("vllm", { replicas: 4 });
    instance.deployments[0]!.release = {
      ...instance.release,
      runtime_revision: "large-runtime",
    };
    await instance.publish();

    const share = await firstChoiceShare(instance, (index) => ({
      active_requests: large(index),
    }));

    expect(share).toBeGreaterThan(0.45);
    expect(share).toBeLessThan(0.7);
  });

  // The silent replica keeps 1/4; the other three split 3/4 as 16:4:4, so the
  // large replica takes 1/2.
  it("keeps an equal share for a replica that leaves its limit out", async () => {
    const instance = await makeCase("vllm", { replicas: 4 });

    const share = await firstChoiceShare(instance, (index) =>
      index === 3 ? {} : { active_requests: large(index) },
    );

    expect(share).toBeGreaterThan(0.38);
    expect(share).toBeLessThan(0.62);
    const silent = instance.runtimes[3]!.calls.length / sessions;
    expect(silent).toBeGreaterThan(0.15);
    expect(silent).toBeLessThan(0.35);
  });

  it("ranks exactly as before when no replica reports a limit", async () => {
    const instance = await makeCase("vllm", { replicas: 4 });

    const share = await firstChoiceShare(instance, () => ({}));

    expect(share).toBeGreaterThan(0.15);
    expect(share).toBeLessThan(0.35);
  });
});
