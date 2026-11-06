import type { EngineerOnboarding } from "../src/api/engineer-onboarding";
import { emptyOnboarding } from "../src/onboarding";
import type { OnboardingAccount, OnboardingDraft } from "../src/onboarding";

export const account: OnboardingAccount = {
  userId: "00000000-0000-4000-8000-000000000001",
  organizationId: "00000000-0000-4000-8000-000000000002",
  name: "Alex Morgan",
  email: "alex@acme.example",
  company: "Acme",
};

export const exampleDraft = (
  patch: Partial<OnboardingDraft> = {},
): OnboardingDraft => ({
  ...emptyOnboarding(),
  legalName: "Acme, Inc.",
  legalAddress: "123 Example Street\nSan Francisco, CA 94105",
  signerTitle: "CTO",
  context:
    "We're building a support agent that sometimes calls the wrong tool when updating an order.",
  ...patch,
});

export const serverState = (
  patch: Partial<EngineerOnboarding> = {},
): EngineerOnboarding => ({
  nda: null,
  slack: null,
  github_installations: [],
  contact_channel: null,
  submitted_at: null,
  ...patch,
});

export const signedNda = {
  document_id: "document-1",
  signed_at: "2026-11-01T12:00:00.000Z",
};

export const activeSlack = {
  channel_id: "C123",
  channel_name: "ext-acme-gradiated",
  status: "active" as const,
  invited_email: "team@acme.example",
  invited_at: "2026-11-01T12:30:00.000Z",
};

export const installation = { id: 42, account: "acme", repository_count: 3 };
