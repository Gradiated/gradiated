import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowLeft, ArrowRight, Check } from "lucide-react";
import {
  emptyOnboarding,
  accountStorageKey,
  onboardingAccountSchema,
  reuseAccount,
  firstIncompleteStep,
  counterpartyDetails,
  onboardingSchema,
} from "../onboarding";
import type { OnboardingDraft, OnboardingAccount } from "../onboarding";
import { getCurrentUser, type CurrentUser } from "../api/queries";
import { NdaSigning } from "../components/NdaSigning";
import { SlackConnectInvite } from "../components/SlackConnectInvite";
import {
  GithubAppInstall,
  type GithubInstallation,
} from "../components/GithubAppInstall";
import { getGithubInstallations } from "../api/github";
import { sendSlackOnboardingNotes } from "../api/slack";
import {
  ENGINEER_SIGNUP_URL,
  ENGINEER_ORGANIZATION_SETUP_URL,
  ENGINEER_PREVIEW_SIGNUP_URL,
} from "../urls";
import "../styles/index.css";
import "../styles/onboarding.css";

const steps = ["Mutual NDA", "Slack & GitHub", "Get to work"];
type UpdateDraft = (values: Partial<OnboardingDraft>) => void;

const OnboardingHelp = ({ step }: { step: string }) => (
  <p className="gs-help">
    Stuck?{" "}
    <a
      href={`mailto:help@gradiated.com?subject=${encodeURIComponent(`Help with Gradiated setup: ${step}`)}`}
    >
      Email us
    </a>
  </p>
);

const loadDraft = (account: OnboardingAccount): OnboardingDraft => {
  try {
    const result = onboardingSchema.safeParse(
      JSON.parse(localStorage.getItem(accountStorageKey(account)) ?? "{}"),
    );
    if (!result.success) return reuseAccount(emptyOnboarding(), account);

    const draft = reuseAccount(result.data, account);

    const incomplete = firstIncompleteStep(draft);

    if (incomplete !== null && draft.step > incomplete) {
      return { ...draft, step: incomplete, submitted: false };
    }

    return { ...draft, step: 0, submitted: false };
  } catch {
    return reuseAccount(emptyOnboarding(), account);
  }
};

const Field = ({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) => (
  <label className="gs-field">
    <span>{label}</span>
    {children}
    {hint && <small>{hint}</small>}
  </label>
);

const StepTitle = ({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) => (
  <div className="gs-step-title">
    <h1>{title}</h1>
    <p>{children}</p>
  </div>
);

const ndaLabel = () => "Mutual NDA with PostHog Inc.";

const accessLabel = (draft: OnboardingDraft) =>
  draft.githubAccount
    ? `GitHub app installed · ${draft.githubAccount}`
    : "GitHub app installation required";

const TeamStep = ({
  draft,
  patch,
  organizationId,
  demo,
  onGithubVerified,
}: {
  draft: OnboardingDraft;
  patch: UpdateDraft;
  organizationId: string;
  demo: boolean;
  onGithubVerified: (installation: GithubInstallation | null) => void;
}) => (
  <>
    <StepTitle title="Set up Slack & GitHub.">
      A shared channel for the conversation. Repository access for the work.
    </StepTitle>
    <GithubAppInstall
      organizationId={organizationId}
      ndaDocumentId={draft.ndaDocumentId}
      demo={demo}
      company={draft.company}
      onVerified={onGithubVerified}
    />
    {draft.channel === "slack" && (
      <SlackConnectInvite
        draft={draft}
        organizationId={organizationId}
        demo={demo}
        onInvited={patch}
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

const AccessStep = ({
  draft,
  patch,
}: {
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
        value={draft.legalName}
        maxLength={200}
        onChange={(event) => patch({ legalName: event.target.value })}
        placeholder="Acme, Inc."
      />
    </Field>
    <div className="gs-field-pair">
      <Field label="Signer’s full name">
        <input
          required
          value={draft.signerName ?? draft.name}
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
    <Field label="Signer’s email">
      <input
        required
        type="email"
        value={draft.signerEmail ?? draft.email}
        maxLength={200}
        onChange={(event) => patch({ signerEmail: event.target.value })}
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

const ReviewStep = ({
  draft,
  onEdit,
  patch,
}: {
  draft: OnboardingDraft;
  onEdit: () => void;
  patch: UpdateDraft;
}) => (
  <>
    <StepTitle title="Let’s get to work.">
      Your engineer will pick this up async.
    </StepTitle>
    <div className="gs-review-heading">
      <h2>{draft.company} × Gradiated</h2>
      <button type="button" className="gs-text-button" onClick={onEdit}>
        Edit setup
      </button>
    </div>
    <dl className="gs-summary">
      <div>
        <dt>Contact</dt>
        <dd>{draft.email}</dd>
      </div>
      <div>
        <dt>Channel</dt>
        <dd>
          {draft.channel === "slack"
            ? draft.slackStatus === "not_sent"
              ? "Slack invitation not sent yet"
              : "#" +
                draft.slack +
                " · " +
                (draft.slackStatus === "joined"
                  ? "connected"
                  : "invitation sent")
            : "Email fallback · Slack unavailable"}
        </dd>
      </div>
      <div>
        <dt>NDA</dt>
        <dd>{ndaLabel()}</dd>
      </div>
      <div>
        <dt>Access</dt>
        <dd>{accessLabel(draft)}</dd>
      </div>
    </dl>
    <h3 className="gs-next-heading">What happens next</h3>
    <ol className="gs-next-list">
      <li>
        <span>1</span>Meet your engineer in{" "}
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
        draft.channel === "slack" && draft.slackStatus !== "not_sent"
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

const previewAccountKey = "gradiated-created-preview-account-v1";

const readPreviewAccount = (): OnboardingAccount | null => {
  try {
    const result = onboardingAccountSchema.safeParse(
      JSON.parse(sessionStorage.getItem(previewAccountKey) ?? "null"),
    );
    return result.success ? result.data : null;
  } catch {
    return null;
  }
};

export const GetStartedPage = () => {
  const [search] = useSearchParams();
  const mode = search.get("preview");
  if (search.get("github_authorized") === "1")
    return (
      <div className="gr-root gs-root">
        <main className="gs-account-gate">
          <h1>Return to setup</h1>
          <p>
            Return to the original tab to check your GitHub installation. You
            can close this tab.
          </p>
          <OnboardingHelp step="GitHub authorization" />
        </main>
      </div>
    );

  return import.meta.env.DEV && (mode === "signup" || mode === "account") ? (
    <AccountSignupPreview key={mode} resume={mode === "account"} />
  ) : (
    <AccountOnboarding key={search.get("organization") ?? "default"} />
  );
};

const AccountSignupPreview = ({ resume }: { resume: boolean }) => {
  const [account, setAccount] = useState<OnboardingAccount | null>(() =>
    resume ? readPreviewAccount() : null,
  );
  const frameRef = useRef<HTMLIFrameElement>(null);
  const [, setSearch] = useSearchParams();

  useEffect(() => {
    const receiveAccount = (event: MessageEvent<unknown>) => {
      if (
        event.origin !== new URL(ENGINEER_PREVIEW_SIGNUP_URL).origin ||
        event.source !== frameRef.current?.contentWindow
      )
        return;
      if (
        !event.data ||
        typeof event.data !== "object" ||
        !("type" in event.data) ||
        event.data.type !== "gradiated:engineer-preview-account" ||
        !("account" in event.data)
      )
        return;
      const result = onboardingAccountSchema.safeParse(event.data.account);
      if (!result.success) return;

      sessionStorage.setItem(previewAccountKey, JSON.stringify(result.data));
      setAccount(result.data);
      setSearch({ preview: "account" }, { replace: true });
    };

    window.addEventListener("message", receiveAccount);
    return () => window.removeEventListener("message", receiveAccount);
  }, [setSearch]);

  if (account)
    return <GetStartedWorkflow key={account.userId} account={account} demo />;

  return (
    <div className="gr-root gs-root gs-account-preview">
      <div className="gs-prototype">
        Prototype · signup is simulated · no emails or OAuth requests are sent
      </div>
      <iframe
        ref={frameRef}
        className="gs-signup-frame"
        title="Create your Gradiated account"
        src={ENGINEER_PREVIEW_SIGNUP_URL}
        sandbox="allow-scripts allow-same-origin allow-forms"
      />
      <OnboardingHelp step="Create an account" />
    </div>
  );
};

const AccountOnboarding = () => {
  const [search, setSearch] = useSearchParams();
  const [organizations, setOrganizations] = useState<
    CurrentUser["organizations"]
  >([]);
  const [account, setAccount] = useState<OnboardingAccount | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setError(false);

    void getCurrentUser()
      .then((user) => {
        if (!active) return;

        const requestedOrganization = new URLSearchParams(
          window.location.search,
        ).get("organization");
        const memberships = user.organizations.filter(
          (row) => row.status === "active",
        );
        if (!requestedOrganization && memberships.length > 1) {
          setOrganizations(memberships);
          return;
        }
        const organization = requestedOrganization
          ? memberships.find((row) => row.id === requestedOrganization)
          : memberships[0];
        if (!organization) {
          setError(true);
          return;
        }
        if (
          organization.role === "admin" &&
          !organization.onboarding_completed
        ) {
          const destination = new URL(ENGINEER_ORGANIZATION_SETUP_URL);
          destination.searchParams.set("organization", organization.id);
          window.location.replace(destination.toString());
          return;
        }

        setAccount({
          userId: user.id,
          organizationId: organization.id,
          name: user.name,
          email: user.email,
          company: organization.name,
        });
      })
      .catch((cause: unknown) => {
        if (!active) return;

        if (
          cause instanceof Error &&
          "status" in cause &&
          cause.status === 401
        ) {
          const recoverStaff =
            "code" in cause && cause.code === "staff_session_recovery_required";
          window.location.replace(
            recoverStaff
              ? ENGINEER_ORGANIZATION_SETUP_URL
              : ENGINEER_SIGNUP_URL,
          );
          return;
        }

        setError(true);
      });

    return () => {
      active = false;
    };
  }, [attempt]);

  if (account)
    return (
      <GetStartedWorkflow
        key={account.userId + ":" + account.organizationId}
        account={account}
      />
    );

  if (organizations.length > 1)
    return (
      <div className="gr-root gs-root">
        <div className="gs-auth-shell">
          <main className="gs-main gs-auth-container">
            <StepTitle title="Choose your organization.">
              Which team is this engineer for?
            </StepTitle>
            <Field label="Organization">
              <select
                defaultValue=""
                onChange={(event) => {
                  const next = new URLSearchParams(search);
                  next.set("organization", event.target.value);
                  setSearch(next);
                }}
              >
                <option value="" disabled>
                  Choose an organization
                </option>
                {organizations.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.name}
                  </option>
                ))}
              </select>
            </Field>
            <OnboardingHelp step="Choose an organization" />
          </main>
        </div>
      </div>
    );

  return (
    <div className="gr-root gs-root">
      <main className="gs-account-gate">
        {error ? (
          <>
            <h1>We couldn’t load your account.</h1>
            <button
              type="button"
              className="gr-button gr-button--main"
              onClick={() => setAttempt((current) => current + 1)}
            >
              Try again
            </button>
            <a className="gs-text-button" href={ENGINEER_SIGNUP_URL}>
              Sign in or create an account <ArrowRight size={14} />
            </a>
            {import.meta.env.DEV && (
              <Link
                className="gs-text-button"
                to="/get-started/?preview=account"
              >
                Open the post-signup demo <ArrowRight size={14} />
              </Link>
            )}
          </>
        ) : (
          <>
            <h1>Set up your engineer.</h1>
            <p role="status">Loading your account…</p>
          </>
        )}
        <OnboardingHelp step="Account setup" />
      </main>
    </div>
  );
};

const GetStartedWorkflow = ({
  account,
  demo = false,
}: {
  account: OnboardingAccount;
  demo?: boolean;
}) => {
  const [search] = useSearchParams();
  const previewSlack =
    import.meta.env.DEV && demo && search.get("step") === "slack";
  const [draft, setDraft] = useState(() => {
    const current = loadDraft(account);

    return previewSlack ? { ...current, introduced: true, step: 1 } : current;
  });
  const [saved, setSaved] = useState(true);
  const [signingOpen, setSigningOpen] = useState(false);
  const [ndaVerified, setNdaVerified] = useState(previewSlack);
  const [githubVerified, setGithubVerified] = useState(false);
  const [checkingGithub, setCheckingGithub] = useState(false);
  const [githubError, setGithubError] = useState("");
  const [sendingNotes, setSendingNotes] = useState(false);
  const [notesError, setNotesError] = useState("");
  const notesRequest = useRef<{ key: string; id: string } | null>(null);
  const headingRef = useRef<HTMLElement>(null);
  const patch: UpdateDraft = (values) => {
    const ndaFields = [
      "legalName",
      "legalAddress",
      "signerName",
      "signerTitle",
      "signerEmail",
    ] as const;
    const changesNda = ndaFields.some(
      (key) => key in values && values[key] !== draft[key],
    );
    if (changesNda) {
      setNdaVerified(false);
      setGithubVerified(false);
    }

    setDraft((current) => ({
      ...current,
      ...values,
      ...(changesNda ? { ndaDocumentId: null } : {}),
    }));
  };

  useEffect(() => {
    document.title = draft.submitted
      ? "Setup complete | Gradiated"
      : "Get a forward deployed engineer | Gradiated";
    try {
      localStorage.setItem(accountStorageKey(account), JSON.stringify(draft));
      setSaved(true);
    } catch {
      setSaved(false);
    }
  }, [draft, account]);

  useEffect(() => {
    headingRef.current?.focus({ preventScroll: true });
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [draft.step, draft.submitted, draft.introduced, signingOpen]);

  return (
    <div className="gr-root gs-root" data-theme="taupe">
      <div className="gs-prototype">
        {demo ? "Prototype · demo account" : "Prototype"}
      </div>
      <div className="gs-auth-shell">
        <div
          className={`gs-auth-container${signingOpen ? " gs-auth-container--signing" : ""}`}
        >
          <header className="gs-header">
            <Link to="/" aria-label="Gradiated home" className="gs-logo">
              <img
                src="/brand/gradiated-wordmark.svg"
                alt="Gradiated"
                width="10788"
                height="1193"
              />
            </Link>
          </header>
          {!draft.introduced ? (
            <main className="gs-main" ref={headingRef} tabIndex={-1}>
              <StepTitle title="Let’s get you set up with a forward deployed engineer.">
                Self-serve. No sales call.
              </StepTitle>
              <p className="gs-introduction">
                A real human from our team will join you in Slack and work with
                your codebase to get more out of your models.
              </p>
              <div className="gs-actions">
                <button
                  type="button"
                  className="gr-button gr-button--main gs-primary"
                  onClick={() =>
                    patch({ introduced: true, submitted: false, step: 0 })
                  }
                >
                  Get started <ArrowRight size={15} />
                </button>
              </div>
            </main>
          ) : draft.submitted ? (
            <main
              className="gs-main gs-confirmation"
              ref={headingRef}
              tabIndex={-1}
              aria-label="Setup complete"
            >
              <p>
                Thank you, we've got everything we need. One of our researchers
                will have a look into your project now and will suggest a plan
                on Slack with you as soon as possible, likely within a working
                day!
              </p>
              <p>
                If in the meantime you want to chat or tell us anything, feel
                free to hop into the slack channel we just set up with you and
                invite some colleagues to it.
              </p>
            </main>
          ) : (
            <main className="gs-main" ref={headingRef} tabIndex={-1}>
              <nav className="gs-progress" aria-label="Setup steps">
                <ol>
                  {steps.map((label, index) => (
                    <li
                      key={label}
                      className={
                        index === draft.step
                          ? "is-current"
                          : index < draft.step
                            ? "is-done"
                            : ""
                      }
                    >
                      <button
                        type="button"
                        disabled={
                          index > draft.step ||
                          (index > 0 && !ndaVerified) ||
                          (index > 1 && !githubVerified) ||
                          signingOpen
                        }
                        onClick={() => patch({ step: index })}
                        aria-current={index === draft.step ? "step" : undefined}
                      >
                        <span>
                          {index < draft.step ? <Check size={12} /> : index + 1}
                        </span>
                        <span>{label}</span>
                      </button>
                    </li>
                  ))}
                </ol>
              </nav>
              {!saved && (
                <p className="gs-note" role="status">
                  Progress won’t be saved
                </p>
              )}
              {signingOpen ? (
                <NdaSigning
                  organizationId={account.organizationId}
                  details={counterpartyDetails(draft)}
                  initialDocumentId={draft.ndaDocumentId}
                  demo={demo}
                  onDocument={(id) => patch({ ndaDocumentId: id })}
                  onComplete={(id) => {
                    setNdaVerified(true);
                    setSigningOpen(false);
                    patch({ ndaDocumentId: id, step: 1 });
                  }}
                  onBack={() => setSigningOpen(false)}
                />
              ) : (
                <form
                  onSubmit={async (event) => {
                    event.preventDefault();
                    if (checkingGithub || sendingNotes) return;
                    if (draft.step === 0) {
                      setSigningOpen(true);
                      return;
                    }
                    if (draft.step > 0) {
                      if (!githubVerified || !draft.githubInstallationId) {
                        setGithubError(
                          "Install the Gradiated GitHub app and select at least one repository before continuing. If installation needs approval, ask your GitHub organization owner to approve it.",
                        );
                        return;
                      }

                      if (!demo) {
                        setCheckingGithub(true);
                        setGithubError("");
                        try {
                          const result = await getGithubInstallations(
                            account.organizationId,
                            draft.ndaDocumentId!,
                            draft.githubInstallationId,
                          );
                          if (
                            !result.installations.some(
                              (item) => item.id === draft.githubInstallationId,
                            )
                          ) {
                            setGithubVerified(false);
                            setGithubError(
                              "GitHub access changed. Return to the installation step and check again.",
                            );
                            return;
                          }
                        } catch (error) {
                          setGithubError(
                            error instanceof Error
                              ? error.message
                              : "Could not verify GitHub.",
                          );
                          return;
                        } finally {
                          setCheckingGithub(false);
                        }
                      }
                    }
                    if (draft.step === 2) {
                      const incomplete = firstIncompleteStep(draft);
                      const notes = draft.context.trim();
                      if (
                        incomplete === null &&
                        ndaVerified &&
                        notes &&
                        draft.channel === "slack" &&
                        draft.slackStatus !== "not_sent" &&
                        (!demo || draft.slackDeliveryMode === "live")
                      ) {
                        setSendingNotes(true);
                        setNotesError("");
                        const key = JSON.stringify([
                          account.organizationId,
                          draft.slack,
                          notes,
                        ]);
                        if (notesRequest.current?.key !== key)
                          notesRequest.current = {
                            key,
                            id: crypto.randomUUID(),
                          };
                        try {
                          if (demo) {
                            const response = await fetch(
                              "/__slack-preview/messages",
                              {
                                method: "POST",
                                headers: { "Content-Type": "application/json" },
                                body: JSON.stringify({
                                  organizationId: account.organizationId,
                                  channelName: draft.slack,
                                  email: account.email,
                                  notes,
                                  requestId: notesRequest.current.id,
                                }),
                              },
                            );
                            const result = await response.json();
                            if (!response.ok || result.status !== "sent")
                              throw new Error(
                                result.error ??
                                  "Slack did not confirm your notes. Check the channel before retrying.",
                              );
                          } else {
                            await sendSlackOnboardingNotes(
                              account.organizationId,
                              draft.ndaDocumentId!,
                              draft.slack,
                              notes,
                              notesRequest.current.id,
                            );
                          }
                        } catch (error) {
                          setNotesError(
                            error instanceof Error
                              ? error.message
                              : "Could not send your notes to Slack. Your note is still saved here.",
                          );
                          return;
                        } finally {
                          setSendingNotes(false);
                        }
                      }

                      patch(
                        incomplete === null && ndaVerified
                          ? { submitted: true, step: 3 }
                          : { step: incomplete ?? 0 },
                      );
                    } else
                      patch({
                        step: draft.step + 1,
                        ...(draft.step === 0
                          ? {
                              legalName: draft.legalName || draft.company,
                              signerName: draft.signerName ?? draft.name,
                              signerEmail: draft.signerEmail ?? draft.email,
                            }
                          : {}),
                      });
                  }}
                >
                  {draft.step === 0 && (
                    <AccessStep draft={draft} patch={patch} />
                  )}
                  {draft.step === 1 && (
                    <TeamStep
                      draft={draft}
                      patch={patch}
                      organizationId={account.organizationId}
                      demo={demo}
                      onGithubVerified={(installation) => {
                        setGithubVerified(installation !== null);
                        if (installation) {
                          setGithubError("");
                          patch({
                            githubInstallationId: installation.id,
                            githubAccount: installation.account,
                            githubRepositoryCount:
                              installation.repository_count,
                          });
                        }
                      }}
                    />
                  )}
                  {draft.step === 2 && (
                    <ReviewStep
                      draft={draft}
                      patch={patch}
                      onEdit={() => patch({ step: 0 })}
                    />
                  )}
                  <div className="gs-actions">
                    <button
                      type="submit"
                      className="gr-button gr-button--main gs-primary"
                      disabled={checkingGithub || sendingNotes}
                      aria-describedby={
                        githubError ? "gs-github-error" : undefined
                      }
                    >
                      {sendingNotes
                        ? "Sending notes…"
                        : checkingGithub
                          ? "Checking GitHub…"
                          : draft.step === 0
                            ? "Review & sign NDA"
                            : draft.step === 2
                              ? "Start project"
                              : "Continue"}
                      <ArrowRight size={15} />
                    </button>
                    {draft.step > 0 && (
                      <button
                        type="button"
                        className="gs-back"
                        onClick={() => patch({ step: draft.step - 1 })}
                      >
                        <ArrowLeft size={14} /> Back
                      </button>
                    )}
                  </div>
                  {githubError && (
                    <p id="gs-github-error" role="alert" className="gs-note">
                      {githubError}
                    </p>
                  )}
                  {notesError && (
                    <p role="alert" className="gs-note">
                      {notesError}
                    </p>
                  )}
                </form>
              )}
              <div className="gs-account-identity">
                Signed in as {account.email} ·{" "}
                <button
                  type="button"
                  className="gs-text-button"
                  onClick={() => {
                    setNdaVerified(false);
                    setGithubVerified(false);
                    setSigningOpen(false);
                    setDraft(reuseAccount(emptyOnboarding(), account));
                  }}
                >
                  Start over
                </button>
              </div>
            </main>
          )}
          {!draft.submitted && (
            <OnboardingHelp
              step={
                !draft.introduced
                  ? "Get an engineer"
                  : (steps[draft.step] ?? "Project setup")
              }
            />
          )}
        </div>
      </div>
    </div>
  );
};
