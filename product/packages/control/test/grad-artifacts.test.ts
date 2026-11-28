import { describe, expect, it, vi } from "vitest";
import { createGradArtifacts, versionPinHolder } from "../src/training/grad.js";

const workspaceId = "0198ae50-94d8-7d4d-a8be-9f9b44b8c774";
const versionId = "0198ae50-94d8-7d4d-a8be-9f9b44b8c775";
const artifact = {
  id: "fast-diff-merge@2026-11-26-1",
  workspace_id: workspaceId,
  name: "fast-diff-merge",
  version: "2026-11-26-1",
  run_id: "run_1",
  checkpoint_id: null,
  base_model: "qwen/qwen3-8b",
  recipe_kind: "sft",
  format: "peft_lora",
  sha256: "a".repeat(64),
  size_bytes: 10,
  manifest: { base_model_repo: "Qwen/Qwen3-8B" },
  provenance: { source: "run", run_id: "run_1", uploader: null, uri: null },
  eval_report: null,
  created_at: "2026-11-26T00:00:00Z",
};

// grad's GET /internal/v1/workspaces/{ws}/artifacts/{ref} (routes/internal-cloud.ts).
const resolved = (overrides: Record<string, unknown> = {}) => ({
  artifact,
  object: {
    key: `artifacts/${workspaceId}/${artifact.sha256}`,
    sha256: artifact.sha256,
    checksum_sha256: Buffer.from(artifact.sha256, "hex").toString("base64"),
    checksum_type: "FULL_OBJECT",
    size_bytes: 12,
    ...overrides,
  },
  download_url: "https://s3.invalid/x",
  expires_at: "2026-11-27T00:00:00Z",
});

const client = (responses: Response[]) => {
  const fetch = vi.fn(async () => responses.shift()!);
  const authorization = vi.fn(async () => "service-jwt");
  return {
    fetch,
    authorization,
    grad: createGradArtifacts({
      baseUrl: "http://grad-internal.training.svc:8789",
      authorization,
      fetch: fetch as unknown as typeof globalThis.fetch,
    }),
  };
};
const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status });

describe("grad artifact client", () => {
  it("resolves a reference with a workspace-scoped service token", async () => {
    const { fetch, authorization, grad } = client([json(200, resolved())]);

    expect(await grad.resolve(workspaceId, "fast-diff-merge@latest")).toEqual({
      id: artifact.id,
      workspace_id: workspaceId,
      name: "fast-diff-merge",
      version: "2026-11-26-1",
      format: "peft_lora",
      recipe_kind: "sft",
      base_model: "qwen/qwen3-8b",
      key: `artifacts/${workspaceId}/${artifact.sha256}`,
      sha256: artifact.sha256,
      size_bytes: 12,
      source: "run",
    });
    expect(String((fetch.mock.calls[0] as unknown[])[0])).toBe(
      `http://grad-internal.training.svc:8789/internal/v1/workspaces/${workspaceId}/artifacts/fast-diff-merge%40latest`,
    );
    expect(authorization).toHaveBeenCalledWith({
      workspaceId,
      scopes: ["artifacts:pin"],
    });
  });

  it("treats a missing artifact or another workspace's as not found", async () => {
    const { grad } = client([
      json(404, { code: "artifact_not_found" }),
      json(200, {
        ...resolved(),
        artifact: { ...artifact, workspace_id: versionId },
        object: { ...resolved().object, key: `artifacts/${versionId}/x` },
      }),
      json(409, { code: "artifact_not_servable" }),
    ]);

    expect(await grad.resolve(workspaceId, artifact.id)).toBeNull();
    expect(await grad.resolve(workspaceId, artifact.id)).toBeNull();
    await expect(grad.resolve(workspaceId, artifact.id)).rejects.toMatchObject({
      code: "artifact_not_servable",
    });
  });

  it("refuses a stored object that is not the artifact's", async () => {
    const { grad } = client([
      json(200, resolved({ sha256: "b".repeat(64) })),
      json(200, resolved({ checksum_sha256: "AAAA" })),
      json(200, resolved({ key: `artifacts/${versionId}/${artifact.sha256}` })),
      json(200, resolved({ key: `artifacts/${workspaceId}/../x` })),
      json(200, resolved({ checksum_type: "COMPOSITE" })),
      json(409, { code: "artifact_checksum_mismatch" }),
    ]);

    for (let attempt = 0; attempt < 5; attempt++)
      await expect(
        grad.resolve(workspaceId, artifact.id),
      ).rejects.toMatchObject({ code: "unavailable" });
    await expect(grad.resolve(workspaceId, artifact.id)).rejects.toMatchObject({
      code: "artifact_checksum_mismatch",
    });
  });

  it("reads a release stored at its job key from before artifacts/", async () => {
    const key = `ws/${workspaceId}/jobs/job_1/1/${artifact.sha256}`;
    const { grad } = client([json(200, resolved({ key }))]);

    expect(await grad.resolve(workspaceId, artifact.id)).toMatchObject({ key });
  });

  it("pins with a holder and reason and maps refusals", async () => {
    const holder = versionPinHolder(versionId);
    const { fetch, grad } = client([
      json(201, { pin: { artifact_id: artifact.id, holder }, artifact }),
      json(409, { code: "artifact_not_servable" }),
      json(500, {}),
    ]);

    await grad.pin(workspaceId, artifact.id, holder);
    const [url, init] = fetch.mock.calls[0] as unknown as [URL, RequestInit];
    expect(String(url)).toBe(
      `http://grad-internal.training.svc:8789/internal/v1/workspaces/${workspaceId}/artifacts/fast-diff-merge%402026-11-26-1/pins/inference%3Aversion%3A${versionId}`,
    );
    expect(init.method).toBe("PUT");

    await expect(
      grad.pin(workspaceId, artifact.id, holder),
    ).rejects.toMatchObject({ code: "artifact_not_servable" });
    await expect(
      grad.pin(workspaceId, artifact.id, holder),
    ).rejects.toMatchObject({ code: "unavailable" });
  });

  it("unpins idempotently", async () => {
    const { grad } = client([
      new Response(null, { status: 204 }),
      json(404, {}),
    ]);
    const holder = versionPinHolder(versionId);

    await grad.unpin(workspaceId, artifact.id, holder);
    await grad.unpin(workspaceId, artifact.id, holder);
  });
});
