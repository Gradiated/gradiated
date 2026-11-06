import { GithubAppInstall } from "../GithubAppInstall";
import { SlackConnectInvite } from "../SlackConnectInvite";
import type { EngineerOnboarding } from "../../api/engineer-onboarding";
import { channelSummary, ndaReference, slackInvited } from "../../onboarding";
import type {
  OnboardingAccount,
  OnboardingDraft,
  VerifiedInstallation,
} from "../../onboarding";
import { Field, StepTitle } from "./OnboardingParts";

export type UpdateDraft = (values: Partial<OnboardingDraft>) => void;

const ndaLabel = "Mutual NDA with PostHog Inc.";

const accessLabel = (installation: VerifiedInstallation | null) =>
  installation
    ? `GitHub app installed · ${installation.account}`
    : "GitHub app installation required";

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
  onRefresh: () => Promise<void>;
  onGithubVerified: (installation: VerifiedInstallation | null) => void;
}) => (
  <>
    <StepTitle title="Set up Slack & GitHub.">
      A shared channel for the conversation. Repository access for the work.
    </StepTitle>
    <GithubAppInstall
      organizationId={account.organizationId}
      ndaDocumentId={ndaReference(server, draft)}
      saved={installation}
      onVerified={onGithubVerified}
    />
    {draft.channel === "slack" && (
      <SlackConnectInvite
        account={account}
        server={server}
        draft={draft}
        patch={patch}
        onInvited={onRefresh}
      />
    )}
    <label className="gs-email-fallback">
      <input
        type="checkbox"
        checked={draft.channel === "email"}
        onChange={(event) =>
          patch({ channel: event.target.checked ? "email" : "slack" })
        }
      />
      <span>Our team can’t use Slack — use email instead.</span>
    </label>
  </>
);

export const AccessStep = ({
  account,
  draft,
  patch,
}: {
  account: OnboardingAccount;
  draft: OnboardingDraft;
  patch: UpdateDraft;
}) => (
  <>
    <StepTitle title="Your mutual NDA.">
      Confirm your company details and who will sign.
    </StepTitle>
    <Field label="Legal company name">
      <input
        required
        value={draft.legalName || account.company}
        maxLength={200}
        onChange={(event) => patch({ legalName: event.target.value })}
        placeholder="Acme, Inc."
      />
    </Field>
    <div className="gs-field-pair">
      <Field label="Signer’s full name">
        <input
          required
          value={draft.signerName ?? account.name}
          maxLength={100}
          onChange={(event) => patch({ signerName: event.target.value })}
          placeholder="Alex Morgan"
        />
      </Field>
      <Field label="Signer’s title">
        <input
          required
          value={draft.signerTitle}
          maxLength={100}
          onChange={(event) => patch({ signerTitle: event.target.value })}
          placeholder="CTO"
        />
      </Field>
    </div>
    <Field
      label="Signer’s email"
      hint="The signer must be the signed-in organization admin. To use a different email, sign in with that account."
    >
      <input
        required
        type="email"
        value={account.email}
        maxLength={200}
        readOnly
        placeholder="signer@company.com"
      />
    </Field>
    <Field label="Company address">
      <textarea
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
  <>
    <StepTitle title="Let’s get to work.">
      Your engineer will pick this up async.
    </StepTitle>
    <div className="gs-review-heading">
      <h2>{account.company} × Gradiated</h2>
      <button type="button" className="gs-text-button" onClick={onEdit}>
        Edit setup
      </button>
    </div>
    <dl className="gs-summary">
      <div>
        <dt>Contact</dt>
        <dd>{account.email}</dd>
      </div>
      <div>
        <dt>Channel</dt>
        <dd>{channelSummary(server, draft)}</dd>
      </div>
      <div>
        <dt>NDA</dt>
        <dd>{ndaLabel}</dd>
      </div>
      <div>
        <dt>Access</dt>
        <dd>{accessLabel(installation)}</dd>
      </div>
    </dl>
    <h3 className="gs-next-heading">What happens next</h3>
    <ol className="gs-next-list">
      <li>
        <span>1</span>Meet your researcher in{" "}
        {draft.channel === "slack" ? "Slack" : "email"}
      </li>
      <li>
        <span>2</span>Review your codebase together
      </li>
      <li>
        <span>3</span>
        Pick a test case together
      </li>
    </ol>
    <Field
      label="Anything else you’d like us to know or have as context? (optional)"
      hint={
        draft.channel === "slack" && slackInvited(server)
          ? "We’ll share these in your Slack channel as notes from onboarding when you start the project."
          : undefined
      }
    >
      <textarea
        rows={4}
        maxLength={3000}
        value={draft.context}
        onChange={(event) => patch({ context: event.target.value })}
      />
    </Field>
  </>
);
