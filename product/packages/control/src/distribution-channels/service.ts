import { createHash } from "node:crypto";

import { and, eq } from "drizzle-orm";
import { v7 as uuidv7 } from "uuid";

import type { ControlDatabase } from "../db/client.js";
import {
  apiKeys,
  billingAccounts,
  organizations,
  workspaces,
} from "../db/schema/index.js";
import type { WorkspaceRecord } from "../workspaces/service.js";

export interface ConfiguredDistributionChannel {
  organizationId: string;
  workspaceId: string;
  apiKeyId: string;
}

export async function configureOpenRouterDistributionChannel(
  database: ControlDatabase,
  rawApiKey: string,
): Promise<ConfiguredDistributionChannel> {
  const digest = createHash("sha256").update(rawApiKey).digest();
  const result = await database.transaction(async (transaction) => {
    const now = new Date();
    let [organization] = await transaction
      .select()
      .from(organizations)
      .where(
        and(
          eq(organizations.kind, "distribution_channel"),
          eq(organizations.name, "OpenRouter"),
        ),
      )
      .limit(1);

    if (!organization) {
      [organization] = await transaction
        .insert(organizations)
        .values({
          id: uuidv7(),
          kind: "distribution_channel",
          name: "OpenRouter",
          status: "active",
          createdAt: now,
          updatedAt: now,
        })
        .returning();
      if (!organization) {
        throw new Error("The OpenRouter organization was not created.");
      }
    } else if (organization.status !== "active") {
      [organization] = await transaction
        .update(organizations)
        .set({ status: "active", updatedAt: now })
        .where(eq(organizations.id, organization.id))
        .returning();
      if (!organization) {
        throw new Error("The OpenRouter organization was not updated.");
      }
    }

    let [workspace] = await transaction
      .select()
      .from(workspaces)
      .where(
        and(
          eq(workspaces.organizationId, organization.id),
          eq(workspaces.isDefault, true),
        ),
      )
      .limit(1);
    if (!workspace) {
      [workspace] = await transaction
        .insert(workspaces)
        .values({
          id: uuidv7(),
          organizationId: organization.id,
          name: "Default",
          isDefault: true,
          createdAt: now,
          updatedAt: now,
        })
        .returning();
      if (!workspace) {
        throw new Error("The OpenRouter workspace was not created.");
      }
    }

    await transaction
      .insert(billingAccounts)
      .values({
        organizationId: organization.id,
        mode: "invoiced",
        balance: 0n,
        createdAt: now,
        updatedAt: now,
      })
      .onConflictDoUpdate({
        target: billingAccounts.organizationId,
        set: { mode: "invoiced", updatedAt: now },
      });

    let [apiKey] = await transaction
      .select()
      .from(apiKeys)
      .where(eq(apiKeys.digest, digest))
      .limit(1);
    if (!apiKey) {
      [apiKey] = await transaction
        .insert(apiKeys)
        .values({
          id: uuidv7(),
          organizationId: organization.id,
          workspaceId: workspace.id,
          name: "OpenRouter provider",
          digest,
          createdBy: null,
          createdAt: now,
          updatedAt: now,
        })
        .returning();
      if (!apiKey) {
        throw new Error("The OpenRouter API key was not created.");
      }
    } else if (
      apiKey.organizationId !== organization.id ||
      apiKey.workspaceId !== workspace.id
    ) {
      throw new Error("The supplied API key belongs to another organization.");
    } else if (apiKey.revokedAt) {
      [apiKey] = await transaction
        .update(apiKeys)
        .set({
          revokedAt: null,
          updatedAt: now,
        })
        .where(eq(apiKeys.id, apiKey.id))
        .returning();
      if (!apiKey) {
        throw new Error("The OpenRouter API key was not updated.");
      }
    }

    const [billingAccount] = await transaction
      .select()
      .from(billingAccounts)
      .where(eq(billingAccounts.organizationId, organization.id))
      .limit(1);
    if (!billingAccount) {
      throw new Error("The OpenRouter billing account is missing.");
    }

    return { organization, workspace, apiKey, billingAccount };
  });

  return {
    organizationId: result.organization.id,
    workspaceId: result.workspace.id,
    apiKeyId: result.apiKey.id,
  };
}
