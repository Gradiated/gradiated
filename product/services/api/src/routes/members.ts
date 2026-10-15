import {
  CreateInvitationsSchema,
  CurrentOrganizationSchema,
  InvitationListSchema,
  InvitationParamsSchema,
  InvitationPreviewSchema,
  InvitationSchema,
  InvitationTokenSchema,
  MemberListSchema,
  MemberParamsSchema,
  MemberSchema,
  OrganizationIdParamsSchema,
  UpdateMemberSchema,
  problemContent,
  type Invitation,
  type Member,
} from "@gradiated/contracts";
import {
  ControlServiceError,
  type InvitationRecord,
  type IssuedInvitation,
  type MemberRecord,
  type MemberService,
  type OrganizationService,
} from "@gradiated/control";
import { createRoute, type OpenAPIHono } from "@hono/zod-openapi";

import { invitationUrl, type InvitationSender } from "../email/invitation.js";
import { requireUser } from "../http/problems.js";
import type { ApiEnvironment } from "../types.js";
import { toCurrentOrganization } from "./me.js";

const base = "/api/v1/organizations/{organization_id}";
const errors = {
  401: { description: "Authentication required.", content: problemContent },
  403: { description: "Not allowed.", content: problemContent },
  404: { description: "Not found.", content: problemContent },
  422: { description: "Invalid request.", content: problemContent },
};
const json = <Schema>(schema: Schema, description: string) => ({
  description,
  content: { "application/json": { schema } },
});
const body = <Schema>(schema: Schema) => ({
  required: true,
  content: { "application/json": { schema } },
});

const listMembers = createRoute({
  method: "get",
  path: `${base}/members`,
  operationId: "listMembers",
  tags: ["Members"],
  request: { params: OrganizationIdParamsSchema },
  responses: {
    200: json(MemberListSchema, "Active members, oldest first."),
    ...errors,
  },
});
const updateMember = createRoute({
  method: "patch",
  path: `${base}/members/{user_id}`,
  operationId: "updateMember",
  tags: ["Members"],
  request: { params: MemberParamsSchema, body: body(UpdateMemberSchema) },
  responses: {
    200: json(MemberSchema, "The member with their new role."),
    ...errors,
  },
});
const removeMember = createRoute({
  method: "delete",
  path: `${base}/members/{user_id}`,
  operationId: "removeMember",
  tags: ["Members"],
  request: { params: MemberParamsSchema },
  responses: { 204: { description: "The member was removed." }, ...errors },
});
const listInvitations = createRoute({
  method: "get",
  path: `${base}/invitations`,
  operationId: "listInvitations",
  tags: ["Members"],
  request: { params: OrganizationIdParamsSchema },
  responses: {
    200: json(InvitationListSchema, "Invitations that are not yet accepted."),
    ...errors,
  },
});
const createInvitations = createRoute({
  method: "post",
  path: `${base}/invitations`,
  operationId: "createInvitations",
  tags: ["Members"],
  request: {
    params: OrganizationIdParamsSchema,
    body: body(CreateInvitationsSchema),
  },
  responses: {
    201: json(InvitationListSchema, "Invitations were emailed."),
    409: {
      description: "Some addresses already belong to members.",
      content: problemContent,
    },
    503: {
      description:
        "The invitations were saved, but some emails could not be sent.",
      content: problemContent,
    },
    ...errors,
  },
});
const resendInvitation = createRoute({
  method: "post",
  path: `${base}/invitations/{invitation_id}/resend`,
  operationId: "resendInvitation",
  tags: ["Members"],
  request: { params: InvitationParamsSchema },
  responses: {
    200: json(InvitationSchema, "A new link was emailed."),
    503: {
      description: "The invitation was saved, but the email could not be sent.",
      content: problemContent,
    },
    ...errors,
  },
});
const revokeInvitation = createRoute({
  method: "delete",
  path: `${base}/invitations/{invitation_id}`,
  operationId: "revokeInvitation",
  tags: ["Members"],
  request: { params: InvitationParamsSchema },
  responses: { 204: { description: "The invitation was revoked." }, ...errors },
});
const previewInvitation = createRoute({
  method: "post",
  path: "/api/v1/invitations/preview",
  operationId: "previewInvitation",
  tags: ["Members"],
  description: "Describes an invitation link. The token is the credential.",
  request: { body: body(InvitationTokenSchema) },
  responses: {
    200: json(InvitationPreviewSchema, "The invitation's state."),
    422: errors[422],
  },
});
const acceptInvitation = createRoute({
  method: "post",
  path: "/api/v1/invitations/accept",
  operationId: "acceptInvitation",
  tags: ["Members"],
  request: { body: body(InvitationTokenSchema) },
  responses: {
    ...errors,
    200: json(CurrentOrganizationSchema, "The organization you joined."),
    403: {
      description: "The invitation is for a different email address.",
      content: problemContent,
    },
    409: {
      description: "You are already a member.",
      content: problemContent,
    },
  },
});

const toMember = (member: MemberRecord): Member => ({
  user_id: member.userId,
  email: member.email,
  role: member.role,
  joined_at: member.joinedAt.toISOString(),
});

const toInvitation = (invitation: InvitationRecord): Invitation => ({
  id: invitation.id,
  email: invitation.email,
  role: invitation.role,
  invited_by_email: invitation.invitedByEmail,
  expires_at: invitation.expiresAt.toISOString(),
  created_at: invitation.createdAt.toISOString(),
});

export const registerMemberRoutes = (
  app: OpenAPIHono<ApiEnvironment>,
  dependencies: {
    members: MemberService;
    organizations: Pick<OrganizationService, "listForUser">;
    sendInvitation: InvitationSender;
    consoleUrl: string;
  },
): void => {
  const { members, organizations, sendInvitation, consoleUrl } = dependencies;
  const send = (inviter: string, issued: IssuedInvitation) =>
    sendInvitation({
      email: issued.invitation.email,
      invitedByEmail: inviter,
      organizationName: issued.organizationName,
      role: issued.invitation.role,
      url: invitationUrl(consoleUrl, issued.token),
    });

  app.openapi(listMembers, async (context) => {
    const user = await requireUser(context);
    const { organization_id } = context.req.valid("param");
    const rows = await members.listMembers(user.id, organization_id);

    return context.json({ data: rows.map(toMember), next_cursor: null }, 200);
  });

  app.openapi(updateMember, async (context) => {
    const user = await requireUser(context);
    const { organization_id, user_id } = context.req.valid("param");
    const input = context.req.valid("json");
    const member = await members.updateMember(
      user.id,
      organization_id,
      user_id,
      input,
    );

    context
      .get("analytics")
      ?.track(user.id, "organization_member_role_changed", {
        organization_id,
        role: member.role,
      });

    return context.json(toMember(member), 200);
  });

  app.openapi(removeMember, async (context) => {
    const user = await requireUser(context);
    const { organization_id, user_id } = context.req.valid("param");
    await members.removeMember(user.id, organization_id, user_id);

    context.get("analytics")?.track(user.id, "organization_member_removed", {
      organization_id,
    });

    return context.body(null, 204);
  });

  app.openapi(listInvitations, async (context) => {
    const user = await requireUser(context);
    const { organization_id } = context.req.valid("param");
    const rows = await members.listInvitations(user.id, organization_id);

    return context.json(
      { data: rows.map(toInvitation), next_cursor: null },
      200,
    );
  });

  app.openapi(createInvitations, async (context) => {
    const user = await requireUser(context);
    const { organization_id } = context.req.valid("param");
    const issued = await members.createInvitations(
      user.id,
      organization_id,
      context.req.valid("json"),
    );
    const delivered = await Promise.allSettled(
      issued.map((invitation) => send(user.email, invitation)),
    );

    if (delivered.some((result) => result.status === "rejected"))
      throw new ControlServiceError(
        "unavailable",
        "The invitations were saved, but some emails could not be sent. Use Resend to try again.",
      );

    context.get("analytics")?.track(user.id, "organization_members_invited", {
      organization_id,
      invitation_count: issued.length,
    });

    return context.json(
      {
        data: issued.map(({ invitation }) => toInvitation(invitation)),
        next_cursor: null,
      },
      201,
    );
  });

  app.openapi(resendInvitation, async (context) => {
    const user = await requireUser(context);
    const { organization_id, invitation_id } = context.req.valid("param");
    const issued = await members.resendInvitation(
      user.id,
      organization_id,
      invitation_id,
    );
    await send(user.email, issued).catch((error: unknown) => {
      throw new ControlServiceError(
        "unavailable",
        "The invitation was saved, but the email could not be sent. Try again.",
        error,
      );
    });

    return context.json(toInvitation(issued.invitation), 200);
  });

  app.openapi(revokeInvitation, async (context) => {
    const user = await requireUser(context);
    const { organization_id, invitation_id } = context.req.valid("param");
    await members.revokeInvitation(user.id, organization_id, invitation_id);

    return context.body(null, 204);
  });

  app.openapi(previewInvitation, async (context) => {
    const { token } = context.req.valid("json");

    return context.json(await members.previewInvitation(token), 200);
  });

  app.openapi(acceptInvitation, async (context) => {
    const user = await requireUser(context);
    const { token } = context.req.valid("json");
    const { organizationId } = await members.acceptInvitation(user, token);
    const [organization] = await organizations.listForUser(
      user.id,
      organizationId,
    );
    if (!organization)
      throw new ControlServiceError(
        "not_found",
        "The organization was not found.",
      );

    context
      .get("analytics")
      ?.track(user.id, "organization_invitation_accepted", {
        organization_id: organizationId,
      });

    return context.json(toCurrentOrganization(organization), 200);
  });
};
