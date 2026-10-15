import {
  CreateInvitationsSchema,
  UpdateMemberSchema,
  type CreateInvitations,
  type InvitationPreview,
  type UpdateMember,
} from "@gradiated/contracts";

import { requireMembership, requireOrganizationAdmin } from "../access.js";
import type { ControlDatabase } from "../db/client.js";
import { ControlServiceError } from "../errors.js";
import { randomToken, sha256Digest } from "../secrets.js";
import {
  createMemberStore,
  type InvitationRecord,
  type MemberRecord,
} from "./store.js";

export type { InvitationRecord, MemberRecord } from "./store.js";

export interface IssuedInvitation {
  invitation: InvitationRecord;
  organizationName: string;
  token: string;
}

export interface InvitationAcceptor {
  id: string;
  email: string;
  emailVerified: boolean;
}

export interface MemberService {
  listMembers(userId: string, organizationId: string): Promise<MemberRecord[]>;
  updateMember(
    userId: string,
    organizationId: string,
    memberId: string,
    input: UpdateMember,
  ): Promise<MemberRecord>;
  removeMember(
    userId: string,
    organizationId: string,
    memberId: string,
  ): Promise<void>;
  listInvitations(
    userId: string,
    organizationId: string,
  ): Promise<InvitationRecord[]>;
  createInvitations(
    userId: string,
    organizationId: string,
    input: CreateInvitations,
  ): Promise<IssuedInvitation[]>;
  resendInvitation(
    userId: string,
    organizationId: string,
    invitationId: string,
  ): Promise<IssuedInvitation>;
  revokeInvitation(
    userId: string,
    organizationId: string,
    invitationId: string,
  ): Promise<void>;
  previewInvitation(token: string): Promise<InvitationPreview>;
  acceptInvitation(
    user: InvitationAcceptor,
    token: string,
  ): Promise<{ organizationId: string }>;
}

const issueToken = () => {
  const token = randomToken();

  return { token, tokenDigest: sha256Digest(token) };
};

const notAdmin = () =>
  new ControlServiceError(
    "forbidden",
    "Only admins of active organizations can do this.",
  );

const notFound = (subject: string) =>
  new ControlServiceError("not_found", `The ${subject} was not found.`);

export const createMemberService = (
  database: ControlDatabase,
): MemberService => {
  const records = createMemberStore(database);

  const requireOtherMember = async (
    userId: string,
    organizationId: string,
    memberId: string,
  ) => {
    await requireOrganizationAdmin(database, { userId, organizationId });
    if (memberId === userId)
      throw new ControlServiceError(
        "forbidden",
        "You can't change or remove your own membership.",
      );

    const member = await records.findMember(organizationId, memberId);
    if (!member) throw notFound("member");

    return member;
  };

  const organizationName = async (organizationId: string) => {
    const name = await records.organizationName(organizationId);
    if (!name) throw notFound("organization");

    return name;
  };

  return {
    async listMembers(userId, organizationId) {
      await requireMembership(database, { userId, organizationId });

      return records.listMembers(organizationId);
    },

    async updateMember(userId, organizationId, memberId, input) {
      const { role } = UpdateMemberSchema.parse(input);
      const member = await requireOtherMember(userId, organizationId, memberId);
      if (!(await records.updateRole(organizationId, userId, memberId, role)))
        throw notAdmin();

      return { ...member, role };
    },

    async removeMember(userId, organizationId, memberId) {
      await requireOtherMember(userId, organizationId, memberId);
      if (!(await records.removeMember(organizationId, userId, memberId)))
        throw notAdmin();
    },

    async listInvitations(userId, organizationId) {
      await requireMembership(database, { userId, organizationId });

      return records.listInvitations(organizationId);
    },

    async createInvitations(userId, organizationId, input) {
      const { emails, role } = CreateInvitationsSchema.parse(input);
      await requireOrganizationAdmin(database, { userId, organizationId });

      const unique = [...new Set(emails)];
      const members = await records.findMemberEmails(organizationId, unique);
      if (members.length)
        throw new ControlServiceError(
          "conflict",
          `Already in this organization: ${members.join(", ")}.`,
        );

      const name = await organizationName(organizationId);
      const now = new Date();
      const issued: IssuedInvitation[] = [];
      for (const email of unique) {
        const { token, tokenDigest } = issueToken();
        const invitation = await records.upsertInvitation({
          organizationId,
          email,
          role,
          tokenDigest,
          createdBy: userId,
          now,
        });
        if (!invitation) throw notFound("invitation");

        issued.push({ invitation, organizationName: name, token });
      }

      return issued;
    },

    async resendInvitation(userId, organizationId, invitationId) {
      await requireOrganizationAdmin(database, { userId, organizationId });

      const { token, tokenDigest } = issueToken();
      const invitation = await records.reissueInvitation(
        organizationId,
        invitationId,
        tokenDigest,
        new Date(),
      );
      if (!invitation) throw notFound("invitation");

      return {
        invitation,
        organizationName: await organizationName(organizationId),
        token,
      };
    },

    async revokeInvitation(userId, organizationId, invitationId) {
      await requireOrganizationAdmin(database, { userId, organizationId });

      if (!(await records.revokeInvitation(organizationId, invitationId)))
        throw notFound("invitation");
    },

    async previewInvitation(token) {
      const invitation = await records.findByToken(token, new Date());
      if (!invitation || invitation.status === "invalid")
        return { status: "invalid" };

      return {
        status: invitation.status,
        organization_id: invitation.organizationId,
        organization_name: invitation.organizationName,
        email: invitation.email,
        role: invitation.role,
        invited_by_email: invitation.invitedByEmail,
      };
    },

    async acceptInvitation(user, token) {
      const now = new Date();
      const invitation = await records.findByToken(token, now);
      if (invitation?.status !== "pending") throw notFound("invitation");
      if (!user.emailVerified || user.email.toLowerCase() !== invitation.email)
        throw new ControlServiceError(
          "forbidden",
          `This invitation is for ${invitation.email}.`,
        );

      const accepted = await records.accept(invitation.id, user.id, now, token);
      if (!accepted) throw notFound("invitation");
      if (!accepted.joined)
        throw new ControlServiceError(
          "conflict",
          "You're already a member of this organization.",
        );

      return { organizationId: accepted.organizationId };
    },
  };
};
