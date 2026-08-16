import type { AuthService, SessionUser } from "../src/types.js";

export const organizationId = "0198ae59-294a-73a9-9d2f-962449d34226";
export const workspaceId = "0198ae5a-2529-7c1a-801b-dc9d5f876a94";
export const apiKeyId = "0198ae6f-68b0-7644-812d-c4bf16a926e3";
export const now = new Date("2026-08-16T12:05:00.000Z");

export const user: SessionUser = {
  id: "0198ae50-94d8-7d4d-a8be-9f9b44b8c774",
  name: "Ada Lovelace",
  email: "ada@example.com",
  emailVerified: true,
  image: null,
  createdAt: new Date("2026-08-16T12:00:00.000Z"),
};

export const authenticated: AuthService = {
  handler: async () => new Response(null, { status: 404 }),
  resolveSession: async () => user,
};

export function workspaceService() {
  return {
    listWorkspaces: async () => [
      {
        id: workspaceId,
        organizationId,
        name: "Default",
        isDefault: true,
        archivedAt: null,
        createdAt: now,
        updatedAt: now,
      },
    ],
    createWorkspace: async (
      _userId: string,
      receivedOrganizationId: string,
      input: { name: string },
    ) => ({
      id: workspaceId,
      organizationId: receivedOrganizationId,
      name: input.name,
      isDefault: false,
      archivedAt: null,
      createdAt: now,
      updatedAt: now,
    }),
    listApiKeys: async () => [],
    createApiKey: async (
      userId: string,
      receivedOrganizationId: string,
      receivedWorkspaceId: string,
      input: { name: string; expiresAt: Date | null },
    ) => ({
      apiKey: {
        id: apiKeyId,
        organizationId: receivedOrganizationId,
        workspaceId: receivedWorkspaceId,
        name: input.name,
        expiresAt: input.expiresAt,
        revokedAt: null,
        createdBy: userId,
        createdAt: now,
        updatedAt: now,
      },
      secret: `grad_${"a".repeat(43)}`,
    }),
    revokeApiKey: async () => undefined,
  };
}
