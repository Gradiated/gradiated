import { createServer, type IncomingMessage, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AdapterProbeTarget } from "@gradiated/control";

import { ApiMetrics } from "../src/metrics.js";
import {
  createAdapterProbe,
  createQualificationLock,
  reportAdapterQualification,
} from "../src/training/adapter-probe.js";
import { captureServiceLogs } from "./support.js";

const workspaceId = "0195f2a0-0000-7000-8000-000000000002";
const versionId = "0195f2a0-0000-7000-8000-000000000001";
const deploymentId = "0195f2a0-0000-7000-8000-000000000009";

const servers: Server[] = [];
afterEach(async () => {
  vi.restoreAllMocks();
  await Promise.all(
    servers
      .splice(0)
      .map((server) => new Promise((resolve) => server.close(resolve))),
  );
});

const body = async (request: IncomingMessage) => {
  let text = "";
  for await (const chunk of request) text += String(chunk);
  return text;
};

type SeenRequest = {
  method: string | undefined;
  url: string | undefined;
  body: string;
};

const loader = async (
  respond: (request: SeenRequest) => {
    status: number;
    body?: string;
    delayMs?: number;
  },
) => {
  const requests: SeenRequest[] = [];
  const server = createServer(async (request, response) => {
    const seen = {
      method: request.method,
      url: request.url,
      body: await body(request),
    };
    requests.push(seen);
    const reply = respond(seen);
    if (reply.delayMs)
      await new Promise((resolve) => setTimeout(resolve, reply.delayMs));
    response.writeHead(reply.status, { "Content-Type": "application/json" });
    response.end(reply.body ?? "");
  });
  servers.push(server);
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address() as AddressInfo;
  const target: AdapterProbeTarget = {
    id: deploymentId,
    modelId: "z-ai/glm-5.3-flash",
    serviceUrl: `http://127.0.0.1:${port}/alloc/${deploymentId}`,
    release: {
      schema_version: 1,
      runtime_revision: "glm-sglang-1",
      model_path: "m",
      model_revision: "r",
      tokenizer_path: "m",
      tokenizer_revision: "r",
      lora_enabled: true,
    },
  };
  return { requests, target };
};

describe("adapter probe", () => {
  it("posts the version ID and workspace to the allocation's loader probe", async () => {
    const { requests, target } = await loader(() => ({
      status: 200,
      body: JSON.stringify({ boot_id: "boot", ready: true }),
    }));

    await expect(
      createAdapterProbe()(target, { workspaceId, versionId }),
    ).resolves.toEqual({ ok: true });

    expect(requests).toEqual([
      {
        method: "POST",
        url: `/alloc/${deploymentId}/internal/adapters/probe`,
        body: JSON.stringify({ name: versionId, workspace_id: workspaceId }),
      },
    ]);
  });

  it.each([
    [422, '{"error":"invalid_adapter"}', true, "invalid_adapter"],
    [503, '{"error":"capacity_unavailable"}', false, "capacity_unavailable"],
    [503, '{"error":"preparation_failed"}', false, "preparation_failed"],
    [503, '{"error":"adapter_unavailable"}', false, "adapter_unavailable"],
    [503, "", false, "probe_http_503"],
    [404, "unknown deployment\n", false, "probe_http_404"],
    [502, '{"error":"<script>"}', false, "probe_http_502"],
    [200, '{"ready":false}', false, "probe_invalid_response"],
  ] as const)(
    "maps a %i %s response to a bounded reason",
    async (status, text, rejected, reason) => {
      const { target } = await loader(() => ({ status, body: text }));

      await expect(
        createAdapterProbe()(target, { workspaceId, versionId }),
      ).resolves.toEqual({ ok: false, rejected, reason });
    },
  );

  it("times out a hung probe", async () => {
    const { target } = await loader(() => ({ status: 200, delayMs: 1_000 }));

    await expect(
      createAdapterProbe({ timeoutMs: 50 })(target, { workspaceId, versionId }),
    ).resolves.toEqual({
      ok: false,
      rejected: false,
      reason: "probe_timeout",
    });
  });

  it("reports an unreachable allocation", async () => {
    const { target } = await loader(() => ({ status: 200 }));
    await Promise.all(
      servers
        .splice(0)
        .map((server) => new Promise((resolve) => server.close(resolve))),
    );

    await expect(
      createAdapterProbe()(target, { workspaceId, versionId }),
    ).resolves.toEqual({
      ok: false,
      rejected: false,
      reason: "probe_unreachable",
    });
  });

  it("refuses targets with credentials or a query", async () => {
    const probe = createAdapterProbe({
      fetch: vi.fn(async () => new Response("{}")),
    });
    for (const serviceUrl of [
      "http://user:secret@gpu.example:8888/alloc/a",
      "http://gpu.example:8888/alloc/a?x=1",
      "file:///etc/passwd",
    ])
      await expect(
        probe(
          {
            id: deploymentId,
            modelId: "m",
            serviceUrl,
            release: {} as AdapterProbeTarget["release"],
          },
          { workspaceId, versionId },
        ),
      ).resolves.toMatchObject({ ok: false, reason: "probe_unreachable" });
  });
});

describe("adapter qualification reports", () => {
  it("logs identifiers and counts each outcome by base model", async () => {
    const logs = captureServiceLogs();
    const metrics = new ApiMetrics({ collectProcessMetrics: false });
    metrics.initializeAdapterQualifications(["z-ai/glm-5.3-flash"]);
    const report = reportAdapterQualification(metrics);

    report({
      outcome: "passed",
      modelId: "z-ai/glm-5.3-flash",
      workspaceId,
      versionId,
      deploymentId,
      attempts: 1,
      durationMs: 8_300,
    });
    report({
      outcome: "rejected",
      reason: "invalid_adapter",
      modelId: "z-ai/glm-5.3-flash",
      workspaceId,
      versionId,
      deploymentId,
      attempts: 2,
      durationMs: 1_200,
    });

    expect(logs.events()).toMatchObject([
      {
        level: "info",
        event: "adapter_qualification",
        workspace_id: workspaceId,
        version_id: versionId,
        deployment_id: deploymentId,
        model_id: "z-ai/glm-5.3-flash",
        reason: "passed",
        attempt: 1,
        duration_ms: 8_300,
      },
      {
        level: "warn",
        event: "adapter_qualification",
        reason: "rejected/invalid_adapter",
        attempt: 2,
      },
    ]);
    const text = await metrics.registry.metrics();
    expect(text).toContain(
      'gradiated_api_adapter_qualifications_total{model="z-ai/glm-5.3-flash",outcome="passed",service="api"} 1',
    );
    expect(text).toContain(
      'gradiated_api_adapter_qualifications_total{model="z-ai/glm-5.3-flash",outcome="rejected",service="api"} 1',
    );
    expect(text).toContain(
      'gradiated_api_adapter_qualifications_total{model="z-ai/glm-5.3-flash",outcome="failed",service="api"} 0',
    );
    expect(text).toContain(
      'gradiated_api_adapter_qualification_duration_seconds_count{service="api",outcome="passed"} 1',
    );
  });
});

describe("adapter qualification lock", () => {
  const store = () => {
    const values = new Map<string, { value: string; expires: number }>();
    return {
      values,
      set: vi.fn(
        async (key: string, value: string, options: { PX: number }) => {
          const current = values.get(key);
          if (current && current.expires > Date.now()) return null;
          values.set(key, { value, expires: Date.now() + options.PX });
          return "OK";
        },
      ),
      eval: vi.fn(
        async (_: string, options: { keys: string[]; arguments: string[] }) => {
          const [key] = options.keys;
          if (values.get(key!)?.value !== options.arguments[0]) return 0;
          values.delete(key!);
          return 1;
        },
      ),
    };
  };

  it("lets one request hold a version until it releases it", async () => {
    const valkey = store();
    const lock = createQualificationLock(valkey);

    const release = await lock(versionId);
    expect(release).toBeTypeOf("function");
    expect(await lock(versionId)).toBeUndefined();
    expect(await lock("0195f2a0-0000-7000-8000-00000000000a")).toBeTypeOf(
      "function",
    );

    await release!();
    expect(await lock(versionId)).toBeTypeOf("function");
    expect(valkey.set).toHaveBeenCalledWith(
      `adapter-qualification:{${versionId}}`,
      expect.any(String),
      { NX: true, PX: 600_000 },
    );
  });

  it("does not release a lock that expired and was taken by another request", async () => {
    const valkey = store();
    const lock = createQualificationLock(valkey);
    const stale = await lock(versionId);
    valkey.values.get(`adapter-qualification:{${versionId}}`)!.expires = 0;
    await lock(versionId);

    await stale!();

    expect(await lock(versionId)).toBeUndefined();
  });

  it("answers unavailable when Valkey cannot be reached", async () => {
    const lock = createQualificationLock({
      set: async () => {
        throw new Error("connection refused");
      },
      eval: async () => 0,
    });

    await expect(lock(versionId)).rejects.toMatchObject({
      code: "unavailable",
    });
  });
});
