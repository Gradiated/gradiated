import { describe, expect, it, vi } from "vitest";
import { ControlServiceError } from "@gradiated/control";
import { authenticated, createTestApp, workspaceId } from "./support.js";

const versionId = "0198ae70-0e61-7a51-9d5c-2f4b5e6a7b8e";
const fileId = "0198ae70-0e61-7a51-9d5c-2f4b5e6a7b91";
const signature = "a".repeat(43);
const link = `${versionId}/${signature}`;
const sharePath = `/api/v1/workspaces/${workspaceId}/tasks/triage/versions/${versionId}/share`;
const file = {
  id: fileId,
  workspaceId,
  versionId,
  status: "ready" as const,
  completedAt: new Date(),
  name: "report.md",
  contentType: "text/markdown",
  sizeBytes: 100,
  createdAt: new Date("2026-11-01T00:00:00Z"),
};
const sharedReport = {
  versionId,
  version: "triage-v1",
  task: "triage",
  baseModelId: "Qwen/Qwen3-0.6B",
  createdAt: new Date("2026-11-01T00:00:00Z"),
  adapter: {
    format: "peft_lora" as const,
    artifact_uri: "s3://private/adapter.tar",
    sha256: "a".repeat(64),
    size_bytes: 1024,
    rank: 16,
    base_model_revision: "b".repeat(40),
  },
  files: [file],
};

const unusedShares = {
  get: vi.fn(),
  shared: vi.fn(),
  sharedContent: vi.fn(),
  sharedDownload: vi.fn(),
};

describe("report share routes", () => {
  it("returns a version's signed public link", async () => {
    const get = vi.fn(async () => ({ versionId, signature }));
    const app = createTestApp({
      auth: authenticated,
      services: { training: { shares: { ...unusedShares, get } } },
    });

    const response = await app.request(sharePath);
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ version_id: versionId, signature });
    expect(get).toHaveBeenCalledWith(
      expect.any(String),
      workspaceId,
      "triage",
      versionId,
    );
    expect((await app.request(sharePath, { method: "PUT" })).status).toBe(404);
  });

  it("serves shared reports without a session and keeps them out of search", async () => {
    const shares = {
      shared: vi.fn(async () => sharedReport),
      sharedContent: vi.fn(async () => ({
        name: "report.md",
        content_type: "text/markdown",
        content: "# Report",
      })),
      sharedDownload: vi.fn(async () => ({
        url: "https://storage.invalid/report.md",
        expires_at: new Date().toISOString(),
      })),
    };
    const app = createTestApp({
      services: { training: { shares: { ...unusedShares, ...shares } } },
    });

    for (const path of [
      `/api/v1/shared-reports/${link}`,
      `/api/v1/shared-reports/${link}/files/${fileId}/content`,
      `/api/v1/shared-reports/${link}/files/${fileId}/download`,
    ]) {
      const response = await app.request(path);
      expect(response.status).toBe(200);
      expect(response.headers.get("x-robots-tag")).toBe("noindex, nofollow");
      expect(response.headers.get("cache-control")).toBe("no-store");
    }
    const report = await (
      await app.request(`/api/v1/shared-reports/${link}`)
    ).json();
    expect(report).toEqual({
      task: "triage",
      version: "triage-v1",
      base_model_id: "Qwen/Qwen3-0.6B",
      created_at: "2026-11-01T00:00:00.000Z",
      adapter: { rank: 16, size_bytes: 1024, checkpoint: "b".repeat(40) },
      files: [
        {
          id: fileId,
          name: "report.md",
          content_type: "text/markdown",
          size_bytes: 100,
          created_at: "2026-11-01T00:00:00.000Z",
        },
      ],
    });
    expect(report).not.toHaveProperty("versionId");
    expect(JSON.stringify(report)).not.toContain("s3://");
  });

  it("returns 404 for unknown links and rejects malformed signatures", async () => {
    const shared = vi.fn(async () => {
      throw new ControlServiceError("not_found", "The report was not found.");
    });
    const app = createTestApp({
      services: { training: { shares: { ...unusedShares, shared } } },
    });

    expect((await app.request(`/api/v1/shared-reports/${link}`)).status).toBe(
      404,
    );
    expect(
      (await app.request(`/api/v1/shared-reports/${versionId}/short`)).status,
    ).toBe(422);
    expect(shared).toHaveBeenCalledOnce();
  });

  it("serves a shared version's adapter summary and base structure without a session", async () => {
    const weights = {
      rank: 1,
      alpha: 2,
      scale: 2,
      parameters: 10,
      modules: [],
    };
    const structure = { layerCount: 28, expertCount: 0 };
    const sharedAdapterWeights = vi.fn(async () => weights);
    const sharedAdapterConfiguration = vi.fn(async () => structure);
    const app = createTestApp({
      services: {
        training: { sharedAdapterWeights, sharedAdapterConfiguration },
      },
    });

    for (const [path, body] of [
      [`/api/v1/shared-reports/${link}/adapter/weights`, weights],
      [`/api/v1/shared-reports/${link}/adapter/configuration`, structure],
    ] as const) {
      const response = await app.request(path);
      expect(response.status).toBe(200);
      expect(await response.json()).toEqual(body);
      expect(response.headers.get("x-robots-tag")).toBe("noindex, nofollow");
    }
    expect(sharedAdapterWeights).toHaveBeenCalledWith(versionId, signature);
    expect(sharedAdapterConfiguration).toHaveBeenCalledWith(
      versionId,
      signature,
    );
  });

  it("returns 404 for a shared adapter behind an unknown link", async () => {
    const sharedAdapterWeights = vi.fn(async () => {
      throw new ControlServiceError("not_found", "The report was not found.");
    });
    const app = createTestApp({
      services: { training: { sharedAdapterWeights } },
    });

    expect(
      (await app.request(`/api/v1/shared-reports/${link}/adapter/weights`))
        .status,
    ).toBe(404);
  });
});
