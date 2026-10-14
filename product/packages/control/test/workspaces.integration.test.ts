import { EVALUATION_JUDGES } from "@gradiated/contracts";
import { createHash, randomUUID } from "node:crypto";

import { eq } from "drizzle-orm";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { apiKeys, workspaces } from "../src/db/schema/index.js";
import type { OrganizationRole } from "../src/organizations/service.js";
import {
  createWorkspaceApiKeyService,
  type WorkspaceApiKeyService,
} from "../src/workspaces/service.js";
import { seedMember, seedUser, seedWorkspace } from "./support/fixtures.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";

describe("workspaces and API keys", () => {
  let testDatabase: TestDatabase;
  let service: WorkspaceApiKeyService;

  beforeAll(async () => {
    testDatabase = await createTestDatabase();
    service = createWorkspaceApiKeyService(testDatabase.database);
  });

  afterAll(() => testDatabase.dispose());

  const membership = (
    role: OrganizationRole,
    status: "active" | "suspended" = "active",
  ) => seedMember(testDatabase.database, { role, organization: { status } });

  const archive = (workspaceId: string) =>
    testDatabase.database
      .update(workspaces)
      .set({ archivedAt: new Date() })
      .where(eq(workspaces.id, workspaceId));

  const storedKey = async (apiKeyId: string) => {
    const [row] = await testDatabase.database
      .select()
      .from(apiKeys)
      .where(eq(apiKeys.id, apiKeyId));

    return row;
  };

  it.each([
    ...EVALUATION_JUDGES,
    "openai/gpt-4.1-mini",
    "anthropic/claude-haiku-4-5",
  ])("persists catalog judge %s", async (judge) => {
    const { userId, workspaceId } = await membership("owner");
    const updated = await service.updateWorkspace(userId, workspaceId, {
      default_judge_model: judge,
    });
    expect(updated.defaultJudgeModel).toBe(judge);
  });

  it("renames the selected workspace without changing its capture or judge settings", async () => {
    const { userId, workspaceId, organizationId } = await membership("owner");
    const before = (
      await service.listWorkspaces(userId, organizationId, false)
    ).find((row) => row.id === workspaceId)!;
    const updated = await service.updateWorkspace(userId, workspaceId, {
      name: "  Production  ",
    });
    expect(updated.name).toBe("Production");
    expect(updated.traceCaptureEnabled).toBe(before.traceCaptureEnabled);
    expect(updated.traceRetentionDays).toBe(before.traceRetentionDays);
    expect(updated.defaultJudgeModel).toBe(before.defaultJudgeModel);
    expect(
      (await service.listWorkspaces(userId, organizationId, false)).find(
        (row) => row.id === workspaceId,
      )?.name,
    ).toBe("Production");
  });
  it.each([false, true])(
    "rejects duplicate workspace names even when archived=%s",
    async (archived) => {
      const { userId, workspaceId, organizationId } = await membership("owner");
      const original = (
        await service.listWorkspaces(userId, organizationId, false)
      ).find((row) => row.id === workspaceId)!;
      const duplicate = await service.createWorkspace(userId, organizationId, {
        name: "Research",
      });
      if (archived) await archive(duplicate.id);
      await expect(
        service.updateWorkspace(userId, workspaceId, { name: "rESEARCH" }),
      ).rejects.toMatchObject({
        code: "conflict",
        message: "A workspace with this name already exists.",
      });
      expect(
        (await service.listWorkspaces(userId, organizationId, false)).find(
          (row) => row.id === workspaceId,
        )?.name,
      ).toBe(original.name);
    },
  );
  it("allows changing only the case of the current workspace name", async () => {
    const { userId, workspaceId, organizationId } = await membership("owner");
    const original = (
      await service.listWorkspaces(userId, organizationId, false)
    ).find((row) => row.id === workspaceId)!;
    const updated = await service.updateWorkspace(userId, workspaceId, {
      name: original.name.toUpperCase(),
    });
    expect(updated.name).toBe(original.name.toUpperCase());
  });
  it("prevents ordinary members from renaming a workspace", async () => {
    const { userId, workspaceId } = await membership("member");
    await expect(
      service.updateWorkspace(userId, workspaceId, { name: "Denied" }),
    ).rejects.toMatchObject({ code: "forbidden" });
  });

  describe("createWorkspace", () => {
    it.each<OrganizationRole>(["owner", "admin"])(
      "lets an %s create a workspace",
      async (role) => {
        const { userId, organizationId } = await membership(role);

        const workspace = await service.createWorkspace(
          userId,
          organizationId,
          { name: "Research" },
        );

        expect(workspace).toMatchObject({
          organizationId,
          name: "Research",
          traceCaptureEnabled: true,
          traceRetentionDays: 180,
          defaultJudgeModel: "openai/gpt-6.1-sol",
          isDefault: false,
          archivedAt: null,
        });
      },
    );

    it.each<OrganizationRole>(["billing", "member"])(
      "forbids a %s",
      async (role) => {
        const { userId, organizationId } = await membership(role);

        await expect(
          service.createWorkspace(userId, organizationId, { name: "Denied" }),
        ).rejects.toMatchObject({ code: "forbidden" });
      },
    );

    it("forbids an owner of a suspended organization", async () => {
      const { userId, organizationId } = await membership("owner", "suspended");

      await expect(
        service.createWorkspace(userId, organizationId, { name: "Denied" }),
      ).rejects.toMatchObject({ code: "forbidden" });
    });

    it("hides the organization from a non-member", async () => {
      const { organizationId } = await membership("owner");
      const outsider = await seedUser(testDatabase.database);

      await expect(
        service.createWorkspace(outsider, organizationId, { name: "Denied" }),
      ).rejects.toMatchObject({ code: "not_found" });
    });
  });

  describe("listWorkspaces", () => {
    it("hides archived workspaces unless they are requested", async () => {
      const { userId, organizationId, workspaceId } =
        await membership("member");
      const archived = await seedWorkspace(testDatabase.database, {
        organizationId,
        archived: true,
      });

      const active = await service.listWorkspaces(
        userId,
        organizationId,
        false,
      );
      const all = await service.listWorkspaces(userId, organizationId, true);

      expect(active.map(({ id }) => id)).toEqual([workspaceId]);
      expect(all.map(({ id }) => id).sort()).toEqual(
        [workspaceId, archived].sort(),
      );
    });

    it("returns nothing to a non-member", async () => {
      const { organizationId } = await membership("owner");
      const outsider = await seedUser(testDatabase.database);

      expect(
        await service.listWorkspaces(outsider, organizationId, true),
      ).toEqual([]);
    });
  });

  describe("listApiKeys", () => {
    it("lists the workspace keys without their digests", async () => {
      const { userId, organizationId, workspaceId } = await membership("owner");
      const otherWorkspace = await seedWorkspace(testDatabase.database, {
        organizationId,
      });
      const { apiKey } = await service.createApiKey(userId, workspaceId, {
        name: "Listed",
        expiresAt: null,
      });
      await service.createApiKey(userId, otherWorkspace, {
        name: "Elsewhere",
        expiresAt: null,
      });

      const keys = await service.listApiKeys(userId, workspaceId);

      expect(keys).toEqual([apiKey]);
      expect(keys[0]).not.toHaveProperty("digest");
    });

    it("hides the workspace from a non-member", async () => {
      const { organizationId, workspaceId } = await membership("owner");
      const outsider = await seedUser(testDatabase.database);

      await expect(
        service.listApiKeys(outsider, workspaceId),
      ).rejects.toMatchObject({ code: "not_found" });
    });
  });

  describe("API-key management access", () => {
    const manage = (
      userId: string,
      organizationId: string,
      workspaceId: string,
    ) => [
      () =>
        service.createApiKey(userId, workspaceId, {
          name: "Denied",
          expiresAt: null,
        }),
      () => service.revokeApiKey(userId, workspaceId, randomUUID()),
    ];

    it.each<OrganizationRole>(["billing", "member"])(
      "forbids a %s",
      async (role) => {
        const { userId, organizationId, workspaceId } = await membership(role);

        for (const action of manage(userId, organizationId, workspaceId)) {
          await expect(action()).rejects.toMatchObject({ code: "forbidden" });
        }
      },
    );

    it("hides the workspace from a non-member", async () => {
      const { organizationId, workspaceId } = await membership("owner");
      const outsider = await seedUser(testDatabase.database);

      for (const action of manage(outsider, organizationId, workspaceId)) {
        await expect(action()).rejects.toMatchObject({ code: "not_found" });
      }
    });
  });

  describe("createApiKey", () => {
    it("stores only the digest of a well-formed secret", async () => {
      const { userId, organizationId, workspaceId } = await membership("admin");

      const { apiKey, secret } = await service.createApiKey(
        userId,
        workspaceId,
        { name: "CI", expiresAt: null },
      );
      const stored = await storedKey(apiKey.id);

      expect(secret).toMatch(/^grad_[A-Za-z0-9_-]{43}$/);
      expect(stored?.digest).toEqual(
        createHash("sha256").update(secret).digest(),
      );
      expect(Object.values(stored ?? {})).not.toContain(secret);
      expect(apiKey).toMatchObject({
        organizationId,
        workspaceId,
        createdBy: userId,
        revokedAt: null,
      });
    });

    it("rejects an expiry in the past", async () => {
      const { userId, organizationId, workspaceId } = await membership("owner");

      await expect(
        service.createApiKey(userId, workspaceId, {
          name: "Expired",
          expiresAt: new Date(Date.now() - 1_000),
        }),
      ).rejects.toMatchObject({ code: "forbidden" });
    });

    it("forbids keys in an archived workspace", async () => {
      const { userId, organizationId, workspaceId } = await membership("owner");
      await archive(workspaceId);

      await expect(
        service.createApiKey(userId, workspaceId, {
          name: "Archived",
          expiresAt: null,
        }),
      ).rejects.toMatchObject({ code: "forbidden" });
    });
  });

  describe("revokeApiKey", () => {
    const createKey = async () => {
      const access = await membership("owner");
      const { apiKey } = await service.createApiKey(
        access.userId,
        access.workspaceId,
        { name: "Revocable", expiresAt: null },
      );

      return { ...access, apiKeyId: apiKey.id };
    };

    it("keeps the first revocation time", async () => {
      const { userId, organizationId, workspaceId, apiKeyId } =
        await createKey();

      await service.revokeApiKey(userId, workspaceId, apiKeyId);
      const firstRevokedAt = (await storedKey(apiKeyId))?.revokedAt;
      await service.revokeApiKey(userId, workspaceId, apiKeyId);

      expect(firstRevokedAt).toBeInstanceOf(Date);
      expect((await storedKey(apiKeyId))?.revokedAt).toEqual(firstRevokedAt);
    });

    it("does not find a key from another workspace", async () => {
      const { userId, organizationId, apiKeyId } = await createKey();
      const otherWorkspace = await seedWorkspace(testDatabase.database, {
        organizationId,
      });

      await expect(
        service.revokeApiKey(userId, otherWorkspace, apiKeyId),
      ).rejects.toMatchObject({ code: "not_found" });
      await expect(
        service.revokeApiKey(userId, otherWorkspace, randomUUID()),
      ).rejects.toMatchObject({ code: "not_found" });
    });

    it("forbids revocation in an archived workspace", async () => {
      const { userId, organizationId, workspaceId, apiKeyId } =
        await createKey();
      await archive(workspaceId);

      await expect(
        service.revokeApiKey(userId, workspaceId, apiKeyId),
      ).rejects.toMatchObject({ code: "forbidden" });
      expect((await storedKey(apiKeyId))?.revokedAt).toBeNull();
    });
  });
});
