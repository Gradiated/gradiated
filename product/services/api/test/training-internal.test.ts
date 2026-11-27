import { describe, expect, it, vi } from "vitest";
import type { EvalVersions } from "@gradiated/control";
import { createTrainingInternalApp } from "../src/training-internal.js";

const token = "t".repeat(40);
const previous = "p".repeat(40);
const workspaceId = "0198ae50-94d8-7d4d-a8be-9f9b44b8c774";
const path = "/api/internal/v1/training/eval-versions";

const app = (publish: EvalVersions["publish"]) =>
  createTrainingInternalApp({ tokens: [token, previous], evals: { publish } });
const post = (target: ReturnType<typeof app>, body: unknown, bearer = token) =>
  target.request(path, {
    method: "POST",
    headers: {
      authorization: `Bearer ${bearer}`,
      "content-type": "application/json",
    },
    body: JSON.stringify(body),
  });
const published = {
  model: `acme/grad-eval-${workspaceId}/art_abc`,
  version: { id: workspaceId },
};

describe("training internal listener", () => {
  it("accepts the current and previous token and nothing else", async () => {
    const publish = vi.fn(
      async () => published,
    ) as unknown as EvalVersions["publish"];
    const target = app(publish);
    const body = {
      workspace_id: workspaceId,
      artifact_id: "fast-diff-merge@2026-11-26-1",
    };

    for (const bearer of ["x".repeat(40), `${token}x`, ""])
      expect((await post(target, body, bearer)).status).toBe(401);
    expect(publish).not.toHaveBeenCalled();

    for (const bearer of [token, previous]) {
      const response = await post(target, body, bearer);
      expect(response.status).toBe(200);
      expect(response.headers.get("cache-control")).toBe("no-store");
      expect(await response.json()).toEqual({
        model: published.model,
        version_id: workspaceId,
      });
    }
    expect(publish).toHaveBeenCalledWith(
      workspaceId,
      "fast-diff-merge@2026-11-26-1",
    );
  });

  it("validates bodies", async () => {
    const publish = vi.fn() as unknown as EvalVersions["publish"];
    for (const body of [
      { workspace_id: workspaceId, artifact_id: "Bad Name" },
      { workspace_id: "nope", artifact_id: "art_abc" },
      { workspace_id: workspaceId, artifact_id: "art_abc", extra: true },
    ])
      expect((await post(app(publish), body)).status).toBe(422);
    expect(publish).not.toHaveBeenCalled();
  });
});
