import type { GithubIntegrationSettings } from "@gradiated/contracts";

import { requireOrganizationAdmin } from "../access.js";
import type { ControlDatabase } from "../db/client.js";
import { ControlServiceError } from "../errors.js";
import {
  createIntegrationStore,
  type GithubIntegrationRecord,
  type IntegrationRecord,
  type SlackIntegrationRecord,
  type SlackInvitationSettings,
} from "./store.js";

export type {
  GithubIntegrationRecord,
  IntegrationRecord,
  SlackIntegrationRecord,
} from "./store.js";

export type SlackInvitationClaim =
  | {
      claimed: true;
      integration: SlackIntegrationRecord;
      previous: SlackInvitationSettings;
    }
  | { claimed: false; availableAt: Date };

export interface IntegrationService {
  list(userId: string, organizationId: string): Promise<IntegrationRecord[]>;
  findSlackChannel(
    userId: string,
    organizationId: string,
  ): Promise<SlackIntegrationRecord | undefined>;
  recordSlackChannel(
    userId: string,
    organizationId: string,
    channel: { id: string; name: string },
  ): Promise<SlackIntegrationRecord>;
  claimSlackInvitation(
    userId: string,
    organizationId: string,
    input: { email: string; cooldownMs: number },
  ): Promise<SlackInvitationClaim>;
  releaseSlackInvitation(
    userId: string,
    organizationId: string,
    claim: Extract<SlackInvitationClaim, { claimed: true }>,
  ): Promise<void>;
  activate(
    userId: string,
    organizationId: string,
    integrationId: string,
  ): Promise<IntegrationRecord>;
  revoke(
    userId: string,
    organizationId: string,
    integrationId: string,
  ): Promise<void>;
  recordGithubInstallation(
    userId: string,
    organizationId: string,
    installation: { id: number } & Omit<
      GithubIntegrationSettings,
      "schema_version"
    >,
  ): Promise<GithubIntegrationRecord>;
}

const notFound = () =>
  new ControlServiceError("not_found", "The integration was not found.");

export const createIntegrationService = (
  database: ControlDatabase,
): IntegrationService => {
  const records = createIntegrationStore(database);
  const authorize = (userId: string, organizationId: string) =>
    requireOrganizationAdmin(database, { userId, organizationId });

  return {
    async list(userId, organizationId) {
      await authorize(userId, organizationId);

      return records.list(organizationId);
    },

    async findSlackChannel(userId, organizationId) {
      await authorize(userId, organizationId);

      return records.findSlack(organizationId);
    },

    async recordSlackChannel(userId, organizationId, channel) {
      await authorize(userId, organizationId);

      const integration = await records.insertSlack({
        organizationId,
        channelId: channel.id,
        channelName: channel.name,
        createdBy: userId,
        now: new Date(),
      });
      if (!integration)
        throw new ControlServiceError(
          "conflict",
          "This organization or Slack channel already has a Slack integration.",
        );

      return integration;
    },

    async claimSlackInvitation(userId, organizationId, input) {
      await authorize(userId, organizationId);

      const current = await records.findSlack(organizationId);
      if (!current) throw notFound();

      const now = new Date();
      const integration = await records.claimSlackInvitation({
        organizationId,
        integrationId: current.id,
        email: input.email,
        now,
        availableAfter: new Date(now.getTime() - input.cooldownMs),
      });
      if (integration)
        return {
          claimed: true,
          integration,
          previous: {
            invited_email: current.settings.invited_email,
            invited_at: current.settings.invited_at,
          },
        };

      const latest = await records.findSlack(organizationId);
      const invitedAt = latest?.settings.invited_at;
      if (!invitedAt) throw notFound();

      return {
        claimed: false,
        availableAt: new Date(Date.parse(invitedAt) + input.cooldownMs),
      };
    },

    async releaseSlackInvitation(userId, organizationId, claim) {
      await authorize(userId, organizationId);

      const claimedAt = claim.integration.settings.invited_at;
      if (!claimedAt) return;

      await records.restoreSlackInvitation({
        organizationId,
        integrationId: claim.integration.id,
        claimedAt,
        previous: claim.previous,
      });
    },

    async activate(userId, organizationId, integrationId) {
      await authorize(userId, organizationId);

      const integration = await records.setStatus(
        organizationId,
        integrationId,
        "active",
      );
      if (!integration) throw notFound();

      return integration;
    },

    async revoke(userId, organizationId, integrationId) {
      await authorize(userId, organizationId);

      if (!(await records.setStatus(organizationId, integrationId, "revoked")))
        throw notFound();
    },

    async recordGithubInstallation(userId, organizationId, installation) {
      await authorize(userId, organizationId);

      const integration = await records.upsertGithub({
        organizationId,
        installationId: String(installation.id),
        settings: {
          schema_version: 1,
          account_login: installation.account_login,
          repository_selection: installation.repository_selection,
        },
        createdBy: userId,
        now: new Date(),
      });
      if (!integration)
        throw new ControlServiceError(
          "conflict",
          "This GitHub installation is connected to another organization.",
        );

      return integration;
    },
  };
};
