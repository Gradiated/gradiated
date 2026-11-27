import { ControlServiceError } from "@gradiated/control";
import { describe, expect, it, vi } from "vitest";

import type { TrainingTokenSubject } from "../src/auth/training-tokens.js";
import {
  apiKeyId,
  apiKeySecret,
  authenticated,
  controlServiceProblems,
  createTestApp,
  expectProblem,
  failWith,
  organizationId,
  unauthenticatedProblem,
  user,
  workspaceId,
} from "./support.js";

const path = `/api/v1/workspaces/${workspaceId}/training-tokens`;
const expiresAt = new Date("2026-11-27T12:10:00.000Z");

const testApp = (
  describeTrainingMember = vi.fn(async () => ({
    organizationId,
    workspaceId,
    role: "member" as const,
  })),
) => {
  const signTrainingToken = vi.fn(async (_subject: TrainingTokenSubject) => ({
    token: "header.payload.signature",
    expiresAt,
  }));
  const app = createTestApp({
    auth: { ...authenticated, signTrainingToken },
    services: { workspaces: { describeTrainingMember } },
  });

  return { app, describeTrainingMember, signTrainingToken };
};

describe("training tokens", () => {
  it("signs a token for the signed-in member's workspace", async () => {
    const { app, describeTrainingMember, signTrainingToken } = testApp();

    const response = await app.request(path, { method: "POST" });

    expect(response.status).toBe(201);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(await response.json()).toEqual({
      token: "header.payload.signature",
      expires_at: expiresAt.toISOString(),
    });
    expect(describeTrainingMember).toHaveBeenCalledWith(user.id, workspaceId);
    expect(signTrainingToken).toHaveBeenCalledWith({
      userId: user.id,
      organizationId,
      workspaceId,
      role: "member",
    });
  });

  it.each(controlServiceProblems)(
    "maps $code to $status and signs nothing",
    async (problem) => {
      const { app, signTrainingToken } = testApp(
        vi.fn(failWith(new ControlServiceError(problem.code, "Denied."))),
      );

      await expectProblem(await app.request(path, { method: "POST" }), problem);
      expect(signTrainingToken).not.toHaveBeenCalled();
    },
  );

  it("requires a session", async () => {
    const app = createTestApp();

    await expectProblem(
      await app.request(path, { method: "POST" }),
      unauthenticatedProblem,
    );
  });

  it("refuses a workspace API key", async () => {
    const app = createTestApp({
      services: {
        workspaces: {
          authenticateCredential: async () => ({
            credential: "api_key" as const,
            credentialId: apiKeyId,
            organizationId,
            workspaceId,
            user,
          }),
        },
      },
    });

    await expectProblem(
      await app.request(path, {
        method: "POST",
        headers: { Authorization: `Bearer ${apiKeySecret}` },
      }),
      unauthenticatedProblem,
    );
  });
});
