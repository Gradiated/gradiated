import { z } from "zod";

import type {
  EngineerOnboarding,
  EngineerOnboardingSubmission,
  GithubInstallation,
} from "@/api/engineer-onboarding";
import type { CurrentUser } from "@/api/queries";
import {
  POST_TRAINING_JOURNEY,
  invitationPath,
  type LoginSearch,
} from "@/lib/login-search";

export interface OnboardingSearch {
  journey?: typeof POST_TRAINING_JOURNEY;
  organization?: string;
  /** The console page that opened onboarding, for its way back. */
  from?: string;
}

const ORIGIN_PROBE = "https://console.invalid";

/* Only a path on the console itself, outside onboarding, is a way back. */
export const consoleReturnPath = (value: unknown) => {
  if (typeof value !== "string" || !value.startsWith("/") || value.length > 512)
    return undefined;
  const url = new URL(value, ORIGIN_PROBE);
  if (url.origin !== ORIGIN_PROBE || url.pathname.startsWith("/onboarding"))
    return undefined;
  return url.pathname + url.search + url.hash;
};

export const POST_TRAINING_ONBOARDING_PATH = `/onboarding?journey=${POST_TRAINING_JOURNEY}`;

export const engineerOnboardingKey = (organizationId: string) => [
  "engineer-onboarding",
  organizationId,
];

export const parseOnboardingSearch = (
  search: Record<string, unknown>,
): OnboardingSearch => {
  const organization = z.uuid().safeParse(search.organization);
  const from = consoleReturnPath(search.from);

  return {
    ...(from ? { from } : {}),
    ...(search.journey === POST_TRAINING_JOURNEY
      ? { journey: POST_TRAINING_JOURNEY }
      : {}),
    ...(organization.success ? { organization: organization.data } : {}),
  };
};

export const loginSearchFor = (location: {
  pathname: string;
  search: Record<string, unknown>;
}): LoginSearch =>
  location.pathname === "/onboarding" &&
  location.search.journey === POST_TRAINING_JOURNEY
    ? { journey: POST_TRAINING_JOURNEY }
    : {};

export const signInCallbacks = (search: LoginSearch, consoleOrigin: string) => {
  // An invitation, then an OAuth authorization, comes before the journey.
  const invitation = search.invitation
    ? invitationPath(search.invitation)
    : search.next;
  const postTraining = !invitation && search.journey === POST_TRAINING_JOURNEY;
  const callbackUrl = (path: string) => new URL(path, consoleOrigin).toString();

  return {
    callbackURL: callbackUrl(
      invitation ??
        (postTraining ? POST_TRAINING_ONBOARDING_PATH : "/api-keys"),
    ),
    newUserCallbackURL: callbackUrl(
      invitation ??
        (postTraining ? POST_TRAINING_ONBOARDING_PATH : "/onboarding"),
    ),
    errorCallbackURL: callbackUrl(
      postTraining ? `/login?journey=${POST_TRAINING_JOURNEY}` : "/login",
    ),
  };
};

const draftSchema = z.object({
  legalName: z.string().max(200).default(""),
  legalAddress: z.string().max(1000).default(""),
  signerName: z.string().max(100).nullable().default(null),
  signerTitle: z.string().max(100).default(""),
  ndaRequested: z.boolean().default(false),
  ndaDocumentId: z.string().max(100).nullable().default(null),
  channel: z.enum(["slack", "email"]).default("slack"),
  slackEmail: z.string().max(200).nullable().default(null),
  slackChannelName: z.string().max(80).nullable().default(null),
  context: z.string().max(3000).default(""),
});

export type OnboardingDraft = z.infer<typeof draftSchema>;

export interface OnboardingAccount {
  userId: string;
  organizationId: string;
  name: string;
  email: string;
  company: string;
}

export type VerifiedInstallation = Pick<
  GithubInstallation,
  "id" | "account" | "repository_count"
>;

export const draftStorageKey = (account: OnboardingAccount) =>
  `gradiated-engineer-onboarding-v1:${encodeURIComponent(account.userId)}:${encodeURIComponent(account.organizationId)}`;

export const emptyDraft = (): OnboardingDraft => draftSchema.parse({});

export const restoreDraft = (value: unknown): OnboardingDraft => {
  const parsed = draftSchema.safeParse(value);

  return parsed.success ? parsed.data : emptyDraft();
};

export const counterpartyDetails = (
  draft: OnboardingDraft,
  account: OnboardingAccount,
) => ({
  company: draft.legalName || account.company,
  name: draft.signerName ?? account.name,
  title: draft.signerTitle,
  address: draft.legalAddress,
  email: account.email,
});

const ndaFields = [
  "legalName",
  "legalAddress",
  "signerName",
  "signerTitle",
] as const;

export const changesNda = (
  draft: OnboardingDraft,
  values: Partial<OnboardingDraft>,
) => ndaFields.some((key) => key in values && values[key] !== draft[key]);

export const ndaReference = (
  server: EngineerOnboarding,
  draft: OnboardingDraft,
) =>
  server.nda || !draft.ndaRequested
    ? undefined
    : (draft.ndaDocumentId ?? undefined);

export type OnboardingSection = "code" | "contact" | "nda";

export const sectionId = (section: OnboardingSection) =>
  `onboarding-${section}`;

export const ndaPending = (
  server: EngineerOnboarding,
  draft: OnboardingDraft,
) => draft.ndaRequested && !server.nda;

/* What still stops the project starting. A requested NDA is not listed: it
   is signed as part of starting. */
export const startBlockers = (
  server: EngineerOnboarding,
  draft: OnboardingDraft,
  installation: VerifiedInstallation | null,
  githubAccounts: number,
  accountEmail: string,
) => {
  const blockers: { section: OnboardingSection; label: string }[] = [];
  if (!installation)
    blockers.push({
      section: "code",
      label:
        githubAccounts > 1
          ? "Choose the GitHub account for this project"
          : "Install the GitHub app",
    });
  else if (!installation.repository_count)
    blockers.push({
      section: "code",
      label: "Select a repository on GitHub",
    });

  // The API rejects an NDA without these, so name each one before signing.
  if (ndaPending(server, draft)) {
    const missing = [
      draft.signerName?.trim() === "" ? "signer’s name" : null,
      draft.signerTitle.trim() ? null : "signer’s title",
      draft.legalAddress.trim() ? null : "company address",
    ].filter((field) => field !== null);
    if (missing.length)
      blockers.push({
        section: "nda",
        label: `Add the NDA ${missing.length > 1 ? `${missing.slice(0, -1).join(", ")} and ${missing.at(-1)}` : missing[0]}`,
      });
  }

  if (
    draft.channel === "slack" &&
    !slackInvitedTo(server, slackRecipient(draft, accountEmail))
  )
    blockers.push({
      section: "contact",
      label: "Send the Slack invite, or choose email",
    });

  return blockers;
};

export const repositoryCount = (count: number) =>
  `${count} ${count === 1 ? "repository" : "repositories"}`;

export const slackInvited = (server: EngineerOnboarding) =>
  server.slack?.status === "active";

export const slackRecipient = (draft: OnboardingDraft, accountEmail: string) =>
  (draft.slackEmail ?? accountEmail).trim().toLowerCase();

// Invited, and to the address the form now names.
export const slackInvitedTo = (server: EngineerOnboarding, recipient: string) =>
  slackInvited(server) &&
  server.slack?.invited_email?.toLowerCase() === recipient;

export const engineerSubmission = (
  server: EngineerOnboarding,
  draft: OnboardingDraft,
  installation: VerifiedInstallation,
): EngineerOnboardingSubmission => {
  const notes = draft.context.trim();
  const ndaDocumentId = ndaReference(server, draft);

  return {
    contact_channel: draft.channel,
    github_installation_id: installation.id,
    ...(notes ? { notes } : {}),
    ...(ndaDocumentId ? { nda_document_id: ndaDocumentId } : {}),
  };
};

const submitProblems: Record<
  string,
  { section: OnboardingSection; message: string }
> = {
  nda_required: {
    section: "nda",
    message: "Your mutual NDA is not complete. Review and sign it again.",
  },
  github_authorization_required: {
    section: "code",
    message: "Install the GitHub app again so we can verify it.",
  },
  github_installation_unverified: {
    section: "code",
    message:
      "GitHub did not confirm the selected installation. Check its repository access and try again.",
  },
  github_repositories_required: {
    section: "code",
    message: "Select at least one repository for the Gradiated app on GitHub.",
  },
  slack_channel_required: {
    section: "contact",
    message: "Send the Slack invitation, or choose email instead.",
  },
};

export const submitProblem = (code: string | undefined) =>
  code ? submitProblems[code] : undefined;

export const slackInvitationProblem = (code: string | undefined) => {
  if (code === "slack_channel_name_taken")
    return {
      message: "That channel name is already in use.",
      renameChannel: true,
    };

  if (code === "slack_invitation_cooldown")
    return {
      message:
        "We just sent a Slack invitation. You can send another in 30 seconds.",
      renameChannel: false,
    };

  return undefined;
};

export const SLACK_CHANNEL_PATTERN = /^ext-[a-z0-9]+(?:-[a-z0-9]+)*-gradiated$/;

export const proposedSlackChannel = (company: string) => {
  const slug =
    company
      .normalize("NFKD")
      .replace(/[̀-ͯ]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 66)
      .replace(/-$/g, "") || "customer";

  return `ext-${slug}-gradiated`;
};

export const confirmationMessage = (
  server: EngineerOnboarding,
  email: string,
) => {
  if (
    server.contact_channel !== "slack" ||
    !server.slack ||
    !slackInvited(server)
  )
    return {
      plan: `Your researcher emails a plan to ${email}`,
      followUp: "Anything to add? Email team@gradiated.com.",
    };

  return {
    plan: `Your researcher posts a plan in #${server.slack.channel_name}`,
    followUp: `Accept the Slack invite we sent to ${server.slack.invited_email ?? email}, and invite your colleagues to the channel.`,
  };
};

type Membership = CurrentUser["organizations"][number];

export type AccountChoice =
  | { kind: "pick"; organizations: Membership[] }
  | { kind: "missing" }
  | { kind: "not_admin"; organization: string }
  | { kind: "ready"; account: OnboardingAccount };

export const chooseAccount = (
  user: CurrentUser,
  requestedOrganizationId: string | undefined,
): AccountChoice => {
  // Only organization admins can start a project; the API enforces it too.
  const active = user.organizations.filter((row) => row.status === "active");
  const memberships = active.filter((row) => row.role === "admin");
  if (!requestedOrganizationId && memberships.length > 1)
    return { kind: "pick", organizations: memberships };

  const organization = requestedOrganizationId
    ? memberships.find((row) => row.id === requestedOrganizationId)
    : memberships[0];
  if (!organization) {
    const member = requestedOrganizationId
      ? active.find((row) => row.id === requestedOrganizationId)
      : active[0];
    return member
      ? { kind: "not_admin", organization: member.name }
      : { kind: "missing" };
  }

  return {
    kind: "ready",
    account: {
      userId: user.id,
      organizationId: organization.id,
      name: user.name,
      email: user.email,
      company: organization.name,
    },
  };
};

/* Development uses the Gradiated [DEV] app, whose callback is localhost. */
export const GITHUB_APP_INSTALL_URL = `https://github.com/apps/${import.meta.env.VITE_GITHUB_APP_SLUG || "gradiated"}/installations/new`;

export const GITHUB_RETURN_PATH = "/onboarding/github-connected";

/* Linking a GitHub account that already belongs to another Gradiated user is
   refused; anything else is worth one more try. */
export const githubLinkProblem = (error: string) =>
  error === "account_already_linked_to_different_user"
    ? "That GitHub account is already connected to a different Gradiated account. Sign in to that account to continue, or use a different GitHub account."
    : "Close this tab and choose Install GitHub app again on the setup page.";

/* One trip to GitHub: the app requests user authorization during
   installation, so GitHub returns to Better Auth's GitHub callback with an
   OAuth code. Reusing the state Better Auth issued for linkSocial lets that
   callback link the user's GitHub account, which the API then uses to verify
   the installation. */
export const githubInstallUrl = (authorizationUrl: string) => {
  const url = new URL(authorizationUrl);
  const state = url.searchParams.get("state");
  if (url.protocol !== "https:" || url.hostname !== "github.com" || !state)
    throw new Error("Unexpected GitHub authorization URL.");

  const install = new URL(GITHUB_APP_INSTALL_URL);
  install.searchParams.set("state", state);

  return install.toString();
};
