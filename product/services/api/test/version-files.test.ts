import { describe, expect, it, vi } from "vitest";
import { authenticated, createTestApp, user, workspaceId } from "./support.js";

const versionId = "0198ae70-0e61-7a51-9d5c-2f4b5e6a7b8e";
const fileId = "0198ae70-0e61-7a51-9d5c-2f4b5e6a7b91";
const path = `/api/v1/workspaces/${workspaceId}/tasks/triage/versions/${versionId}/files`;

describe("version file routes", () => {
  it.each([
    { isStaff: false, emailVerified: true, impersonatedBy: null, status: 403 },
    { isStaff: true, emailVerified: false, impersonatedBy: null, status: 403 },
    { isStaff: true, emailVerified: true, impersonatedBy: null, status: 201 },
    {
      isStaff: false,
      emailVerified: true,
      impersonatedBy: user.id,
      status: 201,
    },
  ])(
    "restricts file mutations to verified staff sessions: %j",
    async ({ status, ...session }) => {
      const create = vi.fn(async () => ({
        id: fileId,
        upload_url: "https://storage.invalid/upload",
        expires_at: new Date().toISOString(),
      }));
      const complete = vi.fn(async () => ({
        id: fileId,
        workspaceId,
        versionId,
        status: "ready" as const,
        completedAt: new Date(),
        name: "report.md",
        contentType: "text/markdown",
        sizeBytes: 100,
        createdAt: new Date(),
      }));
      const remove = vi.fn(async () => {});
      const app = createTestApp({
        auth: {
          ...authenticated,
          resolveSession: async () => ({ ...user, ...session }),
        },
        services: {
          training: {
            files: {
              create,
              complete,
              remove,
              list: vi.fn(),
              content: vi.fn(),
              download: vi.fn(),
            },
          },
        },
      });
      const response = await app.request(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "report.md", size_bytes: 100 }),
      });
      expect(response.status).toBe(status);
      expect(
        (await app.request(`${path}/${fileId}`, { method: "PUT" })).status,
      ).toBe(status === 201 ? 200 : 403);
      expect(
        (await app.request(`${path}/${fileId}`, { method: "DELETE" })).status,
      ).toBe(status === 201 ? 204 : 403);
      if (status === 201) {
        expect(response.headers.get("cache-control")).toBe("no-store");
        expect(create).toHaveBeenCalledOnce();
        expect(complete).toHaveBeenCalledOnce();
        expect(remove).toHaveBeenCalledOnce();
      } else {
        expect(create).not.toHaveBeenCalled();
        expect(complete).not.toHaveBeenCalled();
        expect(remove).not.toHaveBeenCalled();
      }
    },
  );
});
