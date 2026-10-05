import { randomUUID } from "node:crypto";
import { afterEach, beforeEach, expect, it } from "vitest";
import { Registry } from "prom-client";
import type { NomadReplica } from "@gradiated/control";
import type { RedisClientType } from "@gradiated/valkey";
import { connectTestValkey } from "../support/valkey.js";
import {
  InferenceProbeMetrics,
  probeLeaseScript,
  runInferenceProbes,
} from "../../src/inference-probes.js";

let client: RedisClientType;
beforeEach(async () => {
  client = await connectTestValkey();
});
afterEach(async () => {
  await client.close();
});

it("elects one owner atomically, renews its lease and allows takeover after expiry", async () => {
  const key = `probe-test:${randomUUID()}`;
  const attempt = (owner: string) =>
    client.eval(probeLeaseScript, { keys: [key], arguments: [owner] });
  const results = await Promise.all([attempt("first"), attempt("second")]);
  expect(results.sort()).toEqual([0, 1]);
  const owner = (await client.get(key))!;
  const standby = owner === "first" ? "second" : "first";
  expect(await attempt(owner)).toBe(1);
  expect(await client.pTTL(key)).toBeGreaterThan(14_000);
  expect(await attempt(standby)).toBe(0);
  await client.pExpire(key, 1);
  await new Promise((resolve) => setTimeout(resolve, 10));
  expect(await attempt(standby)).toBe(1);
  expect(await client.get(key)).toBe(standby);
  await client.del(key);
});

it("standby shutdown preserves the leader lease and a new worker takes over after leader shutdown", async () => {
  const key = "gradiated:inference-probes:leader";
  const replica = {
    id: randomUUID(),
    modelId: "test/model",
    release: {},
  } as NomadReplica;
  const leader = new AbortController();
  let notifyReady!: () => void;
  const ready = new Promise<void>((resolve) => {
    notifyReady = resolve;
  });
  let requests = 0;
  const options = {
    eval: (script: string, options: { keys: string[]; arguments: string[] }) =>
      client.eval(script, options),
    replicas: async () => [replica],
    probe: async () => {
      requests++;
    },
  };
  const run = runInferenceProbes({
    ...options,
    signal: leader.signal,
    metrics: new InferenceProbeMetrics(new Registry()),
    onReady: async () => notifyReady(),
  });
  await ready;
  try {
    const owner = await client.get(key);
    expect(owner).toBeTruthy();
    const standby = new AbortController();
    await runInferenceProbes({
      ...options,
      signal: standby.signal,
      metrics: new InferenceProbeMetrics(new Registry()),
      onReady: async () => standby.abort(),
    });
    expect(requests).toBe(1);
    expect(await client.get(key)).toBe(owner);
  } finally {
    leader.abort();
    await run;
  }
  expect(await client.get(key)).toBeNull();
  const replacement = new AbortController();
  await runInferenceProbes({
    ...options,
    signal: replacement.signal,
    metrics: new InferenceProbeMetrics(new Registry()),
    onReady: async () => replacement.abort(),
  });
  expect(requests).toBe(2);
});
