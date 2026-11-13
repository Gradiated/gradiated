import { EVALUATION_JUDGES } from "@gradiated/contracts";
import { createHash, randomUUID } from "node:crypto";

import { eq } from "drizzle-orm";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import {
  apiKeys,
  oauthAccessTokens,
  oauthClients,
  organizationMembers,
  sessions,
  workspaces,
} from "../src/db/schema/index.js";
import type { OrganizationRole } from "../src/organizations/service.js";
import {
  OAUTH_ACCESS_TOKEN_PREFIX,
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
    const { userId, workspaceId } = await membership("admin");
    const updated = await service.updateWorkspace(userId, workspaceId, {
      default_judge_model: judge,
    });
    expect(updated.defaultJudgeModel).toBe(judge);
  });

  it("renames the selected workspace without changing its capture or judge settings", async () => {
    const { userId, workspaceId, organizationId } = await membership("admin");
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
      const { userId, workspaceId, organizationId } = await membership("admin");
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
    const { userId, workspaceId, organizationId } = await membership("admin");
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
    it.each<OrganizationRole>(["admin"])(
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

    it.each<OrganizationRole>(["member"])("forbids a %s", async (role) => {
      const { userId, organizationId } = await membership(role);

      await expect(
        service.createWorkspace(userId, organizationId, { name: "Denied" }),
      ).rejects.toMatchObject({ code: "forbidden" });
    });

    it("forbids an owner of a suspended organization", async () => {
      const { userId, organizationId } = await membership("admin", "suspended");

      await expect(
        service.createWorkspace(userId, organizationId, { name: "Denied" }),
      ).rejects.toMatchObject({ code: "forbidden" });
    });

    it("hides the organization from a non-member", async () => {
      const { organizationId } = await membership("admin");
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
      const { organizationId } = await membership("admin");
      const outsider = await seedUser(testDatabase.database);

      expect(
        await service.listWorkspaces(outsider, organizationId, true),
      ).toEqual([]);
    });
  });

  describe("listApiKeys", () => {
    it("lists the workspace keys without their digests", async () => {
      const { userId, organizationId, workspaceId } = await membership("admin");
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
      const { organizationId, workspaceId } = await membership("admin");
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

    it("lets members create keys and revoke only their own", async () => {
      const admin = await membership("admin");
      const memberId = await seedUser(testDatabase.database);
      await testDatabase.database.insert(organizationMembers).values({
        organizationId: admin.organizationId,
        userId: memberId,
        role: "member",
        status: "active",
      });
      const adminKey = await service.createApiKey(
        admin.userId,
        admin.workspaceId,
        { name: "Admin", expiresAt: null },
      );

      const memberKey = await service.createApiKey(
        memberId,
        admin.workspaceId,
        { name: "Mine", expiresAt: null },
      );
      await service.revokeApiKey(
        memberId,
        admin.workspaceId,
        memberKey.apiKey.id,
      );

      expect((await storedKey(memberKey.apiKey.id))?.revokedAt).not.toBeNull();
      await expect(
        service.revokeApiKey(memberId, admin.workspaceId, adminKey.apiKey.id),
      ).rejects.toMatchObject({ code: "forbidden" });
    });

    it("hides the workspace from a non-member", async () => {
      const { organizationId, workspaceId } = await membership("admin");
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
      const { userId, organizationId, workspaceId } = await membership("admin");

      await expect(
        service.createApiKey(userId, workspaceId, {
          name: "Expired",
          expiresAt: new Date(Date.now() - 1_000),
        }),
      ).rejects.toMatchObject({ code: "forbidden" });
    });

    it("forbids keys in an archived workspace", async () => {
      const { userId, organizationId, workspaceId } = await membership("admin");
      await archive(workspaceId);

      await expect(
        service.createApiKey(userId, workspaceId, {
          name: "Archived",
          expiresAt: null,
        }),
      ).rejects.toMatchObject({ code: "forbidden" });
    });
  });

  describe("createPlaygroundCredential", () => {
    it("creates an hour-long key that members cannot see", async () => {
      const admin = await membership("admin");
      const memberId = await seedUser(testDatabase.database);
      await testDatabase.database.insert(organizationMembers).values({
        organizationId: admin.organizationId,
        userId: memberId,
        role: "member",
        status: "active",
      });
      const before = Date.now();

      const { apiKeyId, secret, expiresAt } =
        await service.createPlaygroundCredential(memberId, admin.workspaceId);

      expect(secret).toMatch(/^grad_/);
      expect(await storedKey(apiKeyId)).toMatchObject({
        name: "Playground",
        hidden: true,
        createdBy: memberId,
        expiresAt,
        digest: createHash("sha256").update(secret).digest(),
      });
      expect(expiresAt.getTime()).toBeGreaterThanOrEqual(
        before + 60 * 60 * 1000,
      );
      expect(expiresAt.getTime()).toBeLessThanOrEqual(
        Date.now() + 60 * 60 * 1000,
      );
      await expect(
        service.listApiKeys(admin.userId, admin.workspaceId),
      ).resolves.toEqual([]);
    });

    it("rotates one key per member and workspace", async () => {
      const { userId, organizationId, workspaceId } = await membership("admin");
      const otherWorkspace = await seedWorkspace(testDatabase.database, {
        organizationId,
      });

      const first = await service.createPlaygroundCredential(
        userId,
        workspaceId,
      );
      const second = await service.createPlaygroundCredential(
        userId,
        workspaceId,
      );
      const elsewhere = await service.createPlaygroundCredential(
        userId,
        otherWorkspace,
      );

      expect(second.apiKeyId).toBe(first.apiKeyId);
      expect(second.secret).not.toBe(first.secret);
      expect(elsewhere.apiKeyId).not.toBe(first.apiKeyId);
      expect(await storedKey(first.apiKeyId)).toMatchObject({
        digest: createHash("sha256").update(second.secret).digest(),
        expiresAt: second.expiresAt,
      });
      const hidden = await testDatabase.database
        .select()
        .from(apiKeys)
        .where(eq(apiKeys.workspaceId, workspaceId));
      expect(hidden).toHaveLength(1);
    });

    it("forbids credentials in an archived workspace", async () => {
      const { userId, workspaceId } = await membership("admin");
      await archive(workspaceId);

      await expect(
        service.createPlaygroundCredential(userId, workspaceId),
      ).rejects.toMatchObject({
        code: "forbidden",
        message: expect.stringMatching(/^The playground is unavailable/),
      });
    });
  });

  describe("revokeApiKey", () => {
    const createKey = async () => {
      const access = await membership("admin");
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

  describe("authenticateCredential", () => {
    it("finds the creator and workspace of an active key", async () => {
      const { userId, organizationId, workspaceId } =
        await membership("member");
      const { apiKey, secret } = await service.createApiKey(
        userId,
        workspaceId,
        { name: "MCP", expiresAt: null },
      );

      await expect(
        service.authenticateCredential(secret),
      ).resolves.toMatchObject({
        credential: "api_key",
        credentialId: apiKey.id,
        organizationId,
        workspaceId,
        user: { id: userId },
      });
    });

    it("rejects revoked, expired and unknown keys", async () => {
      const { userId, workspaceId } = await membership("admin");
      const revoked = await service.createApiKey(userId, workspaceId, {
        name: "Revoked",
        expiresAt: null,
      });
      await service.revokeApiKey(userId, workspaceId, revoked.apiKey.id);
      const expired = await service.createApiKey(userId, workspaceId, {
        name: "Expired",
        expiresAt: new Date(Date.now() + 60_000),
      });
      await testDatabase.database
        .update(apiKeys)
        .set({
          createdAt: new Date(Date.now() - 120_000),
          expiresAt: new Date(Date.now() - 1_000),
        })
        .where(eq(apiKeys.id, expired.apiKey.id));

      for (const secret of [
        revoked.secret,
        expired.secret,
        `grad_${"x".repeat(43)}`,
        "other",
      ])
        await expect(
          service.authenticateCredential(secret),
        ).resolves.toBeUndefined();
    });

    const oauthToken = async (
      userId: string,
      referenceId: string | null,
      overrides: Partial<typeof oauthAccessTokens.$inferInsert> = {},
    ) => {
      const clientId = randomUUID();
      const token = randomUUID().replaceAll("-", "");
      await testDatabase.database.insert(oauthClients).values({
        id: randomUUID(),
        clientId,
        redirectUris: ["http://localhost/cb"],
      });
      const [row] = await testDatabase.database
        .insert(oauthAccessTokens)
        .values({
          id: randomUUID(),
          token: createHash("sha256").update(token).digest("base64url"),
          clientId,
          userId,
          referenceId,
          scopes: ["mcp", "offline_access"],
          createdAt: new Date(),
          expiresAt: new Date(Date.now() + 60_000),
          ...overrides,
        })
        .returning({ id: oauthAccessTokens.id });

      return { secret: `${OAUTH_ACCESS_TOKEN_PREFIX}${token}`, id: row!.id };
    };

    it("finds the user and consented workspace of an OAuth token", async () => {
      const { userId, organizationId, workspaceId } =
        await membership("member");
      const { secret, id } = await oauthToken(userId, workspaceId);

      await expect(
        service.authenticateCredential(secret),
      ).resolves.toMatchObject({
        credential: "oauth_token",
        credentialId: id,
        organizationId,
        workspaceId,
        user: { id: userId },
      });
    });

    it("rejects OAuth tokens that are expired, revoked, unscoped or without a workspace", async () => {
      const { userId, workspaceId } = await membership("member");
      const tokens = await Promise.all([
        oauthToken(userId, workspaceId, {
          createdAt: new Date(Date.now() - 120_000),
          expiresAt: new Date(Date.now() - 1_000),
        }),
        oauthToken(userId, workspaceId, { revoked: new Date() }),
        oauthToken(userId, workspaceId, { scopes: ["offline_access"] }),
        oauthToken(userId, null),
        oauthToken(userId, randomUUID()),
      ]);

      for (const { secret } of tokens)
        await expect(
          service.authenticateCredential(secret),
        ).resolves.toBeUndefined();
    });

    it("describes a credential with its workspace and organization names", async () => {
      const { userId, workspaceId } = await membership("member");
      const { secret } = await oauthToken(userId, workspaceId);

      await expect(service.describeCredential(secret)).resolves.toMatchObject({
        credential: "oauth_token",
        workspaceId,
        workspaceName: expect.any(String),
        organizationName: expect.any(String),
      });
      await expect(
        service.describeCredential(`grad_${"x".repeat(43)}`),
      ).resolves.toBeUndefined();
    });

    it("gives an OAuth token a hidden inference key beside the playground key", async () => {
      const { userId, workspaceId } = await membership("member");
      const { secret } = await oauthToken(userId, workspaceId);
      const playground = await service.createPlaygroundCredential(
        userId,
        workspaceId,
      );

      const first = await service.createOAuthInferenceCredential(secret);
      const second = await service.createOAuthInferenceCredential(secret);

      expect(first).toBeDefined();
      expect(second?.apiKeyId).toBe(first?.apiKeyId);
      expect(second?.apiKeyId).not.toBe(playground.apiKeyId);
      await expect(
        service.authenticateCredential(second!.secret),
      ).resolves.toMatchObject({ workspaceId, user: { id: userId } });
      // Minting rotates the key, and leaves the playground key working.
      await expect(
        service.authenticateCredential(first!.secret),
      ).resolves.toBeUndefined();
      await expect(
        service.authenticateCredential(playground.secret),
      ).resolves.toBeDefined();
      await expect(
        service.listApiKeys(userId, workspaceId),
      ).resolves.toHaveLength(0);
    });

    it("gives API keys no inference key, since they call inference themselves", async () => {
      const { userId, workspaceId } = await membership("member");
      const { secret } = await service.createApiKey(userId, workspaceId, {
        name: "Key",
        expiresAt: null,
      });

      await expect(
        service.createOAuthInferenceCredential(secret),
      ).resolves.toBeUndefined();
    });
  });

  describe("selectOAuthWorkspace", () => {
    const session = async (userId: string) => {
      const id = randomUUID();
      await testDatabase.database.insert(sessions).values({
        id,
        userId,
        token: randomUUID(),
        expiresAt: new Date(Date.now() + 60_000),
      });

      return id;
    };

    it("records a workspace the member can use on their session", async () => {
      const { userId, workspaceId } = await membership("member");
      const sessionId = await session(userId);

      await service.selectOAuthWorkspace(userId, sessionId, workspaceId);

      const [row] = await testDatabase.database
        .select({ workspaceId: sessions.oauthWorkspaceId })
        .from(sessions)
        .where(eq(sessions.id, sessionId));
      expect(row?.workspaceId).toBe(workspaceId);
    });

    it("refuses another member's workspace, an archived one and another user's session", async () => {
      const { userId, workspaceId } = await membership("member");
      const other = await membership("admin");
      const sessionId = await session(userId);
      const otherSession = await session(other.userId);

      await expect(
        service.selectOAuthWorkspace(userId, sessionId, other.workspaceId),
      ).rejects.toMatchObject({ code: "not_found" });
      await expect(
        service.selectOAuthWorkspace(userId, otherSession, workspaceId),
      ).rejects.toMatchObject({ code: "not_found" });
      await archive(workspaceId);
      await expect(
        service.selectOAuthWorkspace(userId, sessionId, workspaceId),
      ).rejects.toMatchObject({ code: "forbidden" });
    });
  });
});
