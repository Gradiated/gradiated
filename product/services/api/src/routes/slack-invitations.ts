import { problemContent } from "@gradiated/contracts";
import type { IntegrationService } from "@gradiated/control";
import { createRoute, type OpenAPIHono, z } from "@hono/zod-openapi";

import { consoleOnly } from "../http/audience.js";
import {
  requireOnboardingAdmin,
  type OnboardingOrganizations,
} from "../http/onboarding-access.js";
import { ApiProblem, problems } from "../http/problems.js";
import {
  SlackChannelNameSchema,
  SlackInvitationSchema,
  type SlackConnect,
} from "../slack/connect.js";
import {
  inviteToSlack,
  SlackInvitationCooldown,
} from "../slack/invitations.js";
import type { ApiEnvironment } from "../types.js";

const create = createRoute({
  ...consoleOnly,
  method: "post",
  path: "/api/v1/organizations/{organization_id}/slack-invitations",
  operationId: "createSlackInvitation",
  tags: ["Slack invitations"],
  summary:
    "Invite the customer's chosen email to the organization's Slack Connect channel",
  description:
    "Requires an active verified organization admin. Each organization has one channel: the first request creates it, and later requests re-invite into the stored channel and ignore channel_name. The Slack email may differ from the signed-in account. One invitation is sent per organization every 10 minutes. Customer acceptance and workspace approval may still be required.",
  request: {
    params: z.object({
      organization_id: z.uuid().describe("The customer organization."),
    }),
    body: {
      required: true,
      content: {
        "application/json": {
          schema: z.strictObject({
            channel_name: SlackChannelNameSchema.optional().describe(
              "A name for a new channel; ignored once the organization has one.",
            ),
            email: z
              .string()
              .trim()
              .toLowerCase()
              .email()
              .max(200)
              .optional()
              .describe(
                "The Slack invitation recipient; defaults to the signed-in account email",
              ),
          }),
        },
      },
    },
  },
  responses: {
    201: {
      description: "Slack confirmed the invitation or existing membership.",
      content: { "application/json": { schema: SlackInvitationSchema } },
    },
    401: {
      description: "A signed-in user is required.",
      content: problemContent,
    },
    403: {
      description: "A verified organization admin is required.",
      content: problemContent,
    },
    409: {
      description:
        "slack_channel_name_taken: a new channel name is already in use.",
      content: problemContent,
    },
    422: { description: "Invalid request.", content: problemContent },
    429: {
      description:
        "slack_invitation_cooldown: this organization was invited recently; see Retry-After.",
      content: problemContent,
    },
    503: {
      description: "Slack is not configured or did not confirm the request.",
      content: problemContent,
    },
  },
});

export const registerSlackInvitationRoutes = (
  app: OpenAPIHono<ApiEnvironment>,
  services: {
    organizations: OnboardingOrganizations;
    integrations: IntegrationService;
  },
  provider?: SlackConnect,
) => {
  app.openapi(create, async (context) => {
    context.header("Cache-Control", "no-store");
    const { organization_id } = context.req.valid("param");
    const { owner, organization } = await requireOnboardingAdmin(
      context,
      services.organizations,
      organization_id,
    );
    if (!provider)
      throw new ApiProblem(
        problems.unavailable(
          "Automatic Slack invitations have not been configured yet. You can continue with setup.",
        ),
      );

    const input = context.req.valid("json");

    const invitation = await inviteToSlack(provider, services.integrations, {
      userId: owner.userId,
      organizationId: organization_id,
      company: organization.name,
      email: input.email ?? owner.email,
      channelName: input.channel_name,
    }).catch((error: unknown) => {
      if (!(error instanceof SlackInvitationCooldown)) throw error;

      const seconds = Math.max(
        1,
        Math.ceil((error.availableAt.getTime() - Date.now()) / 1000),
      );
      context.header("Retry-After", String(seconds));
      throw new ApiProblem(
        problems.slackInvitationCooldown(
          "A Slack invitation was sent recently. Check your email, or try again in a few minutes.",
        ),
      );
    });

    return context.json(invitation, 201);
  });
};
