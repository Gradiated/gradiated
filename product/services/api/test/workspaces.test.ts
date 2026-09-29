import { ControlServiceError } from "@gradiated/control";
import { describe, expect, it, vi } from "vitest";

import {
  anonymous,
  authenticated,
  controlServiceProblems,
  expectProblem,
  failWith,
  unauthenticatedProblem,
  createTestApp,
  now,
  organizationId,
  postJson,
  user,
  workspaceId,
  workspaceRecord,
  type TestApp,
} from "./support.js";

const workspacesPath = `/api/v1/organizations/${organizationId}/workspaces`;

describe("workspace routes", () => {
  it("patches workspace capture fields and rejects invalid updates", async () => {
    const updateWorkspace = vi.fn(async () => workspaceRecord);
    const app = createTestApp({
      auth: authenticated,
      services: { workspaces: { updateWorkspace } },
    });
    for (const [body, status] of [
      [{ trace_capture_enabled: true }, 200],
      [{ trace_retention_days: 90 }, 200],
      [{ trace_retention_days: 7 }, 422],
      [{}, 422],
      [{ is_default: true }, 422],
    ] as const) {
      const response = await app.request(`/api/v1/workspaces/${workspaceId}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      expect(response.status).toBe(status);
      if (status === 200)
        expect(await response.json()).toMatchObject({ id: workspaceId });
    }
    expect(updateWorkspace).toHaveBeenCalledTimes(2);
    expect(updateWorkspace).toHaveBeenLastCalledWith(user.id, workspaceId, {
      trace_retention_days: 90,
    });
    expect(
      (
        await app.request(`/api/v1/workspaces/${workspaceId}/trace-settings`, {
          method: "PATCH",
        })
      ).status,
    ).toBe(404);
  });

  it("lists workspaces explicitly for the selected organization", async () => {
    const app = createTestApp({
      auth: authenticated,
      services: {
        workspaces: { listWorkspaces: async () => [workspaceRecord] },
      },
    });

    const response = await app.request(workspacesPath);

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      data: [
        {
          id: workspaceId,
          organization_id: organizationId,
          name: "Default",
          is_default: true,
          trace_capture_enabled: false,
          trace_retention_days: 30,
          evaluation_judge: "openai/gpt-5.6-sol",
          archived_at: null,
          created_at: now.toISOString(),
          updated_at: now.toISOString(),
        },
      ],
      next_cursor: null,
    });
  });

  it("creates a workspace for the selected organization", async () => {
    const received: unknown[] = [];
    const app = createTestApp({
      auth: authenticated,
      services: {
        workspaces: {
          createWorkspace: async (userId, receivedOrganizationId, input) => {
            received.push({
              userId,
              organizationId: receivedOrganizationId,
              input,
            });

            return { ...workspaceRecord, name: input.name, isDefault: false };
          },
        },
      },
    });

    const response = await postJson(app, workspacesPath, {
      name: "  Research  ",
    });

    expect(response.status).toBe(201);
    expect(received).toEqual([
      { userId: user.id, organizationId, input: { name: "Research" } },
    ]);
    await expect(response.json()).resolves.toMatchObject({
      organization_id: organizationId,
      name: "Research",
      is_default: false,
    });
  });

  it.each([
    { query: "?include_archived=true", includeArchived: true },
    { query: "?include_archived=false", includeArchived: false },
    { query: "", includeArchived: false },
  ])(
    "passes include_archived $includeArchived for '$query'",
    async ({ query, includeArchived }) => {
      const received: unknown[] = [];
      const app = createTestApp({
        auth: authenticated,
        services: {
          workspaces: {
            listWorkspaces: async (...input) => {
              received.push(input);

              return [];
            },
          },
        },
      });

      const response = await app.request(`${workspacesPath}${query}`);

      expect(response.status).toBe(200);
      expect(received).toEqual([[user.id, organizationId, includeArchived]]);
    },
  );

  it.each(controlServiceProblems)(
    "maps $code on create to $status",
    async (problem) => {
      const app = createTestApp({
        auth: authenticated,
        services: {
          workspaces: {
            createWorkspace: failWith(
              new ControlServiceError(problem.code, "Rejected."),
            ),
          },
        },
      });

      const response = await postJson(app, workspacesPath, {
        name: "Research",
      });

      await expectProblem(response, problem);
    },
  );

  it.each([
    { name: "list", send: (app: TestApp) => app.request(workspacesPath) },
    {
      name: "create",
      send: (app: TestApp) =>
        postJson(app, workspacesPath, { name: "Research" }),
    },
  ])("requires a session to $name", async ({ send }) => {
    const response = await send(createTestApp({ auth: anonymous }));

    await expectProblem(response, unauthenticatedProblem);
  });
});
