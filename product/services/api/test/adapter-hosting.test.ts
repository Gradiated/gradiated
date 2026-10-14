import {
  ControlServiceError,
  type AdapterHostingService,
} from "@gradiated/control";
import { describe, expect, it, vi } from "vitest";
import { createTestApp, postJson, workspaceId } from "./support.js";

import { createGpuControlApp } from "../src/gpu-control.js";

const hostHeaders = {};
const versionId = "0198ae50-94d8-7d4d-a8be-9f9b44b8c774";
const taskId = "0198ae50-94d8-7d4d-a8be-9f9b44b8c775";
const sha256 = "a".repeat(64);
const grantsPath = "/api/internal/v1/adapter-downloads";
const listPath = "/api/internal/v1/task-versions/production";
const target = { workspace_id: workspaceId, version_name: "triage-v1" };
const at = new Date("2026-10-02T00:00:00Z");
const row = {
  task: {
    id: taskId,
    workspaceId,
    name: "triage",
    baseModelId: "gradiated/base",
    comparisonModelId: null,
    judgeModelId: "openai/gpt-5" as const,
    productionVersionId: versionId,
    trainingSchedule: null,
    createdAt: at,
    updatedAt: at,
  },
  version: {
    id: versionId,
    workspaceId,
    taskId,
    trainingRunId: versionId,
    name: "triage-v1",
    baseModelId: "gradiated/base",
    status: "available" as const,
    adapter: {
      format: "peft_lora" as const,
      artifact_uri: "s3://bucket/adapter",
      sha256,
      size_bytes: 1024,
      rank: 2,
      base_model_revision: "frozen-revision",
    },
    createdAt: at,
    updatedAt: at,
  },
  download: {
    url: "https://bucket.s3.amazonaws.com/adapter?signature=test",
    expires_at: "2030-01-01T00:00:00Z",
  },
};
const fixture = () => {
  const service = {
    grant: vi.fn(async () => row),
    productionVersions: vi.fn(async () => [target]),
  } satisfies AdapterHostingService;
  const app = createGpuControlApp({
    provider: "runpod",
    status: { report: async () => undefined },
    check: async () => ({}),
    adapters: { service },
  });
  return { app, service };
};

describe("private adapter routes", () => {
  it("does not expose GPU routes on the public app", async () => {
    const app = createTestApp();
    for (const path of [
      listPath,
      grantsPath,
      "/v1/deployment-status",
      "/api/internal/v1/instances/0198ae50-94d8-7d4d-a8be-9f9b44b8c776/nomad-certificates",
    ])
      expect(
        (
          await app.request(path, {
            method: path === listPath ? "GET" : "POST",
          })
        ).status,
      ).toBe(404);
  });

  it("returns existing version metadata and the signed download protocol expected by the loader", async () => {
    const { app, service } = fixture();
    const response = await postJson(app, grantsPath, target, hostHeaders);
    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(await response.json()).toEqual({
      workspace_id: workspaceId,
      version: {
        id: versionId,
        name: "triage-v1",
        task: "triage",
        training_run_id: versionId,
        base_model_id: "gradiated/base",
        adapter: row.version.adapter,
        status: "available",
        is_production: true,
        created_at: at.toISOString(),
      },
      download: row.download,
    });
    expect(service.grant).toHaveBeenCalledWith(workspaceId, "triage-v1");
  });

  it("returns bounded production identities and empty lists", async () => {
    const { app, service } = fixture();
    const get = () =>
      app.request(listPath + "?base_model_id=gradiated/base", {
        headers: hostHeaders,
      });
    const response = await get();
    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(await response.json()).toEqual({ data: [target] });
    expect(service.productionVersions).toHaveBeenCalledWith("gradiated/base");
    service.productionVersions.mockResolvedValueOnce([]);
    expect(await (await get()).json()).toEqual({ data: [] });
  });

  it("validates exact identity input and required base model", async () => {
    const { app, service } = fixture();
    for (const body of [
      { ...target, version_name: "" },
      { ...target, version_name: "a".repeat(301) },
      { ...target, workspace_id: "bad" },
      { ...target, url: "https://arbitrary.example" },
    ]) {
      expect((await postJson(app, grantsPath, body, hostHeaders)).status).toBe(
        422,
      );
    }
    expect(
      (
        await app.request(listPath, {
          headers: hostHeaders,
        })
      ).status,
    ).toBe(422);
    expect(service.grant).not.toHaveBeenCalled();
    expect(service.productionVersions).not.toHaveBeenCalled();
  });

  it.each([
    ["not_found", 404],
    ["unavailable", 503],
  ] as const)("maps %s safely", async (code, status) => {
    const { app, service } = fixture();
    service.grant.mockRejectedValueOnce(
      new ControlServiceError(code, "Adapter unavailable."),
    );
    const response = await postJson(app, grantsPath, target, hostHeaders);
    expect(response.status).toBe(status);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(await response.text()).not.toContain("signature=test");
  });

  it("keeps GPU routes out of public OpenAPI", async () => {
    const app = createTestApp();
    const document = await (await app.request("/api/openapi.json")).json();
    expect(document.paths).not.toHaveProperty(grantsPath);
    expect(document.paths).not.toHaveProperty(listPath);
  });
});
