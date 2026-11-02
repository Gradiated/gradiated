import { expect, inject } from "vitest";

import type { Case } from "./case.js";
import { GatewayProcess } from "./gateway-process.js";
import { Client, type Response } from "./http-client.js";
import type { JsonObject } from "./json.js";
import { freePort } from "./ports.js";

export const checkQualificationIsolation = async (
  instance: Case,
  outsider: Case,
  body: JsonObject,
  succeeded: (response: Response) => Promise<void>,
): Promise<void> => {
  const target = instance.deployments[1]!;
  target.status = "unavailable";
  await instance.publish();
  await instance.status();
  const stack = inject("stack");
  const gateway = await GatewayProcess.start({
    redisUrl: stack.redisUrl,
    databaseUrl: stack.databaseUrl,
    runtimeToken: stack.runtimeToken,
    port: await freePort(),
    generationTimeoutSeconds: 120,
    verificationWorkspaceId: instance.workspace,
    logName: `qualification-isolation-${crypto.randomUUID()}`,
  });
  const client = new Client(gateway.url, 130_000);
  const header = { "x-gradiated-deployment-id": target.id };
  try {
    for (let index = 0; index < 3; index += 1) {
      const ordinary = await client.post(instance.path, {
        headers: instance.headers,
        json: body,
      });
      expect(ordinary.status, ordinary.text).toBe(200);
      await succeeded(ordinary);
    }
    expect(instance.runtimes[0]!.calls).toHaveLength(3);
    expect(instance.runtimes[1]!.calls).toHaveLength(0);

    const wrongModel = await client.post(outsider.path, {
      headers: { ...outsider.headers, ...header },
      json: outsider.body(),
    });
    expect(wrongModel.status, wrongModel.text).toBe(404);
    await outsider.expectNotDispatched();

    const verified = await client.post(instance.path, {
      headers: { ...instance.headers, ...header },
      json: body,
    });
    expect(verified.status, verified.text).toBe(200);
    await succeeded(verified);
    expect(instance.runtimes[0]!.calls).toHaveLength(3);
    expect(instance.runtimes[1]!.calls).toHaveLength(1);

    target.status = "draining";
    await instance.publish();
    // A new process proves persisted draining state without relying on cache expiry.
    await gateway.stop();
    const draining = await GatewayProcess.start({
      redisUrl: stack.redisUrl,
      databaseUrl: stack.databaseUrl,
      runtimeToken: stack.runtimeToken,
      port: await freePort(),
      generationTimeoutSeconds: 120,
      verificationWorkspaceId: instance.workspace,
      logName: `qualification-draining-${crypto.randomUUID()}`,
    });
    try {
      const response = await new Client(draining.url).post(instance.path, {
        headers: { ...instance.headers, ...header },
        json: body,
      });
      expect(response.status, response.text).toBe(404);
      expect(instance.runtimes[1]!.calls).toHaveLength(1);
    } finally {
      await draining.stop();
    }
  } finally {
    await gateway.stop();
  }
};
