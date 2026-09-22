import { and, asc, eq } from "drizzle-orm";
import { v7 as uuidv7 } from "uuid";

import type { ControlDatabase } from "../db/client.js";
import {
  balanceTransactions,
  billingAccounts,
  organizationMembers,
  organizations,
  workspaces,
} from "../db/schema/index.js";
import {
  ControlServiceError,
  type WorkspaceRecord,
} from "../workspaces/service.js";

export type OrganizationRole = "owner" | "admin" | "billing" | "member";

export interface UserOrganization {
  id: string;
  name: string;
  status: "active" | "suspended";
  role: OrganizationRole;
  defaultWorkspaceId: string;
}

export interface CreatedOrganization {
  id: string;
  kind: "customer";
  name: string;
  status: "active";
  role: "owner";
  defaultWorkspaceId: string;
  createdAt: Date;
  updatedAt: Date;
}

export const SIGNUP_CREDIT_NANO_USD = 5_000_000_000n;
export const SIGNUP_CREDIT_SOURCE_TYPE = "operator";

export interface OrganizationService {
  listForUser(userId: string): Promise<UserOrganization[]>;
  createForUser(userId: string, name: string): Promise<CreatedOrganization>;
  ensurePersonalForUser(
    userId: string,
    name?: string | undefined,
  ): Promise<UserOrganization>;
}

export function createOrganizationService(
  database: ControlDatabase,
): OrganizationService {
  const service: OrganizationService = {
    async listForUser(userId) {
      const rows = await database
        .select({
          id: organizations.id,
          name: organizations.name,
          status: organizations.status,
          role: organizationMembers.role,
          defaultWorkspaceId: workspaces.id,
        })
        .from(organizationMembers)
        .innerJoin(
          organizations,
          eq(organizations.id, organizationMembers.organizationId),
        )
        .innerJoin(
          workspaces,
          and(
            eq(workspaces.organizationId, organizations.id),
            eq(workspaces.isDefault, true),
          ),
        )
        .where(
          and(
            eq(organizationMembers.userId, userId),
            eq(organizationMembers.status, "active"),
            eq(organizations.kind, "customer"),
          ),
        )
        .orderBy(asc(organizations.createdAt), asc(organizations.id));

      return rows.map((row) => ({
        ...row,
        status: row.status as UserOrganization["status"],
        role: row.role as OrganizationRole,
      }));
    },

    async createForUser(userId, name) {
      return createOrganization({ signupCredit: false, userId, name });
    },
    async ensurePersonalForUser(userId, name = "Personal") {
      const existing = await service.listForUser(userId);
      if (existing[0]) return existing[0];
      return createOrganization({ signupCredit: true, userId, name });
    },
  };
  return service;

  async function createOrganization(input: {
    signupCredit: boolean;
    userId: string;
    name: string;
  }): Promise<CreatedOrganization> {
    const organizationId = uuidv7();
    const workspaceId = uuidv7();
    const now = new Date();
    const signupCreditTransactionId = input.signupCredit ? uuidv7() : null;

    const creditBalanceAfter = await database.transaction(
      async (transaction) => {
        await transaction.insert(organizations).values({
          id: organizationId,
          kind: "customer",
          name: input.name,
          status: "active",
          createdAt: now,
          updatedAt: now,
        });
        await transaction.insert(organizationMembers).values({
          organizationId,
          userId: input.userId,
          role: "owner",
          status: "active",
          createdAt: now,
          updatedAt: now,
        });
        await transaction.insert(workspaces).values({
          id: workspaceId,
          organizationId,
          name: "Default",
          isDefault: true,
          createdAt: now,
          updatedAt: now,
        });
        await transaction.insert(billingAccounts).values({
          organizationId,
          mode: "prepaid",
          balance: 0n,
          createdAt: now,
          updatedAt: now,
        });
        if (!signupCreditTransactionId) {
          return 0n;
        }
        await transaction.insert(balanceTransactions).values({
          id: signupCreditTransactionId,
          organizationId,
          type: "credit",
          amount: SIGNUP_CREDIT_NANO_USD,
          balanceAfter: SIGNUP_CREDIT_NANO_USD,
          sourceType: SIGNUP_CREDIT_SOURCE_TYPE,
          sourceId: `signup-grant:${organizationId}`,
          createdBy: input.userId,
          createdAt: now,
        });
        await transaction
          .update(billingAccounts)
          .set({
            balance: SIGNUP_CREDIT_NANO_USD,
            updatedAt: now,
          })
          .where(eq(billingAccounts.organizationId, organizationId));
        return SIGNUP_CREDIT_NANO_USD;
      },
    );

    return {
      id: organizationId,
      kind: "customer",
      name: input.name,
      status: "active",
      role: "owner",
      defaultWorkspaceId: workspaceId,
      createdAt: now,
      updatedAt: now,
    };
  }
}
