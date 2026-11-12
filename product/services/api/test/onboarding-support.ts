import type { OrganizationOnboarding } from "@gradiated/contracts";
import type {
  GithubIntegrationRecord,
  IntegrationRecord,
  IntegrationService,
  SlackIntegrationRecord,
  UserOrganization,
} from "@gradiated/control";
import { vi } from "vitest";

import type { PandaDocNda } from "../src/legal/pandadoc.js";
import { now, organizationId, organizationSummary, user } from "./support.js";

export const recordedNda = {
  document_id: "test-document",
  template_version: "v1",
  signed_at: "2026-08-16T12:00:00.000Z",
};

export const slackRecord = (
  overrides: Partial<SlackIntegrationRecord> = {},
): SlackIntegrationRecord => ({
  id: "0198ae80-0000-7000-8000-000000000001",
  organizationId,
  provider: "slack",
  externalId: "C123456",
  status: "active",
  settings: { schema_version: 1, channel_name: "ext-example-gradiated" },
  createdBy: user.id,
  createdAt: now,
  updatedAt: now,
  ...overrides,
});

export const ndaProvider = (status = "completed") =>
  ({
    templateVersion: "v1",
    read: vi.fn(async (_owner: unknown, id: string) => ({
      id,
      status,
      details: null,
      completed_at: status === "completed" ? recordedNda.signed_at : null,
      customer_completed: status === "completed",
    })),
  }) as unknown as PandaDocNda & { read: ReturnType<typeof vi.fn> };

export const onboardingOrganizations = (
  initial: OrganizationOnboarding = {},
  membership: UserOrganization = organizationSummary,
) => {
  let onboarding = initial;

  return {
    listForUser: vi.fn(async () => [membership]),
    getOnboarding: vi.fn(async () => onboarding),
    recordOnboardingNda: vi.fn(
      async (_userId: string, _organizationId: string, nda) => {
        onboarding = { ...onboarding, nda };

        return onboarding;
      },
    ),
    submitOnboarding: vi.fn(
      async (
        userId: string,
        _organizationId: string,
        contactChannel: "slack" | "email",
      ) => {
        if (onboarding.submitted_at) return { submitted: false, onboarding };

        onboarding = {
          ...onboarding,
          submitted_at: now.toISOString(),
          submitted_by: userId,
          contact_channel: contactChannel,
        };

        return { submitted: true, onboarding };
      },
    ),
    resetOnboardingSubmission: vi.fn(async () => {
      const {
        submitted_at: _submittedAt,
        submitted_by: _submittedBy,
        contact_channel: _contactChannel,
        ...rest
      } = onboarding;
      onboarding = rest;
    }),
  };
};

export const memoryIntegrations = (initial: IntegrationRecord[] = []) => {
  const rows = initial.map((row) => ({ ...row }));
  const slack = () =>
    rows.find(
      (row): row is SlackIntegrationRecord =>
        row.provider === "slack" && row.status !== "revoked",
    );
  const byId = (id: string) => {
    const row = rows.find((candidate) => candidate.id === id);
    if (!row) throw new Error(`Unknown integration ${id}`);

    return row;
  };

  const service = {
    list: vi.fn(async () => rows.filter((row) => row.status !== "revoked")),
    findSlackChannel: vi.fn(async () => slack()),
    recordSlackChannel: vi.fn(
      async (
        _userId: string,
        _organizationId: string,
        channel: { id: string; name: string },
      ) => {
        const row = slackRecord({
          id: `0198ae80-0000-7000-8000-${String(rows.length + 2).padStart(12, "0")}`,
          externalId: channel.id,
          status: "pending",
          settings: { schema_version: 1, channel_name: channel.name },
        });
        rows.push(row);

        return row;
      },
    ),
    claimSlackInvitation: vi.fn(
      async (
        _userId: string,
        _organizationId: string,
        input: { email: string },
      ) => {
        const row = slack()!;
        const previous = {
          invited_email: row.settings.invited_email,
          invited_at: row.settings.invited_at,
        };
        row.settings = {
          ...row.settings,
          invited_email: input.email,
          invited_at: now.toISOString(),
        };

        return { claimed: true as const, integration: row, previous };
      },
    ),
    releaseSlackInvitation: vi.fn(async () => undefined),
    activate: vi.fn(
      async (_userId: string, _organizationId: string, id: string) => {
        const row = byId(id);
        row.status = "active";

        return row;
      },
    ),
    revoke: vi.fn(
      async (_userId: string, _organizationId: string, id: string) => {
        byId(id).status = "revoked";
      },
    ),
    recordGithubInstallation: vi.fn(
      async (
        _userId: string,
        _organizationId: string,
        installation: {
          id: number;
          account_login: string;
          repository_selection: "all" | "selected";
        },
      ) => {
        const row: GithubIntegrationRecord = {
          ...slackRecord(),
          id: `0198ae80-0000-7000-9000-${String(installation.id).padStart(12, "0")}`,
          provider: "github",
          externalId: String(installation.id),
          status: "active",
          settings: {
            schema_version: 1,
            account_login: installation.account_login,
            repository_selection: installation.repository_selection,
          },
        };
        rows.push(row);

        return row;
      },
    ),
  } satisfies IntegrationService;

  return { service, rows };
};
