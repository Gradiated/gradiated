import { z } from "zod";

import type {
  EngineerOnboarding,
  EngineerOnboardingSubmission,
} from "@/api/engineer-onboarding";
import type { CurrentUser } from "@/api/queries";
import { invitationPath, type LoginSearch } from "@/lib/login-search";

export const ENGINEER_ONBOARDING_PATH = "/onboarding/engineer";

export const parseEngineerOnboardingSearch = (
  search: Record<string, unknown>,
): { organization?: string } => {
  const organization = z.uuid().safeParse(search.organization);

  return organization.success ? { organization: organization.data } : {};
};

export const parseOnboardingSearch = (
  search: Record<string, unknown>,
): { next?: "engineer"; organization?: string } => ({
  ...(search.next === "engineer" ? { next: "engineer" as const } : {}),
  ...parseEngineerOnboardingSearch(search),
});

export const loginSearchFor = (pathname: string): LoginSearch =>
  pathname === ENGINEER_ONBOARDING_PATH ? { next: "engineer" } : {};

export const signInCallbacks = (search: LoginSearch, consoleOrigin: string) => {
  const invitation = search.invitation
    ? invitationPath(search.invitation)
    : undefined;
  const engineer = !invitation && search.next === "engineer";
  const callbackUrl = (path: string) => new URL(path, consoleOrigin).toString();

  return {
    callbackURL: callbackUrl(
      invitation ?? (engineer ? ENGINEER_ONBOARDING_PATH : "/api-keys"),
    ),
    newUserCallbackURL: callbackUrl(
      invitation ?? (engineer ? "/onboarding?next=engineer" : "/onboarding"),
    ),
    errorCallbackURL: callbackUrl(engineer ? "/login?next=engineer" : "/login"),
  };
};

const draftSchema = z.object({
  legalName: z.string().max(200).default(""),
  legalAddress: z.string().max(1000).default(""),
  signerName: z.string().max(100).nullable().default(null),
  signerTitle: z.string().max(100).default(""),
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

export interface VerifiedInstallation {
  id: number;
  account: string;
  repository_count: number;
}

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
) => (server.nda ? undefined : (draft.ndaDocumentId ?? undefined));

export type OnboardingView = "introduction" | "steps" | "complete";

export const resumeView = (server: EngineerOnboarding): OnboardingView =>
  server.submitted_at ? "complete" : server.nda ? "steps" : "introduction";

export const resumeStep = (server: EngineerOnboarding) => (server.nda ? 1 : 0);

export const stepLocked = (
  index: number,
  step: number,
  unlocked: { nda: boolean; github: boolean },
) =>
  index > step ||
  (index > 0 && !unlocked.nda) ||
  (index > 1 && !unlocked.github);

export type SubmitAction = "sign" | "github_required" | "advance" | "finish";

export const submitAction = (
  step: number,
  {
    ndaSigned,
    installation,
  }: { ndaSigned: boolean; installation: VerifiedInstallation | null },
): SubmitAction => {
  if (step === 0) return ndaSigned ? "advance" : "sign";

  if (!installation) return "github_required";

  return step === 2 ? "finish" : "advance";
};

export const slackInvited = (server: EngineerOnboarding) =>
  server.slack?.status === "active";

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

const submitProblems: Record<string, { step: number; message: string }> = {
  nda_required: {
    step: 0,
    message: "Your mutual NDA is not complete. Review and sign it again.",
  },
  github_authorization_required: {
    step: 1,
    message: "Authorize GitHub so we can verify your installation.",
  },
  github_installation_unverified: {
    step: 1,
    message:
      "GitHub did not confirm the selected installation. Check its repository access and try again.",
  },
  slack_channel_required: {
    step: 1,
    message: "Send the Slack invitation, or choose email instead.",
  },
};

export const submitProblem = (code: string | undefined) =>
  code ? submitProblems[code] : undefined;

export const slackInvitationProblem = (code: string | undefined) => {
  if (code === "slack_channel_name_taken")
    return {
      message: "That channel name is already in use. Choose another name.",
      renameChannel: true,
    };

  if (code === "slack_invitation_cooldown")
    return {
      message:
        "We just sent a Slack invitation. You can send another in about 10 minutes.",
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

export const channelSummary = (
  server: EngineerOnboarding,
  draft: OnboardingDraft,
) => {
  if (draft.channel === "email") return "Email fallback · Slack unavailable";

  if (!server.slack || !slackInvited(server))
    return "Slack invitation not sent yet";

  return `#${server.slack.channel_name} · invitation sent`;
};

export const confirmationMessage = (
  server: EngineerOnboarding,
  email: string,
) => {
  const meantime = "If in the meantime you want to chat or tell us anything, ";

  if (
    server.contact_channel !== "slack" ||
    !server.slack ||
    !slackInvited(server)
  )
    return {
      plan: `Thank you, we've got everything we need. One of our researchers will have a look into your project now and will email a plan to ${email} as soon as possible, likely within a working day!`,
      followUp: meantime + "email us at help@gradiated.com.",
    };

  return {
    plan: "Thank you, we've got everything we need. One of our researchers will have a look into your project now and will suggest a plan on Slack with you as soon as possible, likely within a working day!",
    followUp:
      meantime +
      `hop into #${server.slack.channel_name} and invite some colleagues to it. If you haven't joined yet, accept the Slack invitation we sent to ${server.slack.invited_email ?? email}.`,
  };
};

type Membership = CurrentUser["organizations"][number];

export type AccountChoice =
  | { kind: "pick"; organizations: Membership[] }
  | { kind: "missing" }
  | { kind: "setup"; organizationId: string }
  | { kind: "ready"; account: OnboardingAccount };

export const chooseAccount = (
  user: CurrentUser,
  requestedOrganizationId: string | undefined,
): AccountChoice => {
  const memberships = user.organizations.filter(
    (row) => row.status === "active",
  );
  if (!requestedOrganizationId && memberships.length > 1)
    return { kind: "pick", organizations: memberships };

  const organization = requestedOrganizationId
    ? memberships.find((row) => row.id === requestedOrganizationId)
    : memberships[0];
  if (!organization) return { kind: "missing" };

  if (organization.role === "admin" && !organization.onboarding_completed)
    return { kind: "setup", organizationId: organization.id };

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
