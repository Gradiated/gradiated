import { describe, expect, it } from "vitest";
import type { EngineerOnboarding } from "@/api/engineer-onboarding";
import type { CurrentUser } from "@/api/queries";
import {
  githubLinkProblem,
  changesNda,
  chooseAccount,
  confirmationMessage,
  counterpartyDetails,
  draftStorageKey,
  emptyDraft,
  engineerSubmission,
  ndaPending,
  ndaReference,
  proposedSlackChannel,
  restoreDraft,
  slackInvitationProblem,
  startBlockers,
  submitProblem,
  type OnboardingAccount,
  type OnboardingDraft,
  githubInstallUrl,
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

describe("onboarding draft", () => {
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

describe("starting the project", () => {
  it("lists what still blocks the start, in page order", () => {
    expect(startBlockers(serverState(), exampleDraft(), null)).toEqual([
      { section: "code", label: "Install the GitHub app" },
      { section: "contact", label: "Send the Slack invite, or choose email" },
    ]);
    expect(
      startBlockers(serverState(), exampleDraft({ channel: "email" }), {
        ...installation,
        repository_count: 0,
      }),
    ).toEqual([{ section: "code", label: "Select a repository on GitHub" }]);
    expect(
      startBlockers(serverState(), exampleDraft({ channel: "email" }), null, 3),
    ).toEqual([
      { section: "code", label: "Choose the GitHub account for this project" },
    ]);
    expect(
      startBlockers(
        serverState({ slack: activeSlack }),
        exampleDraft(),
        installation,
      ),
    ).toEqual([]);
  });

  it("signs a requested NDA as part of starting, until it is recorded", () => {
    const requested = exampleDraft({ ndaRequested: true });

    expect(ndaPending(serverState(), requested)).toBe(true);
    expect(ndaPending(serverState({ nda: signedNda }), requested)).toBe(false);
    expect(ndaPending(serverState(), exampleDraft())).toBe(false);
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
    ["nda_required", "nda"],
    ["github_authorization_required", "code"],
    ["github_installation_unverified", "code"],
    ["github_repositories_required", "code"],
    ["slack_channel_required", "contact"],
  ])("points %s conflicts at the %s section", (code, section) => {
    expect(submitProblem(code)?.section).toBe(section);
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
    ).toMatch(/30 seconds/);
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
  it("points a Slack contact to the invited channel", () => {
    const message = confirmationMessage(
      serverState({ contact_channel: "slack", slack: activeSlack }),
      account.email,
    );

    expect(message.plan).toContain("in #ext-acme-gradiated");
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

    expect(message.plan).toContain("emails a plan to alex@acme.example");
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

  it("offers only organizations the user administers", () => {
    const admin = membership({ id: "admin" });
    const member = membership({ id: "member", role: "member" });

    expect(chooseAccount(user(member, admin), undefined)).toMatchObject({
      kind: "ready",
      account: { organizationId: "admin" },
    });
  });

  it("tells a member to ask an admin rather than failing part way", () => {
    const member = membership({ id: "member", name: "Acme", role: "member" });

    expect(chooseAccount(user(member), undefined)).toEqual({
      kind: "not_admin",
      organization: "Acme",
    });
    expect(chooseAccount(user(member), "member")).toEqual({
      kind: "not_admin",
      organization: "Acme",
    });
  });
});

describe("GitHub installation link", () => {
  it("carries the linking state onto the app installation", () => {
    expect(
      githubInstallUrl(
        "https://github.com/login/oauth/authorize?client_id=x&state=abc&code_challenge=y",
      ),
    ).toBe("https://github.com/apps/gradiated/installations/new?state=abc");
  });

  it("rejects an authorization URL that is not GitHub's or has no state", () => {
    expect(() =>
      githubInstallUrl("https://evil.example/login/oauth/authorize?state=abc"),
    ).toThrow();
    expect(() =>
      githubInstallUrl("https://github.com/login/oauth/authorize"),
    ).toThrow();
  });
});

describe("GitHub link problems", () => {
  it("explains a GitHub account that belongs to another user", () => {
    expect(
      githubLinkProblem("account_already_linked_to_different_user"),
    ).toMatch(/already connected to a different Gradiated account/);
    expect(githubLinkProblem("access_denied")).toMatch(
      /Install GitHub app again/,
    );
  });
});
