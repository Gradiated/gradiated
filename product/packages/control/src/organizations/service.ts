import { and, asc, eq } from "drizzle-orm";
import { v7 as uuidv7 } from "uuid";

import { activeCustomerMember } from "../access.js";
import { postBalanceTransaction } from "../billing/ledger.js";
import type { ControlDatabase } from "../db/client.js";
import {
  billingAccounts,
  organizationMembers,
  organizations,
  workspaces,
  type OrganizationRole,
  type OrganizationStatus,
} from "../db/schema/index.js";

export type { OrganizationRole } from "../db/schema/index.js";

export interface UserOrganization {
  id: string;
  name: string;
  status: OrganizationStatus;
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

export const defaultWorkspaceValues = (organizationId: string, now: Date) => ({
  id: uuidv7(),
  organizationId,
  name: "Default",
  isDefault: true,
  createdAt: now,
  updatedAt: now,
});

export interface OrganizationService {
  listForUser(userId: string): Promise<UserOrganization[]>;
  createForUser(userId: string, name: string): Promise<CreatedOrganization>;
  ensurePersonalForUser(
    userId: string,
    name?: string | undefined,
  ): Promise<UserOrganization>;
}

export const createOrganizationService = (
  database: ControlDatabase,
): OrganizationService => {
  const createOrganization = async (input: {
    signupCredit: boolean;
    userId: string;
    name: string;
  }): Promise<CreatedOrganization> => {
    const organizationId = uuidv7();
    const now = new Date();
    const defaultWorkspace = defaultWorkspaceValues(organizationId, now);

    await database.transaction(async (transaction) => {
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
      await transaction.insert(workspaces).values(defaultWorkspace);
      await transaction.insert(billingAccounts).values({
        organizationId,
        mode: "prepaid",
        balance: 0n,
        createdAt: now,
        updatedAt: now,
      });

      if (!input.signupCredit) return;

      await postBalanceTransaction(transaction, {
        organizationId,
        type: "credit",
        amount: SIGNUP_CREDIT_NANO_USD,
        sourceType: "operator",
        sourceId: `signup-grant:${organizationId}`,
        createdBy: input.userId,
      });
    });

    return {
      id: organizationId,
      kind: "customer",
      name: input.name,
      status: "active",
      role: "owner",
      defaultWorkspaceId: defaultWorkspace.id,
      createdAt: now,
      updatedAt: now,
    };
  };

  const listForUser = async (userId: string): Promise<UserOrganization[]> =>
    database
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
      .where(activeCustomerMember({ userId }))
      .orderBy(asc(organizations.createdAt), asc(organizations.id));

  return {
    listForUser,

    async createForUser(userId, name) {
      return createOrganization({ signupCredit: false, userId, name });
    },

    async ensurePersonalForUser(userId, name = "Personal") {
      const [existing] = await listForUser(userId);
      if (existing) return existing;

      return createOrganization({ signupCredit: true, userId, name });
    },
  };
};
