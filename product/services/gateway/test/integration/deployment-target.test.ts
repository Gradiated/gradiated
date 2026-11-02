import { expect, it } from "vitest";

import { expectRejected } from "./assertions.js";
import { useCases } from "./case.js";

const { makeCase } = useCases();
const header = "x-gradiated-deployment-id";

it("targets an unavailable replica with an ordinary workspace key without publishing it", async () => {
  const instance = await makeCase("vllm", { replicas: 2 });
  const target = instance.deployments[1]!;
  target.status = "unavailable";
  await instance.publish();
  await instance.status();
  const ordinary = await instance.post();
  expect(ordinary.status, ordinary.text).toBe(200);
  expect(ordinary.headers[header]).toBeUndefined();
  await instance.settled(ordinary, { charge: 1060 });
  const pinned = await instance.http.post(instance.path, {
    headers: { ...instance.headers, [header]: target.id },
    json: instance.body(),
  });
  expect(pinned.status, pinned.text).toBe(200);
  expect(pinned.headers[header]).toBe(target.id);
  await instance.settled(pinned, { charge: 1060 });
  const stream = await instance.http.stream(instance.path, {
    headers: { ...instance.headers, [header]: target.id },
    json: instance.body({ stream: true }),
  });
  expect(stream.status).toBe(200);
  expect(stream.headers[header]).toBe(target.id);
  expect((await stream.dataFrames()).at(-1)).toBe("[DONE]");
  await instance.settled(stream, { charge: 1060 });
  const after = await instance.post();
  expect(after.status, after.text).toBe(200);
  await instance.settled(after, { charge: 1060 });
  expect(instance.runtimes.map((runtime) => runtime.calls.length)).toEqual([
    2, 2,
  ]);
});

it("does not fall back when the explicitly selected replica rejects admission", async () => {
  const instance = await makeCase("vllm", { replicas: 2 });
  const target = instance.deployments[1]!;
  instance.runtimes[1]!.enqueue({ status: 503 });
  const response = await instance.http.post(instance.path, {
    headers: { ...instance.headers, [header]: target.id },
    json: instance.body(),
  });
  expectRejected(response, { code: "capacity_exceeded" });
  await instance.settled(response, { status: "failed", charge: 0 });
  expect(instance.runtimes.map((runtime) => runtime.calls.length)).toEqual([
    0, 1,
  ]);
});

it("keeps normal billing admission when selecting a replica", async () => {
  const instance = await makeCase("vllm");
  await instance.setTenant({ balance: 0 });
  const response = await instance.http.post(instance.path, {
    headers: { ...instance.headers, [header]: instance.deployments[0]!.id },
    json: instance.body(),
  });
  expectRejected(response, { code: "insufficient_balance" });
  await instance.expectNotDispatched();
});

it.each(["invalid", "00000000-0000-0000-0000-000000000000"])(
  "rejects a malformed or unknown deployment target %s without dispatch",
  async (id) => {
    const instance = await makeCase("vllm");
    const response = await instance.http.post(instance.path, {
      headers: { ...instance.headers, [header]: id },
      json: instance.body(),
    });
    expect(response.status).toBe(id === "invalid" ? 400 : 404);
    await instance.expectNotDispatched();
  },
);

it("cannot select a deployment belonging to another model", async () => {
  const instance = await makeCase("vllm");
  const other = await makeCase("vllm");
  const response = await instance.http.post(instance.path, {
    headers: { ...instance.headers, [header]: other.deployments[0]!.id },
    json: instance.body(),
  });
  expect(response.status).toBe(404);
  await instance.expectNotDispatched();
  await other.expectNotDispatched();
});

it.each([{ healthy: false }, { received_at: "2000-01-01T00:00:00.000Z" }])(
  "does not bypass an unhealthy or stale target status %j",
  async (status) => {
    const instance = await makeCase("vllm", { replicas: 2 });
    const target = instance.deployments[1]!;
    await instance.redis.hSet(
      `deployment-status:{${instance.digest}}`,
      target.id,
      JSON.stringify({
        schema_version: 1,
        deployment_id: target.id,
        runtime_revision: instance.release.runtime_revision,
        received_at: new Date().toISOString(),
        healthy: true,
        accepting_requests: true,
        reason_code: null,
        ...status,
      }),
    );
    const response = await instance.http.post(instance.path, {
      headers: { ...instance.headers, [header]: target.id },
      json: instance.body(),
    });
    expectRejected(response, { code: "runtime_unavailable" });
    await instance.expectNotDispatched();
  },
);
