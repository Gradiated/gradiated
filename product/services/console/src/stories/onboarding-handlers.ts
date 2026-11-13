import { delay, http, HttpResponse } from "msw";

import type {
  EngineerOnboarding,
  GithubInstallation,
  NdaDetails,
} from "@/api/engineer-onboarding";
import { acmeAdmin, handlersFor } from "@/stories/handlers";

const organizationPath = "/api/v1/organizations/:organizationId";
const now = "2026-11-12T10:00:00.000Z";

export const notStarted: EngineerOnboarding = {
  nda: null,
  slack: null,
  github_installations: [],
  contact_channel: null,
  submitted_at: null,
};

export const invitedSlack: NonNullable<EngineerOnboarding["slack"]> = {
  channel_id: "C0STORYBOOK",
  channel_name: "ext-acme-gradiated",
  status: "active",
  invited_email: "alex@acme.com",
  invited_at: now,
};

export const signedNda: NonNullable<EngineerOnboarding["nda"]> = {
  document_id: "storybook-nda",
  signed_at: now,
};

const repositories = [
  "acme/trainer",
  "acme/eval-harness",
  "acme/data-pipelines",
  "acme/inference-gateway",
  "acme/reward-models",
];

export const acmeInstallation = (
  patch: Partial<GithubInstallation> = {},
): GithubInstallation => ({
  id: 4201,
  account: "acme",
  account_type: "Organization",
  manage_url:
    "https://github.com/organizations/acme/settings/installations/4201",
  repository_selection: "selected",
  repository_count: 3,
  repositories: repositories.slice(0, 3),
  ...patch,
});

export const manyRepositories = acmeInstallation({
  repository_selection: "all",
  repository_count: 47,
  repositories,
});

export const noRepositories = acmeInstallation({
  repository_count: 0,
  repositories: [],
});

export const severalAccounts: GithubInstallation[] = [
  acmeInstallation(),
  acmeInstallation({
    id: 4202,
    account: "acme-labs",
    repository_count: 1,
    repositories: ["acme-labs/rl-gym"],
    manage_url:
      "https://github.com/organizations/acme-labs/settings/installations/4202",
  }),
  acmeInstallation({
    id: 4203,
    account: "acme-research",
    repository_selection: "all",
    repository_count: 58,
    repositories,
    manage_url:
      "https://github.com/organizations/acme-research/settings/installations/4203",
  }),
  acmeInstallation({
    id: 4204,
    account: "alexmorgan",
    account_type: "User",
    repository_count: 2,
    repositories: ["alexmorgan/dotfiles", "alexmorgan/notebooks"],
    manage_url: "https://github.com/settings/installations/4204",
  }),
  acmeInstallation({
    id: 4205,
    account: "acme-archive",
    repository_count: 4,
  }),
  acmeInstallation({
    id: 4206,
    account: "acme-sandbox",
    repository_count: 1,
  }),
];

const problem = (status: number, code: string, detail: string) =>
  HttpResponse.json(
    {
      type: `https://gradiated.com/problems/${code}`,
      title: detail,
      status,
      detail,
      code,
    },
    { status },
  );

const ndaDetails: NdaDetails = {
  company: "Acme",
  name: "Alex Example",
  title: "CTO",
  address: "500 Market Street, San Francisco, CA 94105",
  email: "alex@acme.com",
};

export interface OnboardingScenario {
  onboarding?: EngineerOnboarding;
  installations?: GithubInstallation[];
  /** No GitHub account linked yet. */
  unlinked?: boolean;
  slackInvite?: "ok" | "channel_taken" | "cooldown";
  submission?: "ok" | "github_repositories_required" | "slow";
}

/* The post-training journey for Acme's admin, with its API mocked. Handlers
   come before handlersFor so they take precedence. */
export const onboardingHandlers = ({
  onboarding = notStarted,
  installations = [],
  unlinked = false,
  slackInvite = "ok",
  submission = "ok",
}: OnboardingScenario = {}) => {
  let state = onboarding;

  return [
    http.get(`${organizationPath}/engineer-onboarding`, () =>
      HttpResponse.json(state),
    ),
    http.get(`${organizationPath}/github-installations`, () =>
      HttpResponse.json(
        unlinked
          ? { status: "authorization_required", installations: [] }
          : {
              status: installations.length ? "installed" : "not_installed",
              installations,
            },
      ),
    ),
    http.post("/api/auth/link-social", () =>
      HttpResponse.json({
        url: "https://github.com/login/oauth/authorize?client_id=storybook&state=storybook",
        redirect: false,
      }),
    ),
    http.post(`${organizationPath}/slack-invitations`, async ({ request }) => {
      const body = (await request.json()) as { email: string };
      if (slackInvite === "channel_taken")
        return problem(
          409,
          "slack_channel_name_taken",
          "That channel name is already in use.",
        );
      if (slackInvite === "cooldown")
        return problem(
          429,
          "slack_invitation_cooldown",
          "A Slack invitation was sent recently.",
        );

      state = {
        ...state,
        slack: {
          ...invitedSlack,
          invited_email: body.email,
          invited_at: new Date().toISOString(),
        },
      };
      return HttpResponse.json({
        channel_id: invitedSlack.channel_id,
        channel_name: invitedSlack.channel_name,
        email: body.email,
        status: "invited",
      });
    }),
    http.post(
      `${organizationPath}/engineer-onboarding/submission`,
      async () => {
        if (submission === "github_repositories_required")
          return problem(
            409,
            "github_repositories_required",
            "Select at least one repository for the Gradiated app on GitHub, then try again.",
          );
        if (submission === "slow") await delay("infinite");

        state = {
          ...state,
          contact_channel: state.slack ? "slack" : "email",
          github_installations: [
            { id: 4201, account: "acme", repository_selection: "selected" },
          ],
          submitted_at: new Date().toISOString(),
        };
        return HttpResponse.json(state);
      },
    ),
    http.post(`${organizationPath}/nda-documents`, () =>
      HttpResponse.json({
        id: "storybook-nda",
        status: "preparing",
        details: ndaDetails,
        completed_at: null,
        customer_completed: false,
      }),
    ),
    http.get(`${organizationPath}/nda-documents/:documentId`, () =>
      HttpResponse.json({
        id: "storybook-nda",
        status: "preparing",
        details: ndaDetails,
        completed_at: null,
        customer_completed: false,
      }),
    ),
    ...handlersFor(acmeAdmin),
  ];
};
