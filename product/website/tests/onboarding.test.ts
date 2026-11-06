import { describe, expect, it, vi } from "vitest";
import {
  emptyOnboarding,
  exampleOnboarding,
  onboardingSchema,
  counterpartyDetails,
  firstIncompleteStep,
  accountStorageKey,
  reuseAccount,
  restoreOnboardingDraft,
  verifyOnboardingResume,
} from "../src/onboarding";

describe("onboarding recovery", () => {
  const account = {
    userId: "user-1",
    organizationId: "org-1",
    name: "Alex Morgan",
    email: "alex@acme.example",
    company: "Acme",
  };
  const saved = {
    ...exampleOnboarding(),
    ndaDocumentId: "test-document",
    step: 2,
  };
  const providers = () => ({
    readNda: vi.fn().mockResolvedValue({ status: "completed" }),
    githubInstalled: vi.fn().mockResolvedValue(true),
  });

  it("restores the saved review step and notes", () => {
    expect(restoreOnboardingDraft(saved, account)).toMatchObject({
      step: 2,
      context: saved.context,
      ndaDocumentId: saved.ndaDocumentId,
    });
  });
  it("preserves completed setup instead of restarting the wizard", async () => {
    const draft = restoreOnboardingDraft(
      { ...saved, step: 3, submitted: true },
      account,
    );
    const checks = providers();
    expect(await verifyOnboardingResume(draft, checks)).toMatchObject({
      draft: { step: 3, submitted: true },
      ndaVerified: true,
      githubVerified: true,
    });
    expect(checks.githubInstalled).toHaveBeenCalledWith(
      saved.githubInstallationId,
    );
  });
  it("does not trust saved completion without an NDA reference", () => {
    expect(
      restoreOnboardingDraft(
        { ...saved, ndaDocumentId: null, step: 3, submitted: true },
        account,
      ),
    ).toMatchObject({ step: 0, submitted: false });
  });
  it("binds legacy signer email to the authenticated account and discards its mismatched NDA", () => {
    expect(
      restoreOnboardingDraft(
        { ...saved, signerEmail: "another@acme.example" },
        account,
      ),
    ).toMatchObject({
      signerEmail: account.email,
      ndaDocumentId: null,
      step: 0,
      submitted: false,
    });
  });
  it("keeps an existing NDA when signer emails differ only in case", () => {
    expect(
      restoreOnboardingDraft(
        { ...saved, signerEmail: "ALEX@ACME.EXAMPLE" },
        account,
      ),
    ).toMatchObject({
      ndaDocumentId: saved.ndaDocumentId,
      step: 2,
      signerEmail: account.email,
    });
  });
  it("returns to signing when PandaDoc no longer confirms completion", async () => {
    const checks = providers();
    checks.readNda.mockResolvedValue({ status: "ready" });
    expect(
      await verifyOnboardingResume(
        { ...saved, step: 3, submitted: true },
        checks,
      ),
    ).toMatchObject({
      draft: { step: 0, submitted: false },
      ndaVerified: false,
      githubVerified: false,
    });
    expect(checks.githubInstalled).not.toHaveBeenCalled();
  });
  it("returns to GitHub when installation access has been revoked", async () => {
    const checks = providers();
    checks.githubInstalled.mockResolvedValue(false);
    expect(
      await verifyOnboardingResume(
        { ...saved, step: 3, submitted: true },
        checks,
      ),
    ).toMatchObject({
      draft: { step: 1, submitted: false },
      ndaVerified: true,
      githubVerified: false,
    });
  });
  it("keeps saved progress intact on provider failure so restoration can be retried", async () => {
    const checks = providers();
    checks.readNda.mockRejectedValue(new Error("Provider unavailable"));
    const draft = { ...saved, step: 3, submitted: true };
    await expect(verifyOnboardingResume(draft, checks)).rejects.toThrow(
      "Provider unavailable",
    );
    expect(draft).toMatchObject({
      step: 3,
      submitted: true,
      ndaDocumentId: saved.ndaDocumentId,
    });
  });
  it("resumes after the NDA without trusting a cached GitHub installation", async () => {
    const checks = providers();
    expect(
      await verifyOnboardingResume({ ...saved, step: 0 }, checks),
    ).toMatchObject({
      draft: { step: 1 },
      ndaVerified: true,
      githubVerified: false,
    });
    expect(checks.githubInstalled).not.toHaveBeenCalled();
  });
});

describe("local preview drafts", () => {
  it("does not treat a legacy repository entry as an app installation", () => {
    const draft = onboardingSchema.parse({
      ...exampleOnboarding(),
      githubInstallationId: null,
      repository: "acme/legacy",
    });
    expect(firstIncompleteStep(draft)).toBe(1);
  });
  it("stores a separate Slack recipient without changing the NDA signer", () => {
    const draft = onboardingSchema.parse({
      ...exampleOnboarding(),
      signerEmail: "legal@acme.example",
      slackEmail: "engineering@acme.example",
    });
    expect(draft.slackEmail).toBe("engineering@acme.example");
    expect(counterpartyDetails(draft).email).toBe("legal@acme.example");
    expect(emptyOnboarding().slackEmail).toBeNull();
  });
  it("allows setup to finish with no project description or context note", () => {
    expect(
      firstIncompleteStep({ ...exampleOnboarding(), context: "" }),
    ).toBeNull();
  });
  it("reuses account identity rather than asking for it again or trusting a stale draft", () => {
    const account = {
      userId: "user-1",
      organizationId: "org-1",
      name: "Sam",
      email: "sam@new.example",
      company: "New company",
    };
    const draft = reuseAccount(exampleOnboarding(), account);
    expect(draft).toMatchObject({
      name: "Sam",
      email: "sam@new.example",
      company: "New company",
    });
    expect(reuseAccount(emptyOnboarding(), account).legalName).toBe(
      "New company",
    );
    expect(accountStorageKey(account)).not.toBe(
      accountStorageKey({ ...account, userId: "user-2" }),
    );
    expect(accountStorageKey(account)).not.toBe(
      accountStorageKey({ ...account, organizationId: "org-2" }),
    );
  });
  it("requires a GitHub installation even when Slack is unavailable", () => {
    const emailFallback = {
      ...exampleOnboarding(),
      channel: "email" as const,
      slack: "",
    };
    expect(firstIncompleteStep(emailFallback)).toBeNull();
    expect(
      firstIncompleteStep({ ...emailFallback, githubInstallationId: null }),
    ).toBe(1);
  });

  it("allows Slack acceptance to remain pending while requiring actual NDA signer fields", () => {
    expect(
      firstIncompleteStep({ ...exampleOnboarding(), slack: "" }),
    ).toBeNull();
    expect(
      firstIncompleteStep({ ...exampleOnboarding(), signerTitle: "" }),
    ).toBe(0);
    expect(
      firstIncompleteStep({ ...exampleOnboarding(), legalAddress: "" }),
    ).toBe(0);
    expect(
      firstIncompleteStep({
        ...exampleOnboarding(),
        signerEmail: "not-an-email",
      }),
    ).toBe(0);
  });

  it("round trips progress and the handoff through browser storage", () => {
    const draft = { ...exampleOnboarding(), step: 3, submitted: true };
    expect(onboardingSchema.parse(JSON.parse(JSON.stringify(draft)))).toEqual(
      draft,
    );
  });

  it("shows the introduction first and checks NDA details before connection details", () => {
    expect(emptyOnboarding()).toMatchObject({
      introduced: false,
      step: 0,
      email: "",
      context: "",
      submitted: false,
    });
    expect(firstIncompleteStep(emptyOnboarding())).toBe(0);
    expect(
      firstIncompleteStep({
        ...exampleOnboarding(),
        signerTitle: "",
        githubInstallationId: null,
      }),
    ).toBe(0);
  });

  it("rejects invalid stored steps", () => {
    expect(onboardingSchema.safeParse({ step: 4 }).success).toBe(false);
  });

  it("pre-fills the signer from the project contact until a different signer is supplied", () => {
    const draft = {
      ...emptyOnboarding(),
      name: "Alex Morgan",
      email: "alex@acme.example",
    };
    expect(counterpartyDetails(draft)).toMatchObject({
      name: "Alex Morgan",
      email: "alex@acme.example",
    });
    expect(
      counterpartyDetails({
        ...draft,
        signerName: "Sam Lee",
        signerTitle: "CEO",
        signerEmail: "sam@acme.example",
      }),
    ).toMatchObject({
      name: "Sam Lee",
      title: "CEO",
      email: "sam@acme.example",
    });
  });

  it("allows signer fields to be cleared rather than silently restoring a contact", () => {
    expect(
      counterpartyDetails({
        ...exampleOnboarding(),
        signerName: "",
        signerEmail: "",
      }),
    ).toMatchObject({ name: "", email: "" });
  });
});
