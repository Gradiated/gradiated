import { Check, CircleAlert, LoaderCircle } from "lucide-react";
import type { ReactNode } from "react";

import type { EngineerOnboarding } from "@/api/engineer-onboarding";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  codeSummary,
  confirmationMessage,
  contactSummary,
  ndaSummary,
  proposedSlackChannel,
  sectionId,
  slackInvited,
  type OnboardingAccount,
  type OnboardingDraft,
  type OnboardingSection,
  type VerifiedInstallation,
} from "@/lib/engineer-onboarding";

export type UpdateDraft = (values: Partial<OnboardingDraft>) => void;

export const Eyebrow = ({ children }: { children: ReactNode }) => (
  <span className="font-mono text-xs uppercase tracking-wide text-muted-foreground">
    {children}
  </span>
);

export const PageHeader = ({
  eyebrow,
  title,
  children,
}: {
  eyebrow: ReactNode;
  title: string;
  children?: ReactNode;
}) => (
  <header className="flex max-w-3xl flex-col gap-4">
    <Eyebrow>{eyebrow}</Eyebrow>
    <h1 className="text-4xl font-semibold tracking-tight text-balance md:text-6xl">
      {title}
    </h1>
    {children ? (
      <p className="max-w-2xl text-lg leading-8 text-muted-foreground">
        {children}
      </p>
    ) : null}
  </header>
);

export const Section = ({
  section,
  title,
  optional,
  invalid,
  children,
}: {
  section?: OnboardingSection;
  title: string;
  optional?: boolean;
  invalid?: boolean;
  children: ReactNode;
}) => (
  <section
    id={section ? sectionId(section) : undefined}
    aria-labelledby={section ? `${sectionId(section)}-title` : undefined}
    tabIndex={-1}
    className={
      "flex scroll-mt-6 flex-col gap-4 rounded-lg border bg-card p-6 outline-none md:p-8" +
      (invalid ? " border-destructive/40" : "")
    }
  >
    <h2
      id={section ? `${sectionId(section)}-title` : undefined}
      className="flex items-baseline gap-2.5 text-xl font-semibold tracking-tight"
    >
      {title}
      {optional ? (
        <span className="text-sm font-normal text-muted-foreground">
          Optional
        </span>
      ) : null}
    </h2>
    {children}
  </section>
);

export const NdaSection = ({
  account,
  server,
  draft,
  patch,
}: {
  account: OnboardingAccount;
  server: EngineerOnboarding;
  draft: OnboardingDraft;
  patch: UpdateDraft;
}) => (
  <Section section="nda" title="Mutual NDA" optional>
    {server.nda ? (
      <p role="status" className="flex items-center gap-2 text-sm">
        <Check className="size-4 text-emerald-600" />
        Signed with PostHog Inc. on{" "}
        {new Date(server.nda.signed_at).toLocaleDateString()}
      </p>
    ) : (
      <>
        <Field orientation="horizontal">
          <Checkbox
            id="nda-requested"
            checked={draft.ndaRequested}
            onCheckedChange={(checked) =>
              patch({ ndaRequested: checked === true })
            }
          />
          <FieldLabel htmlFor="nda-requested">
            We’d like a mutual NDA first
          </FieldLabel>
        </Field>
        {draft.ndaRequested ? (
          <>
            <NdaFields account={account} draft={draft} patch={patch} />
            <p className="text-sm text-muted-foreground">
              You’ll sign it with PostHog Inc. when you start the project.
              Changing these details later prepares a new copy.
            </p>
          </>
        ) : null}
      </>
    )}
  </Section>
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
  <div className="grid gap-5 sm:grid-cols-2">
    <Field className="sm:col-span-2">
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
    <Field className="sm:col-span-2">
      <FieldLabel htmlFor="nda-signer-email">Signer’s email</FieldLabel>
      <Input
        id="nda-signer-email"
        type="email"
        value={account.email}
        readOnly
        className="bg-muted text-muted-foreground"
      />
      <FieldDescription>
        The signer must be the signed-in organization admin. To use a different
        email, sign in with that account.
      </FieldDescription>
    </Field>
    <Field className="sm:col-span-2">
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
  </div>
);

export const ContextSection = ({
  server,
  draft,
  patch,
}: {
  server: EngineerOnboarding;
  draft: OnboardingDraft;
  patch: UpdateDraft;
}) => (
  <Section title="Context" optional>
    <Field>
      <FieldLabel
        htmlFor="onboarding-notes"
        className="font-normal text-muted-foreground"
      >
        Goals, constraints, deadlines — anything your researcher should know.
      </FieldLabel>
      <Textarea
        id="onboarding-notes"
        rows={3}
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
  </Section>
);

const Summary = ({ rows }: { rows: [string, ReactNode][] }) => (
  <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2.5 text-sm">
    {rows.map(([label, value]) => (
      <div key={label} className="contents">
        <dt className="text-muted-foreground">{label}</dt>
        <dd className="text-right">{value}</dd>
      </div>
    ))}
  </dl>
);

export const ProjectPanel = ({
  account,
  server,
  draft,
  installation,
  blockers,
  ndaPending,
  submitting,
  error,
  onStart,
  onGoTo,
}: {
  account: OnboardingAccount;
  server: EngineerOnboarding;
  draft: OnboardingDraft;
  installation: VerifiedInstallation | null;
  blockers: { section: OnboardingSection; label: string }[];
  ndaPending: boolean;
  submitting: boolean;
  error: { message: string; section?: OnboardingSection } | null;
  onStart: () => void;
  onGoTo: (section: OnboardingSection) => void;
}) => {
  const where =
    draft.channel === "email"
      ? `By email at ${account.email}`
      : `In #${server.slack?.channel_name ?? draft.slackChannelName ?? proposedSlackChannel(account.company)}`;
  const steps = [
    ...(ndaPending
      ? [["Sign your mutual NDA", "Two minutes, right here."] as const]
      : []),
    ["Meet your researcher", `${where}, usually within a working day.`],
    ["Review your codebase", "Together, in the repositories you shared."],
    ["Pick a first test case", "Something we can measure from day one."],
  ];

  return (
    <aside
      aria-label="Your project"
      className="flex flex-col gap-6 rounded-lg border bg-card p-6 lg:sticky lg:top-6"
    >
      <div className="flex flex-col gap-1.5">
        <span className="font-mono text-xs uppercase tracking-wide text-muted-foreground">
          What happens next
        </span>
        <h2 className="text-2xl font-semibold tracking-tight">
          {account.company} × Gradiated
        </h2>
      </div>
      <ol className="flex flex-col gap-4">
        {steps.map(([title, detail], index) => (
          <li key={title} className="grid grid-cols-[1.75rem_1fr] gap-3">
            <span
              aria-hidden="true"
              className="font-mono text-xs leading-6 text-muted-foreground"
            >
              {String(index + 1).padStart(2, "0")}
            </span>
            <span className="text-sm">
              <span className="font-medium">{title}</span>
              <br />
              <span className="text-muted-foreground">{detail}</span>
            </span>
          </li>
        ))}
      </ol>
      <div className="border-t pt-5">
        <Summary
          rows={[
            ["Code", codeSummary(installation)],
            ["Contact", contactSummary(server, draft)],
            ["NDA", ndaSummary(server, draft)],
          ]}
        />
      </div>
      {error ? (
        <div
          role="alert"
          className="flex flex-col gap-2 rounded-md border border-destructive/30 bg-destructive/5 p-3.5 text-sm"
        >
          <p className="flex gap-2">
            <CircleAlert className="mt-0.5 size-4 shrink-0 text-destructive" />
            {error.message}
          </p>
          {error.section ? (
            <button
              type="button"
              className="self-start font-medium underline underline-offset-4"
              onClick={() => onGoTo(error.section!)}
            >
              Go to {sectionNames[error.section]}
            </button>
          ) : null}
        </div>
      ) : null}
      {blockers.length ? (
        <div className="flex flex-col gap-1.5">
          <span className="text-sm font-medium">Before you can start</span>
          <ul id="start-blockers" className="flex flex-col">
            {blockers.map((blocker) => (
              <li key={blocker.label}>
                <button
                  type="button"
                  className="flex min-h-9 items-center gap-2.5 text-left text-sm underline-offset-4 hover:underline"
                  onClick={() => onGoTo(blocker.section)}
                >
                  <span
                    aria-hidden="true"
                    className="size-3.5 rounded-full border-[1.5px] border-muted-foreground"
                  />
                  {blocker.label}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="flex flex-col gap-2.5">
        <Button
          type="button"
          size="lg"
          disabled={submitting || blockers.length > 0}
          aria-describedby={blockers.length ? "start-blockers" : undefined}
          onClick={onStart}
        >
          {submitting ? <LoaderCircle className="animate-spin" /> : null}
          {submitting
            ? "Starting project…"
            : ndaPending
              ? "Sign NDA & start project"
              : "Start project"}
        </Button>
        <p role="status" className="text-center text-sm text-muted-foreground">
          {submitting
            ? "Checking GitHub one last time and notifying your researcher."
            : ndaPending && !blockers.length
              ? "We start your project as soon as the NDA is signed."
              : blockers.length
                ? null
                : "You can change any of this later."}
        </p>
      </div>
    </aside>
  );
};

const sectionNames: Record<OnboardingSection, string> = {
  code: "repository access",
  contact: "where we’ll talk",
  nda: "the mutual NDA",
};

export const ProjectStarted = ({
  account,
  server,
  installation,
  justStarted,
}: {
  account: OnboardingAccount;
  server: EngineerOnboarding;
  installation: VerifiedInstallation | null;
  justStarted: boolean;
}) => {
  const confirmation = confirmationMessage(server, account.email);
  const slackChannel =
    server.contact_channel === "slack" && server.slack
      ? `#${server.slack.channel_name}`
      : null;
  const recorded = server.github_installations[0];

  return (
    <div className="flex flex-col gap-12">
      <PageHeader
        eyebrow={
          <span className="flex items-center gap-2">
            <Check className="size-3.5 text-emerald-600" />
            Project started
            {server.submitted_at
              ? ` ${new Date(server.submitted_at).toLocaleDateString()}`
              : ""}
          </span>
        }
        title={justStarted ? "You’re all set." : "Your project is underway."}
      >
        {justStarted
          ? "A post-training researcher picks it up from here."
          : "Your post-training researcher is working with you. Here’s what you shared."}
      </PageHeader>
      <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <section
          aria-label="What happens now"
          className="flex flex-col gap-4 rounded-lg border bg-card p-6 md:p-8"
        >
          <p className="max-w-2xl text-lg leading-8">{confirmation.plan}</p>
          <p className="text-sm leading-6 text-muted-foreground">
            {confirmation.followUp}
          </p>
        </section>
        <aside
          aria-label="Your project"
          className="flex flex-col gap-5 rounded-lg border bg-card p-6"
        >
          <div className="flex flex-col gap-1.5">
            <Eyebrow>Your project</Eyebrow>
            <h2 className="text-2xl font-semibold tracking-tight">
              {account.company} × Gradiated
            </h2>
          </div>
          <Summary
            rows={[
              [
                "Code",
                installation
                  ? codeSummary(installation)
                  : (recorded?.account ?? "GitHub"),
              ],
              ["Contact", slackChannel ?? account.email],
              [
                "NDA",
                server.nda
                  ? `Signed ${new Date(server.nda.signed_at).toLocaleDateString()}`
                  : "None",
              ],
            ]}
          />
        </aside>
      </div>
    </div>
  );
};
