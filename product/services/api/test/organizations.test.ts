import { ControlServiceError } from "@gradiated/control";
import { describe, expect, it } from "vitest";

import {
  anonymous,
  authenticated,
  controlServiceProblems,
  expectProblem,
  failWith,
  unauthenticatedProblem,
  validationProblem,
  createTestApp,
  createdOrganization,
  postJson,
  user,
  workspaceId,
} from "./support.js";

describe("organization routes", () => {
  it("creates the organization aggregate for the current user", async () => {
    const received: unknown[] = [];
    const app = createTestApp({
      auth: authenticated,
      services: {
        organizations: {
          createForUser: async (userId, name) => {
            received.push({ userId, name });

            return { ...createdOrganization, name };
          },
        },
      },
    });

    const response = await postJson(app, "/api/v1/organizations", {
      name: "  Analytical Engines  ",
    });

    expect(response.status).toBe(201);
    expect(received).toEqual([{ userId: user.id, name: "Analytical Engines" }]);
    await expect(response.json()).resolves.toMatchObject({
      name: "Analytical Engines",
      role: "owner",
      default_workspace_id: workspaceId,
    });
  });

  it("requires a session", async () => {
    const response = await postJson(
      createTestApp({ auth: anonymous }),
      "/api/v1/organizations",
      { name: "Analytical Engines" },
    );

    await expectProblem(response, unauthenticatedProblem);
  });

  it("rejects an empty name before calling the service", async () => {
    const response = await postJson(
      createTestApp({ auth: authenticated }),
      "/api/v1/organizations",
      { name: "   " },
    );

    await expectProblem(response, validationProblem);
  });

  it.each(controlServiceProblems)("maps $code to $status", async (problem) => {
    const app = createTestApp({
      auth: authenticated,
      services: {
        organizations: {
          createForUser: failWith(
            new ControlServiceError(problem.code, "Rejected."),
          ),
        },
      },
    });

    const response = await postJson(app, "/api/v1/organizations", {
      name: "Analytical Engines",
    });

    await expectProblem(response, problem);
  });
});
