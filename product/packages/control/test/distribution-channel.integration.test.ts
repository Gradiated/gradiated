import { createHash } from "node:crypto";

import { eq } from "drizzle-orm";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  apiKeys,
  billingAccounts,
  organizations,
  workspaces,
} from "../src/db/schema/index.js";
import { configureOpenRouterDistributionChannel } from "../src/distribution-channels/service.js";
import { createWorkspaceApiKeyService } from "../src/workspaces/service.js";
import {
  seedOrganization,
  seedUser,
  seedWorkspace,
} from "./support/fixtures.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";

const rawKey = "sk-or-provider-key";

describe("OpenRouter distribution channel", () => {
  let testDatabase: TestDatabase;

  beforeEach(async () => {
    testDatabase = await createTestDatabase();
  });

  afterEach(() => testDatabase.dispose());

  const configure = (key = rawKey) =>
    configureOpenRouterDistributionChannel(testDatabase.database, key);

  const snapshot = async () => {
    const { database } = testDatabase;

    return {
      organizations: await database.select().from(organizations),
      workspaces: await database.select().from(workspaces),
      billingAccounts: await database.select().from(billingAccounts),
      apiKeys: await database.select().from(apiKeys),
    };
  };

  it("creates the organization, workspace, invoiced account and key", async () => {
    const channel = await configure();
    const state = await snapshot();

    expect(state.organizations).toMatchObject([
      {
        id: channel.organizationId,
        kind: "distribution_channel",
        name: "OpenRouter",
        status: "active",
      },
    ]);
    expect(state.workspaces).toMatchObject([
      { id: channel.workspaceId, isDefault: true },
    ]);
    expect(state.billingAccounts).toMatchObject([
      { organizationId: channel.organizationId, mode: "invoiced" },
    ]);
    expect(state.apiKeys).toMatchObject([
      {
        id: channel.apiKeyId,
        digest: createHash("sha256").update(rawKey).digest(),
        revokedAt: null,
      },
    ]);
  });

  it("returns the same records when it runs again", async () => {
    const first = await configure();

    expect(await configure()).toEqual(first);
  });

  it("reactivates a revoked key and a suspended organization", async () => {
    const first = await configure();
    await testDatabase.database
      .update(apiKeys)
      .set({ revokedAt: new Date() })
      .where(eq(apiKeys.id, first.apiKeyId));
    await testDatabase.database
      .update(organizations)
      .set({ status: "suspended" })
      .where(eq(organizations.id, first.organizationId));

    expect(await configure()).toEqual(first);

    const state = await snapshot();
    expect(state.apiKeys).toMatchObject([{ revokedAt: null }]);
    expect(state.organizations).toMatchObject([{ status: "active" }]);
  });

  it("refuses a key that belongs to a customer organization", async () => {
    const { database } = testDatabase;
    const userId = await seedUser(database);
    const organizationId = await seedOrganization(database, {
      members: [{ userId, role: "owner" }],
    });
    const workspaceId = await seedWorkspace(database, { organizationId });
    const { secret } = await createWorkspaceApiKeyService(
      database,
    ).createApiKey(userId, organizationId, workspaceId, {
      name: "Customer",
      expiresAt: null,
    });
    const before = await snapshot();

    await expect(configure(secret)).rejects.toThrow(
      "The supplied API key belongs to another organization.",
    );

    expect(await snapshot()).toEqual(before);
  });
});
