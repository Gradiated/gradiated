import { ArrowRight, Check, CircleAlert, LoaderCircle } from "lucide-react";
import type { ReactNode } from "react";

import type { EngineerOnboarding } from "@/api/engineer-onboarding";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  confirmationMessage,
  proposedSlackChannel,
  sectionId,
  slackInvited,
  type OnboardingAccount,
  type OnboardingDraft,
  type OnboardingSection,
  type VerifiedInstallation,
} from "@/lib/engineer-onboarding";

export type UpdateDraft = (values: Partial<OnboardingDraft>) => void;

export const PageHeader = ({
  title,
  children,
}: {
  title: string;
  children?: ReactNode;
}) => (
  <header className="flex max-w-3xl flex-col gap-4">
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
        Goals, constraints, deadlines: anything your researcher should know.
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

export const ProjectPanel = ({
  account,
  server,
  draft,
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
    [
      "Pick a first test case for training",
      "Something we can measure from day one.",
    ],
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
          {submitting || blockers.length
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

const TimelineStep = ({
  done,
  title,
  meta,
  children,
}: {
  done?: boolean;
  title: string;
  meta?: string | undefined;
  children?: ReactNode;
}) => (
  <li className="grid grid-cols-[1.5rem_1fr] gap-3 py-4 first:pt-0 last:pb-0">
    <span
      aria-hidden="true"
      className={
        done
          ? "mt-0.5 grid size-5 place-items-center rounded-full bg-emerald-600 text-white"
          : "mt-0.5 size-5 rounded-full border-[1.5px] border-muted-foreground/50"
      }
    >
      {done ? <Check className="size-3" strokeWidth={3} /> : null}
    </span>
    <span className="flex flex-col gap-1">
      <span className="flex flex-wrap items-baseline justify-between gap-x-4">
        <span className="font-medium">{title}</span>
        {meta ? (
          <span className="text-sm text-muted-foreground">{meta}</span>
        ) : null}
      </span>
      {children ? (
        <span className="text-sm leading-6 text-muted-foreground">
          {children}
        </span>
      ) : null}
    </span>
  </li>
);

export const ProjectStarted = ({
  account,
  server,
  onConsole,
  onReset,
}: {
  account: OnboardingAccount;
  server: EngineerOnboarding;
  onConsole: () => void;
  onReset?: (() => void) | undefined;
}) => {
  const confirmation = confirmationMessage(server, account.email);

  return (
    <div className="flex max-w-xl flex-col gap-8">
      <div className="flex flex-col gap-2">
        <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">
          You’re all set.
        </h1>
        <p className="text-muted-foreground">
          One of our researchers will pick it up from here.
        </p>
      </div>
      <ol
        aria-label="Your project"
        className="divide-y rounded-lg border bg-card px-5 py-4"
      >
        <TimelineStep
          done
          title="Project started"
          meta={
            server.submitted_at
              ? new Date(server.submitted_at).toLocaleDateString(undefined, {
                  day: "numeric",
                  month: "short",
                })
              : undefined
          }
        />
        <TimelineStep title={confirmation.plan} meta="Within a working day">
          {confirmation.followUp}
        </TimelineStep>
        <TimelineStep title="Pick a first test case for training" />
      </ol>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Button type="button" onClick={onConsole}>
          Go to console <ArrowRight />
        </Button>
        <p className="text-sm text-muted-foreground">
          Try our hosted models in the playground while you wait.
        </p>
      </div>
      {onReset ? (
        <button
          type="button"
          className="self-start text-sm text-muted-foreground underline underline-offset-4"
          onClick={onReset}
        >
          Reset onboarding (local only)
        </button>
      ) : null}
    </div>
  );
};
