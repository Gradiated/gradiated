import { v7 as uuidv7 } from "uuid";

import {
  UpdateOrganizationSchema,
  type UpdateOrganization,
} from "@gradiated/contracts";
import { companyEmailDomain } from "./email-domains.js";
import { createOrganizationStore } from "./store.js";
import { createMemberStore } from "../members/store.js";
import { ControlServiceError } from "../errors.js";
import { requireOrganizationAdmin } from "../access.js";
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
  autoJoinDomain: string | null;
  onboardingCompleted: boolean;
}

export interface SignupUser {
  id: string;
  email: string;
  emailVerified: boolean;
}

export interface CreatedOrganization {
  id: string;
  kind: "customer";
  name: string;
  status: "active";
  role: "admin";
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
  updateForUser(
    userId: string,
    organizationId: string,
    input: UpdateOrganization,
  ): Promise<UserOrganization>;
  listForUser(
    userId: string,
    organizationId?: string,
  ): Promise<UserOrganization[]>;
  createForUser(userId: string, name: string): Promise<CreatedOrganization>;
  ensurePersonalForUser(
    userId: string,
    name?: string | undefined,
  ): Promise<UserOrganization>;
  ensureForNewUser(user: SignupUser): Promise<UserOrganization>;
}

export const createOrganizationService = (
  database: ControlDatabase,
): OrganizationService => {
  const records = createOrganizationStore(database);
  const members = createMemberStore(database);
  const createOrganization = async (input: {
    signupCredit: boolean;
    onboarded: boolean;
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
        onboardedAt: input.onboarded ? now : null,
        createdAt: now,
        updatedAt: now,
      });
      await transaction.insert(organizationMembers).values({
        organizationId,
        userId: input.userId,
        role: "admin",
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
      role: "admin",
      defaultWorkspaceId: defaultWorkspace.id,
      createdAt: now,
      updatedAt: now,
    };
  };

  const listForUser = async (
    userId: string,
    organizationId?: string,
  ): Promise<UserOrganization[]> => records.listForUser(userId, organizationId);

  const ensurePersonalForUser = async (userId: string, name = "Personal") => {
    const [existing] = await listForUser(userId);
    if (existing) return existing;

    const created = await createOrganization({
      signupCredit: true,
      onboarded: false,
      userId,
      name,
    });

    return {
      id: created.id,
      name: created.name,
      status: created.status,
      role: created.role,
      defaultWorkspaceId: created.defaultWorkspaceId,
      autoJoinDomain: null,
      onboardingCompleted: false,
    };
  };

  const acceptPendingInvitations = async (user: SignupUser) => {
    if (!user.emailVerified) return undefined;

    const now = new Date();
    const joined: string[] = [];
    for (const id of await members.pendingInvitationIdsForEmail(
      user.email,
      now,
    )) {
      const accepted = await members.accept(id, user.id, now);
      if (accepted?.joined) joined.push(accepted.organizationId);
    }

    return joined[0];
  };

  const joinByEmailDomain = async (user: SignupUser) => {
    const domain = companyEmailDomain(user);

    return domain ? records.joinByDomain(user.id, domain) : undefined;
  };

  return {
    listForUser,
    async updateForUser(userId, organizationId, input) {
      await requireOrganizationAdmin(database, { userId, organizationId });

      const update = UpdateOrganizationSchema.parse(input);
      if (update.auto_join_domain) {
        const user = await records.findUser(userId);
        if (!user || companyEmailDomain(user) !== update.auto_join_domain)
          throw new ControlServiceError(
            "forbidden",
            "Automatic joining can only use your own verified company email domain.",
          );
      }

      const organization = await records.update(userId, organizationId, update);
      if (!organization)
        throw new ControlServiceError(
          "not_found",
          "The organization was not found.",
        );

      return organization;
    },

    async createForUser(userId, name) {
      return createOrganization({
        signupCredit: false,
        onboarded: true,
        userId,
        name,
      });
    },

    ensurePersonalForUser,

    async ensureForNewUser(user) {
      const joinedId =
        (await acceptPendingInvitations(user)) ??
        (await joinByEmailDomain(user));
      if (!joinedId) return ensurePersonalForUser(user.id);

      const [joined] = await records.listForUser(user.id, joinedId);

      return joined ?? ensurePersonalForUser(user.id);
    },
  };
};
