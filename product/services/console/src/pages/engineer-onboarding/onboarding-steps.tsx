import type { ReactNode } from "react";

import type { EngineerOnboarding } from "@/api/engineer-onboarding";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  channelSummary,
  slackInvited,
  type OnboardingAccount,
  type OnboardingDraft,
  type VerifiedInstallation,
} from "@/lib/engineer-onboarding";
import { GithubAppInstallation } from "@/pages/engineer-onboarding/github-installation";
import { SlackInvitation } from "@/pages/engineer-onboarding/slack-invitation";

export type UpdateDraft = (values: Partial<OnboardingDraft>) => void;

export const StepTitle = ({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) => (
  <div className="flex flex-col gap-2">
    <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
    <p className="text-sm leading-6 text-muted-foreground">{children}</p>
  </div>
);

export const NdaStep = ({
  account,
  draft,
  patch,
}: {
  account: OnboardingAccount;
  draft: OnboardingDraft;
  patch: UpdateDraft;
}) => (
  <FieldGroup>
    <StepTitle title="Do you need an NDA?">
      Optional. We can sign a mutual NDA before you share your code.
    </StepTitle>
    <Field orientation="horizontal">
      <Checkbox
        id="nda-requested"
        checked={draft.ndaRequested}
        onCheckedChange={(checked) => patch({ ndaRequested: checked === true })}
      />
      <FieldLabel htmlFor="nda-requested">
        We’d like a mutual NDA first
      </FieldLabel>
    </Field>
    {draft.ndaRequested ? (
      <NdaFields account={account} draft={draft} patch={patch} />
    ) : null}
  </FieldGroup>
);

const NdaFields = ({
  account,
  draft,
  patch,
}: {
  account: OnboardingAccount;
  draft: OnboardingDraft;
  patch: UpdateDraft;
}) => (
  <>
    <Field>
      <FieldLabel htmlFor="nda-company">Legal company name</FieldLabel>
      <Input
        id="nda-company"
        required
        value={draft.legalName || account.company}
        maxLength={200}
        onChange={(event) => patch({ legalName: event.target.value })}
        placeholder="Acme, Inc."
      />
    </Field>
    <div className="grid gap-7 sm:grid-cols-2">
      <Field>
        <FieldLabel htmlFor="nda-signer-name">Signer’s full name</FieldLabel>
        <Input
          id="nda-signer-name"
          required
          value={draft.signerName ?? account.name}
          maxLength={100}
          onChange={(event) => patch({ signerName: event.target.value })}
          placeholder="Alex Morgan"
        />
      </Field>
      <Field>
        <FieldLabel htmlFor="nda-signer-title">Signer’s title</FieldLabel>
        <Input
          id="nda-signer-title"
          required
          value={draft.signerTitle}
          maxLength={100}
          onChange={(event) => patch({ signerTitle: event.target.value })}
          placeholder="CTO"
        />
      </Field>
    </div>
    <Field>
      <FieldLabel htmlFor="nda-signer-email">Signer’s email</FieldLabel>
      <Input
        id="nda-signer-email"
        type="email"
        value={account.email}
        readOnly
      />
      <FieldDescription>
        The signer must be the signed-in organization admin. To use a different
        email, sign in with that account.
      </FieldDescription>
    </Field>
    <Field>
      <FieldLabel htmlFor="nda-address">Company address</FieldLabel>
      <Textarea
        id="nda-address"
        required
        rows={2}
        maxLength={1000}
        value={draft.legalAddress}
        onChange={(event) => patch({ legalAddress: event.target.value })}
        placeholder="Street address, city, state / region, postal code, country"
      />
    </Field>
  </>
);

export const TeamStep = ({
  account,
  server,
  draft,
  patch,
  installation,
  onRefresh,
  onGithubVerified,
}: {
  account: OnboardingAccount;
  server: EngineerOnboarding;
  draft: OnboardingDraft;
  patch: UpdateDraft;
  installation: VerifiedInstallation | null;
  onRefresh: () => Promise<unknown>;
  onGithubVerified: (installation: VerifiedInstallation | null) => void;
}) => (
  <FieldGroup>
    <StepTitle title="Set up Slack & GitHub">
      A shared channel for the conversation. Repository access for the work.
    </StepTitle>
    <GithubAppInstallation
      organizationId={account.organizationId}
      saved={installation}
      onVerified={onGithubVerified}
    />
    {draft.channel === "slack" ? (
      <SlackInvitation
        account={account}
        server={server}
        draft={draft}
        patch={patch}
        onInvited={onRefresh}
      />
    ) : null}
    <Field orientation="horizontal">
      <Checkbox
        id="email-fallback"
        checked={draft.channel === "email"}
        onCheckedChange={(checked) =>
          patch({ channel: checked === true ? "email" : "slack" })
        }
      />
      <FieldLabel htmlFor="email-fallback">
        Our team can’t use Slack — use email instead.
      </FieldLabel>
    </Field>
  </FieldGroup>
);

export const ReviewStep = ({
  account,
  server,
  draft,
  installation,
  onEdit,
  patch,
}: {
  account: OnboardingAccount;
  server: EngineerOnboarding;
  draft: OnboardingDraft;
  installation: VerifiedInstallation | null;
  onEdit: () => void;
  patch: UpdateDraft;
}) => (
  <FieldGroup>
    <StepTitle title="Let’s get to work">
      Your engineer will pick this up async.
    </StepTitle>
    <div className="flex items-center justify-between gap-3">
      <h2 className="font-semibold">{account.company} × Gradiated</h2>
      <Button
        type="button"
        variant="link"
        className="h-auto p-0"
        onClick={onEdit}
      >
        Edit setup
      </Button>
    </div>
    <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 rounded-lg border p-4 text-sm">
      <dt className="text-muted-foreground">Contact</dt>
      <dd>{account.email}</dd>
      <dt className="text-muted-foreground">Channel</dt>
      <dd>{channelSummary(server, draft)}</dd>
      <dt className="text-muted-foreground">NDA</dt>
      <dd>{server.nda ? "Mutual NDA with PostHog Inc." : "Not requested"}</dd>
      <dt className="text-muted-foreground">Access</dt>
      <dd>
        {installation
          ? `GitHub app installed · ${installation.account}`
          : "GitHub app installation required"}
      </dd>
    </dl>
    <div className="flex flex-col gap-2">
      <h3 className="text-sm font-semibold">What happens next</h3>
      <ol className="list-inside list-decimal text-sm leading-7">
        <li>
          Meet your researcher in{" "}
          {draft.channel === "slack" ? "Slack" : "email"}
        </li>
        <li>Review your codebase together</li>
        <li>Pick a test case together</li>
      </ol>
    </div>
    <Field>
      <FieldLabel htmlFor="onboarding-notes">
        Anything else you’d like us to know or have as context? (optional)
      </FieldLabel>
      <Textarea
        id="onboarding-notes"
        rows={4}
        maxLength={3000}
        value={draft.context}
        onChange={(event) => patch({ context: event.target.value })}
      />
      {draft.channel === "slack" && slackInvited(server) ? (
        <FieldDescription>
          We’ll share these in your Slack channel as notes from onboarding when
          you start the project.
        </FieldDescription>
      ) : null}
    </Field>
  </FieldGroup>
);
