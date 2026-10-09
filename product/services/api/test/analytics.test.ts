import { createPostHogServer } from "@gradiated/analytics/server";
import { ControlServiceError } from "@gradiated/control";
import { describe, expect, it, vi } from "vitest";
import { createApiAnalytics, createSignupHandler } from "../src/analytics.js";
import {
  authenticated,
  createTestApp,
  postJson,
  user,
  organizationId,
  workspaceId,
  workspaceRecord,
} from "./support.js";

const setup = () => {
  const events: Record<string, unknown>[] = [];
  const fetch = vi.fn<typeof globalThis.fetch>(async (_input, init) => {
    events.push(JSON.parse(String(init?.body)));
    return new Response(null, { status: 200 });
  });
  const client = createPostHogServer({ key: "test", fetch });
  const analytics = createApiAnalytics(
    client,
    async () => organizationId,
    vi.fn(),
  );
  return { events, client, analytics };
};

describe("server-owned product events", () => {
  it("emits signup after personal organization provisioning with a stable event ID", async () => {
    const { client, events } = setup();
    const ensure = vi.fn(async () => ({
      id: organizationId,
      defaultWorkspaceId: workspaceId,
    }));
    await createSignupHandler(ensure, client)(user);
    await client.flush();
    expect(ensure).toHaveBeenCalledWith(user.id);
    expect(events).toContainEqual(
      expect.objectContaining({
        event: "user_signed_up",
        distinct_id: user.id,
        uuid: user.id,
        properties: expect.objectContaining({
          user_id: user.id,
          organization_id: organizationId,
          workspace_id: workspaceId,
          source: "api",
          $set: { email: user.email },
        }),
      }),
    );
    expect(
      events.filter(({ event }) => event === "$groupidentify"),
    ).toHaveLength(2);
  });

  it("never records a signup when provisioning fails", async () => {
    const { client, events } = setup();
    const handler = createSignupHandler(async () => {
      throw new Error("provisioning failed");
    }, client);
    await expect(handler(user)).rejects.toThrow("provisioning failed");
    await client.flush();
    expect(events).toEqual([]);
  });

  it("records a successful API workspace creation without free-text inputs", async () => {
    const { analytics, events } = setup();
    const app = createTestApp({
      auth: authenticated,
      analytics,
      services: {
        workspaces: { createWorkspace: async () => workspaceRecord },
      },
    });
    const response = await postJson(
      app,
      `/api/v1/organizations/${organizationId}/workspaces`,
      { name: "private workspace name" },
    );
    expect(response.status).toBe(201);
    await analytics.flush();
    expect(events).toContainEqual(
      expect.objectContaining({
        event: "workspace_created",
        properties: expect.objectContaining({
          $groups: { organization: organizationId, workspace: workspaceId },
        }),
      }),
    );
    expect(JSON.stringify(events)).not.toContain("private workspace name");
  });

  it("does not record denied mutations", async () => {
    const { analytics, events } = setup();
    const app = createTestApp({
      auth: authenticated,
      analytics,
      services: {
        workspaces: {
          createWorkspace: async () => {
            throw new ControlServiceError("forbidden", "denied");
          },
        },
      },
    });
    expect(
      (
        await postJson(
          app,
          `/api/v1/organizations/${organizationId}/workspaces`,
          { name: "private" },
        )
      ).status,
    ).toBe(403);
    await analytics.flush();
    expect(events).toEqual([]);
  });

  it("resolves the resource organization for revocations", async () => {
    const { analytics, events } = setup();
    analytics.trackWorkspace(user.id, "api_key_revoked", {
      workspace_id: workspaceId,
      api_key_id: "key",
    });
    await analytics.flush();
    expect(events[0]).toMatchObject({
      distinct_id: user.id,
      properties: {
        organization_id: organizationId,
        workspace_id: workspaceId,
        $groups: { organization: organizationId, workspace: workspaceId },
      },
    });
  });
});
