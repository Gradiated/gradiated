import { describe, expect, it } from "vitest";
import type { EngineerOnboarding } from "@/api/engineer-onboarding";
import type { CurrentUser } from "@/api/queries";
import {
  changesNda,
  channelSummary,
  chooseAccount,
  confirmationMessage,
  counterpartyDetails,
  draftStorageKey,
  emptyDraft,
  engineerSubmission,
  ndaReference,
  proposedSlackChannel,
  restoreDraft,
  resumeStep,
  resumeView,
  slackInvitationProblem,
  stepLocked,
  submitAction,
  submitProblem,
  type OnboardingAccount,
  type OnboardingDraft,
} from "@/lib/engineer-onboarding";

const account: OnboardingAccount = {
  userId: "00000000-0000-4000-8000-000000000001",
  organizationId: "00000000-0000-4000-8000-000000000002",
  name: "Alex Morgan",
  email: "alex@acme.example",
  company: "Acme",
};

const exampleDraft = (
  patch: Partial<OnboardingDraft> = {},
): OnboardingDraft => ({
  ...emptyDraft(),
  legalName: "Acme, Inc.",
  legalAddress: "123 Example Street\nSan Francisco, CA 94105",
  signerTitle: "CTO",
  context:
    "We're building a support agent that sometimes calls the wrong tool when updating an order.",
  ...patch,
});

const serverState = (
  patch: Partial<EngineerOnboarding> = {},
): EngineerOnboarding => ({
  nda: null,
  slack: null,
  github_installations: [],
  contact_channel: null,
  submitted_at: null,
  ...patch,
});

const signedNda = {
  document_id: "document-1",
  signed_at: "2026-11-01T12:00:00.000Z",
};

const activeSlack = {
  channel_id: "C123",
  channel_name: "ext-acme-gradiated",
  status: "active" as const,
  invited_email: "team@acme.example",
  invited_at: "2026-11-01T12:30:00.000Z",
};

const installation = { id: 42, account: "acme", repository_count: 3 };

describe("onboarding resume", () => {
  it("starts with the introduction until the NDA is recorded", () => {
    expect(resumeView(serverState())).toBe("introduction");
    expect(resumeStep(serverState())).toBe(0);
  });

  it("resumes at Slack and GitHub once the server records the NDA", () => {
    const server = serverState({ nda: signedNda });

    expect(resumeView(server)).toBe("steps");
    expect(resumeStep(server)).toBe(1);
  });

  it("shows the confirmation once the server records the submission", () => {
    expect(
      resumeView(
        serverState({
          nda: signedNda,
          submitted_at: "2026-11-02T09:00:00.000Z",
        }),
      ),
    ).toBe("complete");
  });

  it("restores only form fields from storage", () => {
    const restored = restoreDraft({
      ...exampleDraft(),
      step: 2,
      submitted: true,
      githubInstallationId: 7,
    });

    expect(restored).toEqual(exampleDraft());
    expect(restoreDraft({ channel: "fax" })).toEqual(restoreDraft({}));
  });

  it("scopes stored drafts to user and organization", () => {
    expect(draftStorageKey(account)).toContain(account.userId);
    expect(draftStorageKey(account)).toContain(account.organizationId);
  });
});

describe("onboarding steps", () => {
  it("opens signing for a requested NDA until it is recorded", () => {
    const requested = { ndaRequested: true, installation: null };
    expect(submitAction(0, { ...requested, ndaSigned: false })).toBe("sign");
    expect(submitAction(0, { ...requested, ndaSigned: true })).toBe("advance");
  });

  it("skips signing when no NDA is requested", () => {
    expect(
      submitAction(0, {
        ndaSigned: false,
        ndaRequested: false,
        installation: null,
      }),
    ).toBe("advance");
  });

  it("requires a verified GitHub installation after the NDA", () => {
    expect(
      submitAction(1, {
        ndaSigned: true,
        ndaRequested: true,
        installation: null,
      }),
    ).toBe("github_required");
    expect(
      submitAction(1, { ndaSigned: true, ndaRequested: true, installation }),
    ).toBe("advance");
    expect(
      submitAction(2, { ndaSigned: true, ndaRequested: true, installation }),
    ).toBe("finish");
  });

  it("locks later steps until their prerequisites are verified", () => {
    expect(stepLocked(1, 1, { nda: false, github: false })).toBe(true);
    expect(stepLocked(1, 1, { nda: true, github: false })).toBe(false);
    expect(stepLocked(2, 2, { nda: true, github: false })).toBe(true);
    expect(stepLocked(2, 1, { nda: true, github: true })).toBe(true);
  });

  it("drops the in-progress NDA document when signer details change", () => {
    const draft = exampleDraft();

    expect(changesNda(draft, { legalName: draft.legalName })).toBe(false);
    expect(changesNda(draft, { context: "New" })).toBe(false);
    expect(changesNda(draft, { signerTitle: "CEO" })).toBe(true);
  });

  it("fixes the signer email to the signed-in account", () => {
    expect(
      counterpartyDetails(exampleDraft({ legalName: "" }), account),
    ).toEqual({
      company: "Acme",
      name: "Alex Morgan",
      title: "CTO",
      address: "123 Example Street\nSan Francisco, CA 94105",
      email: account.email,
    });
  });

  it("sends the local NDA document only until the server records one", () => {
    const draft = exampleDraft({
      ndaRequested: true,
      ndaDocumentId: "document-2",
    });

    expect(ndaReference(serverState(), draft)).toBe("document-2");
    expect(
      ndaReference(serverState({ nda: signedNda }), draft),
    ).toBeUndefined();
    expect(
      ndaReference(serverState(), { ...draft, ndaRequested: false }),
    ).toBeUndefined();
  });
});

describe("onboarding submission", () => {
  it("maps the chosen channel, installation and trimmed notes", () => {
    expect(
      engineerSubmission(
        serverState({ nda: signedNda }),
        exampleDraft({ context: "  Context  " }),
        installation,
      ),
    ).toEqual({
      contact_channel: "slack",
      github_installation_id: 42,
      notes: "Context",
    });
  });

  it("omits empty notes and includes an unrecorded NDA document", () => {
    expect(
      engineerSubmission(
        serverState(),
        exampleDraft({
          channel: "email",
          context: " ",
          ndaRequested: true,
          ndaDocumentId: "document-2",
        }),
        installation,
      ),
    ).toEqual({
      contact_channel: "email",
      github_installation_id: 42,
      nda_document_id: "document-2",
    });
  });

  it.each([
    ["nda_required", 0],
    ["github_authorization_required", 1],
    ["github_installation_unverified", 1],
    ["slack_channel_required", 1],
  ])("returns %s conflicts to step %i", (code, step) => {
    expect(submitProblem(code)?.step).toBe(step);
  });

  it("leaves unknown errors to their own message", () => {
    expect(submitProblem(undefined)).toBeUndefined();
    expect(submitProblem("conflict")).toBeUndefined();
  });

  it("maps Slack invitation conflicts by code", () => {
    expect(slackInvitationProblem("slack_channel_name_taken")).toMatchObject({
      renameChannel: true,
    });
    expect(
      slackInvitationProblem("slack_invitation_cooldown")?.message,
    ).toMatch(/10 minutes/);
    expect(slackInvitationProblem("nda_required")).toBeUndefined();
  });
});

describe("onboarding Slack channel", () => {
  it("proposes a channel name Slack accepts from the company name", () => {
    expect(proposedSlackChannel("Acme, Inc.")).toBe("ext-acme-inc-gradiated");
    expect(proposedSlackChannel("Café Société")).toBe(
      "ext-cafe-societe-gradiated",
    );
    expect(proposedSlackChannel("!!!")).toBe("ext-customer-gradiated");
    expect(proposedSlackChannel("a".repeat(200)).length).toBeLessThanOrEqual(
      80,
    );
  });
});

describe("onboarding summary and confirmation", () => {
  it("summarizes the channel from server state", () => {
    expect(
      channelSummary(serverState(), exampleDraft({ channel: "email" })),
    ).toBe("Email fallback · Slack unavailable");
    expect(
      channelSummary(
        serverState({ slack: { ...activeSlack, status: "pending" } }),
        exampleDraft(),
      ),
    ).toBe("Slack invitation not sent yet");
    expect(
      channelSummary(serverState({ slack: activeSlack }), exampleDraft()),
    ).toBe("#ext-acme-gradiated · invitation sent");
  });

  it("points a Slack contact to the invited channel", () => {
    const message = confirmationMessage(
      serverState({ contact_channel: "slack", slack: activeSlack }),
      account.email,
    );

    expect(message.plan).toContain("on Slack");
    expect(message.followUp).toContain("#ext-acme-gradiated");
    expect(message.followUp).toContain("team@acme.example");
  });

  it.each([
    [
      "email contact",
      serverState({ contact_channel: "email", slack: activeSlack }),
    ],
    [
      "a pending Slack channel",
      serverState({
        contact_channel: "slack",
        slack: { ...activeSlack, status: "pending" },
      }),
    ],
  ])("does not mention Slack for %s", (_label, server) => {
    const message = confirmationMessage(server, account.email);

    expect(message.plan).toContain("email a plan to alex@acme.example");
    expect(message.plan + message.followUp).not.toMatch(/slack/i);
  });
});

const membership = (
  patch: Partial<CurrentUser["organizations"][number]>,
): CurrentUser["organizations"][number] => ({
  id: "00000000-0000-4000-8000-000000000001",
  name: "Acme",
  status: "active",
  role: "admin",
  default_workspace_id: "00000000-0000-4000-8000-000000000002",
  auto_join_domain: null,
  onboarding_completed: true,
  ...patch,
});

const user = (...organizations: CurrentUser["organizations"]): CurrentUser => ({
  id: "00000000-0000-4000-8000-000000000003",
  name: "Alex Morgan",
  email: "alex@acme.example",
  email_verified: true,
  impersonation_expires_at: null,
  impersonated_by: null,
  is_staff: false,
  company_email_domain: "acme.example",
  image_url: null,
  created_at: "2026-10-14T00:00:00Z",
  organizations,
});

describe("onboarding account", () => {
  it("asks which organization when several are active", () => {
    const first = membership({ id: "first" });
    const second = membership({ id: "second" });

    expect(chooseAccount(user(first, second), undefined)).toEqual({
      kind: "pick",
      organizations: [first, second],
    });
  });

  it("uses the requested active organization", () => {
    expect(
      chooseAccount(
        user(membership({ id: "first" }), membership({ id: "second" })),
        "second",
      ),
    ).toMatchObject({ kind: "ready", account: { organizationId: "second" } });
  });

  it("rejects a requested organization that is not an active membership", () => {
    expect(
      chooseAccount(
        user(membership({ id: "first", status: "suspended" })),
        "first",
      ),
    ).toEqual({ kind: "missing" });
  });
});
