import { v7 as uuidv7 } from "uuid";

import {
  ContactChannelSchema,
  UpdateOrganizationSchema,
  type ContactChannel,
  type OrganizationNda,
  type OrganizationOnboarding,
  type UpdateOrganization,
} from "@gradiated/contracts";
import { companyEmailDomain } from "./email-domains.js";
import { isTakenOrganizationSlug, requireChangeableSlug } from "./slugs.js";
import { createOrganizationStore } from "./store.js";
import { requireRow } from "../require-row.js";
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
  slug: string;
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
  slug: string;
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
    page?: { search: string; limit: number; offset: number },
  ): Promise<UserOrganization[]>;
  createForUser(
    userId: string,
    name: string,
    slug?: string,
  ): Promise<CreatedOrganization>;
  ensurePersonalForUser(
    userId: string,
    name?: string | undefined,
  ): Promise<UserOrganization>;
  ensureForNewUser(user: SignupUser): Promise<UserOrganization>;
  getOnboarding(
    userId: string,
    organizationId: string,
  ): Promise<OrganizationOnboarding>;
  recordOnboardingNda(
    userId: string,
    organizationId: string,
    nda: OrganizationNda,
  ): Promise<OrganizationOnboarding>;
  submitOnboarding(
    userId: string,
    organizationId: string,
    contactChannel: ContactChannel,
  ): Promise<{ submitted: boolean; onboarding: OrganizationOnboarding }>;
  /** Reserves the submission for two minutes; returns the claim or null. */
  claimOnboardingSubmission(
    userId: string,
    organizationId: string,
  ): Promise<string | null>;
  releaseOnboardingSubmission(
    userId: string,
    organizationId: string,
    claimedAt: string,
  ): Promise<void>;
  /** Local test mode only; never wired in production. */
  resetOnboardingSubmission(
    userId: string,
    organizationId: string,
  ): Promise<void>;
}

const SUBMISSION_CLAIM_MS = 2 * 60 * 1000;

const organizationNotFound = () =>
  new ControlServiceError("not_found", "The organization was not found.");

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
    slug?: string | undefined;
  }): Promise<CreatedOrganization> => {
    const organizationId = uuidv7();
    const now = new Date();
    const defaultWorkspace = defaultWorkspaceValues(organizationId, now);

    const slug = await database
      .transaction(async (transaction) => {
        if (input.slug)
          await requireChangeableSlug(transaction, organizationId, input.slug);
        const created = await transaction
          .insert(organizations)
          .values({
            id: organizationId,
            kind: "customer",
            name: input.name,
            slug: input.slug,
            status: "active",
            onboardedAt: input.onboarded ? now : null,
            createdAt: now,
            updatedAt: now,
          })
          .returning({ slug: organizations.slug });
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

        if (input.signupCredit)
          await postBalanceTransaction(transaction, {
            organizationId,
            type: "credit",
            amount: SIGNUP_CREDIT_NANO_USD,
            sourceType: "operator",
            sourceId: `signup-grant:${organizationId}`,
            createdBy: input.userId,
          });

        // The database assigns a random placeholder until onboarding.
        return requireRow(created, "The organization was not created.").slug;
      })
      .catch((error: unknown) => {
        if (isTakenOrganizationSlug(error))
          throw new ControlServiceError(
            "conflict",
            "Another organization already uses this slug.",
            error,
          );
        throw error;
      });

    return {
      id: organizationId,
      kind: "customer",
      name: input.name,
      slug,
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
    page?: { search: string; limit: number; offset: number },
  ): Promise<UserOrganization[]> =>
    records.listForUser(userId, organizationId, page);

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
      slug: created.slug,
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

    async createForUser(userId, name, slug) {
      return createOrganization({
        slug,
        signupCredit: false,
        onboarded: true,
        userId,
        name,
      });
    },

    ensurePersonalForUser,

    async getOnboarding(userId, organizationId) {
      await requireOrganizationAdmin(database, { userId, organizationId });

      const onboarding = await records.readOnboarding(organizationId);
      if (!onboarding) throw organizationNotFound();

      return onboarding;
    },

    async recordOnboardingNda(userId, organizationId, nda) {
      await requireOrganizationAdmin(database, { userId, organizationId });

      const onboarding = await records.recordOnboardingNda(organizationId, nda);
      if (!onboarding) throw organizationNotFound();

      return onboarding;
    },

    async submitOnboarding(userId, organizationId, contactChannel) {
      await requireOrganizationAdmin(database, { userId, organizationId });

      const result = await records.submitOnboarding(organizationId, {
        submitted_at: new Date().toISOString(),
        submitted_by: userId,
        contact_channel: ContactChannelSchema.parse(contactChannel),
      });
      if (!result) throw organizationNotFound();

      return result;
    },

    async claimOnboardingSubmission(userId, organizationId) {
      await requireOrganizationAdmin(database, { userId, organizationId });

      const now = Date.now();
      const claimedAt = new Date(now).toISOString();
      const claimed = await records.claimOnboardingSubmission(
        organizationId,
        claimedAt,
        new Date(now - SUBMISSION_CLAIM_MS).toISOString(),
      );

      return claimed ? claimedAt : null;
    },

    async releaseOnboardingSubmission(userId, organizationId, claimedAt) {
      await requireOrganizationAdmin(database, { userId, organizationId });
      await records.releaseOnboardingSubmission(organizationId, claimedAt);
    },

    async resetOnboardingSubmission(userId, organizationId) {
      await requireOrganizationAdmin(database, { userId, organizationId });
      await records.resetOnboardingSubmission(organizationId);
    },

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
