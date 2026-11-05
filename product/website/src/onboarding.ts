import { z } from "zod";

export const onboardingStorageKey = "gradiated-onboarding-preview-v3";

export const mutualNda = {
  templateUrl:
    "https://docs.google.com/document/d/1K-1ErUrHbvNs8ed8CXSQIuA0xJdg55sC/edit",
  company: "PostHog Inc.",
  signer: "James Hawkins",
  title: "Co-CEO",
  address: "PostHog Inc., 2261 Market Street #4008\nSan Francisco, CA 94114",
} as const;

export const onboardingSchema = z.object({
  introduced: z.boolean().default(false),
  ndaDocumentId: z.string().max(100).nullable().default(null),
  context: z.string().max(3000).default(""),
  name: z.string().max(100).default(""),
  email: z.string().max(200).default(""),
  company: z.string().max(200).default(""),
  channel: z.enum(["slack", "email"]).default("slack"),
  slack: z.string().max(200).default(""),
  slackEmail: z.string().max(200).nullable().default(null),
  slackDeliveryMode: z.enum(["simulated", "live"]).nullable().default(null),
  slackStatus: z.enum(["not_sent", "invited", "joined"]).default("not_sent"),
  legalName: z.string().max(200).default(""),
  legalAddress: z.string().max(1000).default(""),
  signerName: z.string().max(100).nullable().default(null),
  signerTitle: z.string().max(100).default(""),
  signerEmail: z.string().max(200).nullable().default(null),
  repository: z.string().max(300).default(""),
  step: z.number().int().min(0).max(3).default(0),
  submitted: z.boolean().default(false),
});

export type OnboardingDraft = z.infer<typeof onboardingSchema>;

export const onboardingAccountSchema = z.object({
  userId: z.uuid(),
  organizationId: z.uuid(),
  name: z.string().max(100),
  email: z.email(),
  company: z.string().trim().min(1).max(200),
});

export type OnboardingAccount = z.infer<typeof onboardingAccountSchema>;

export const accountStorageKey = (account: OnboardingAccount) =>
  onboardingStorageKey +
  ":" +
  encodeURIComponent(account.userId) +
  ":" +
  encodeURIComponent(account.organizationId);

export const reuseAccount = (
  draft: OnboardingDraft,
  account: OnboardingAccount,
): OnboardingDraft => ({
  ...draft,
  name: account.name,
  email: account.email,
  company: account.company,
  legalName: draft.legalName || account.company,
  ...(draft.email !== account.email || draft.company !== account.company
    ? { slack: "", slackStatus: "not_sent" as const }
    : {}),
});

export const emptyOnboarding = (): OnboardingDraft =>
  onboardingSchema.parse({});

export const counterpartyDetails = (draft: OnboardingDraft) => ({
  company: draft.legalName,
  name: draft.signerName ?? draft.name,
  title: draft.signerTitle ?? "",
  address: draft.legalAddress ?? "",
  email: draft.signerEmail ?? draft.email,
});

export const firstIncompleteStep = (draft: OnboardingDraft): number | null => {
  const signer = counterpartyDetails(draft);

  if (
    !signer.company.trim() ||
    !signer.address.trim() ||
    !signer.name.trim() ||
    !signer.title.trim() ||
    !z.email().safeParse(signer.email.trim()).success
  )
    return 0;

  if (
    !draft.company.trim() ||
    !z.email().safeParse(draft.email.trim()).success ||
    !draft.repository.trim()
  )
    return 1;

  return null;
};

export const exampleOnboarding = (): OnboardingDraft => ({
  ...emptyOnboarding(),
  introduced: true,
  context:
    "We're building a support agent. It answers questions well, but sometimes calls the wrong tool when updating an order. We'd like to fix that, then see if we can run it on a cheaper model.",
  name: "Alex Morgan",
  email: "alex@acme.example",
  company: "Acme",
  slack: "",
  legalName: "Acme, Inc.",
  legalAddress: "123 Example Street\nSan Francisco, CA 94105",
  signerName: "Alex Morgan",
  signerTitle: "CTO",
  signerEmail: "alex@acme.example",
  repository: "acme/support-agent",
});
