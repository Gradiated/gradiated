import { describe, expect, it } from "vitest";
import {
  emptyOnboarding,
  exampleOnboarding,
  onboardingSchema,
  counterpartyDetails,
  firstIncompleteStep,
  accountStorageKey,
  reuseAccount,
} from "../src/onboarding";

describe("local preview drafts", () => {
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
  it("requires a repository even when Slack is unavailable", () => {
    const emailFallback = {
      ...exampleOnboarding(),
      channel: "email" as const,
      slack: "",
    };
    expect(firstIncompleteStep(emailFallback)).toBeNull();
    expect(firstIncompleteStep({ ...emailFallback, repository: "" })).toBe(1);
  });

  it("requires Slack details on the preferred path and the actual NDA signer fields", () => {
    expect(firstIncompleteStep({ ...exampleOnboarding(), slack: "" })).toBe(1);
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
        repository: "",
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
