import { describe, expect, it, vi } from "vitest";
import { PublishError, type TrainingService } from "@gradiated/control";
import { authenticated, createTestApp, user, workspaceId } from "./support.js";

const versions = `/api/v1/workspaces/${workspaceId}/tasks/fast-diff-merge/versions`;
const now = new Date("2026-11-27T12:00:00.000Z");
const task = {
  id: "0198ae50-94d8-7d4d-a8be-9f9b44b8c774",
  name: "fast-diff-merge",
  productionVersionId: null,
};
const version = {
  id: "0198ae50-94d8-7d4d-a8be-9f9b44b8c775",
  name: "2026-11-26-1",
  trainingRunId: null,
  baseModelId: "Qwen/Qwen3-0.6B",
  adapter: {
    format: "peft_lora",
    artifact_uri: `s3://grad/artifacts/${workspaceId}/${"a".repeat(64)}.grad.tar.gz`,
    sha256: "a".repeat(64),
    size_bytes: 10,
    rank: 32,
  },
  status: "available",
  createdAt: now,
};
const post = (app: ReturnType<typeof createTestApp>, body: unknown) =>
  app.request(versions, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });

const appWith = (artifacts: Record<string, unknown>) =>
  createTestApp({
    auth: authenticated,
    services: {
      training: {
        artifacts: artifacts as unknown as TrainingService["artifacts"],
      },
    },
  });

describe("publishing artifacts as versions", () => {
  it("publishes into the model in the path and reports the serving check", async () => {
    const publish = vi.fn(async () => ({
      task,
      version,
      created: true,
      qualification: { outcome: "passed" },
    }));
    const response = await post(appWith({ publish }), {
      artifact: "fast-diff-merge@2026-11-26-1",
    });

    expect(response.status).toBe(201);
    expect(await response.json()).toMatchObject({
      name: "2026-11-26-1",
      task: "fast-diff-merge",
      status: "available",
      qualification: { outcome: "passed" },
    });
    expect(publish).toHaveBeenCalledWith(user.id, workspaceId, {
      artifact: "fast-diff-merge@2026-11-26-1",
      task: "fast-diff-merge",
    });
  });

  it("answers 200 when the artifact already has a version", async () => {
    const publish = vi.fn(async () => ({
      task,
      version,
      created: false,
      qualification: { outcome: "passed" },
    }));
    expect(
      (await post(appWith({ publish }), { artifact: "fast-diff-merge@latest" }))
        .status,
    ).toBe(200);
  });

  it("rejects malformed references before calling the service", async () => {
    const publish = vi.fn();
    for (const body of [
      {},
      { artifact: "Bad Name@1" },
      { artifact: "x", extra: 1 },
    ])
      expect((await post(appWith({ publish }), body)).status).toBe(422);
    expect(publish).not.toHaveBeenCalled();
  });

  it.each([
    ["format_not_servable_yet", 422],
    ["base_revision_mismatch", 422],
    ["version_name_taken", 409],
  ] as const)("maps %s to %i with its code", async (code, status) => {
    const publish = vi.fn(async () => {
      throw new PublishError(code, "Supported formats: peft_lora, cartridge.");
    });
    const response = await post(appWith({ publish }), {
      artifact: "fast-diff-merge@latest",
    });

    expect(response.status).toBe(status);
    expect(await response.json()).toMatchObject({
      code,
      detail: "Supported formats: peft_lora, cartridge.",
    });
  });

  it("deletes a version", async () => {
    const deleteVersion = vi.fn(async () => undefined);
    const response = await appWith({ deleteVersion }).request(
      `${versions}/2026-11-26-1`,
      { method: "DELETE" },
    );

    expect(response.status).toBe(204);
    expect(deleteVersion).toHaveBeenCalledWith(
      user.id,
      workspaceId,
      "fast-diff-merge",
      "2026-11-26-1",
    );
  });

  it("lists production changes", async () => {
    const listProductionChanges = vi.fn(async () => [
      {
        id: "0198ae50-94d8-7d4d-a8be-9f9b44b8c776",
        taskId: task.id,
        fromVersionId: null,
        toVersionId: version.id,
        actor: `user:${user.id}`,
        createdAt: now,
      },
    ]);
    const response = await createTestApp({
      auth: authenticated,
      services: { training: { listProductionChanges } },
    }).request(
      `/api/v1/workspaces/${workspaceId}/tasks/fast-diff-merge/production-changes`,
    );

    expect(await response.json()).toEqual({
      data: [
        {
          id: "0198ae50-94d8-7d4d-a8be-9f9b44b8c776",
          from_version_id: null,
          to_version_id: version.id,
          actor: `user:${user.id}`,
          created_at: now.toISOString(),
        },
      ],
    });
  });
});
