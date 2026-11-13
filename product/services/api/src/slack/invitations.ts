import type { IntegrationService } from "@gradiated/control";

import { ApiProblem, problems } from "../http/problems.js";
import {
  SlackInvitationSchema,
  slackChannelName,
  type SlackConnect,
} from "./connect.js";

export const SLACK_INVITATION_COOLDOWN_MS = 30_000;

export class SlackInvitationCooldown extends Error {
  constructor(readonly availableAt: Date) {
    super("A Slack invitation was sent recently.");
    this.name = "SlackInvitationCooldown";
  }
}

export const inviteToSlack = async (
  slack: SlackConnect,
  integrations: IntegrationService,
  input: {
    userId: string;
    organizationId: string;
    company: string;
    email: string;
    channelName?: string | undefined;
  },
) => {
  const { userId, organizationId } = input;
  let integration = await integrations.findSlackChannel(userId, organizationId);
  if (integration && !(await slack.findChannel(integration.externalId))) {
    await integrations.revoke(userId, organizationId, integration.id);
    integration = undefined;
  }

  if (!integration) {
    const created = await slack.createChannel(
      input.channelName ?? slackChannelName(input.company),
    );
    if (created.status === "name_taken")
      throw new ApiProblem(
        problems.onboardingConflict(
          "slack_channel_name_taken",
          "That Slack channel name is already in use. Choose a different name.",
        ),
      );

    integration = await integrations.recordSlackChannel(
      userId,
      organizationId,
      created.channel,
    );
    await slack.labelChannel(created.channel.id, organizationId);
  }

  const claim = await integrations.claimSlackInvitation(
    userId,
    organizationId,
    { email: input.email, cooldownMs: SLACK_INVITATION_COOLDOWN_MS },
  );
  if (!claim.claimed) throw new SlackInvitationCooldown(claim.availableAt);

  let status: Awaited<ReturnType<SlackConnect["inviteMembers"]>>;
  try {
    status = await slack.inviteMembers(integration.externalId, input.email);
  } catch (error) {
    await integrations
      .releaseSlackInvitation(userId, organizationId, claim)
      .catch(() => undefined);
    throw error;
  }

  await integrations.activate(userId, organizationId, integration.id);

  return SlackInvitationSchema.parse({
    channel_id: integration.externalId,
    channel_name: integration.settings.channel_name,
    email: input.email,
    status,
  });
};
