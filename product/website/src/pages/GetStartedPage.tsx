import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  CircleDashed,
  Code2,
  LockKeyhole,
  MessageSquare,
  Plus,
  X,
} from "lucide-react";
import {
  emptyOnboarding,
  exampleOnboarding,
  accountStorageKey,
  onboardingAccountSchema,
  reuseAccount,
  firstIncompleteStep,
  counterpartyDetails,
  mutualNda,
  onboardingSchema,
} from "../onboarding";
import type { OnboardingDraft, OnboardingAccount } from "../onboarding";
import { getCurrentUser } from "../api/queries";
import {
  ENGINEER_SIGNUP_URL,
  ENGINEER_ORGANIZATION_SETUP_URL,
  ENGINEER_PREVIEW_SIGNUP_URL,
} from "../urls";
import "../styles/index.css";
import "../styles/onboarding.css";

const steps = ["Slack & GitHub", "Mutual NDA", "Get to work"];
type UpdateDraft = (values: Partial<OnboardingDraft>) => void;

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

    return draft;
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
  draft.repository || "GitHub repository";

const TeamStep = ({
  draft,
  patch,
}: {
  draft: OnboardingDraft;
  patch: UpdateDraft;
}) => (
  <>
    <StepTitle title="Set up Slack & GitHub.">
      Your forward deployed engineer is a real human. Work together async in
      Slack.
    </StepTitle>
    <Field
      label="GitHub repository"
      hint="We’ll request access to this repo after the NDA is signed."
    >
      <input
        required
        value={draft.repository}
        maxLength={300}
        onChange={(event) => patch({ repository: event.target.value })}
        placeholder="your-org/your-repository"
      />
    </Field>
    {draft.channel === "slack" && (
      <Field
        label="Slack workspace"
        hint="We’ll arrange a joint Slack Connect channel. Slack is our preferred way to work."
      >
        <input
          required
          value={draft.slack}
          maxLength={200}
          onChange={(event) => patch({ slack: event.target.value })}
          placeholder="your-team.slack.com"
        />
      </Field>
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
  onNda,
}: {
  draft: OnboardingDraft;
  patch: UpdateDraft;
  onNda: () => void;
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
    <button type="button" className="gs-text-button" onClick={onNda}>
      Preview pre-filled NDA <ArrowRight size={13} />
    </button>
    <p className="gs-note">
      Both parties review and sign. Signature dates are added at signing.
    </p>
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
            ? "Shared Slack channel · " + draft.slack
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
        <span>2</span>Sign the mutual NDA and approve GitHub access
      </li>
      <li>
        <span>3</span>
        Pick a test case together
      </li>
    </ol>
    <Field label="Anything else you’d like us to know or have as context? (optional)">
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
    </div>
  );
};

const AccountOnboarding = () => {
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
        const organization = requestedOrganization
          ? user.organizations.find(
              (row) =>
                row.id === requestedOrganization && row.status === "active",
            )
          : user.organizations.find((row) => row.status === "active");
        const pending = user.organizations.find(
          (row) => row.role === "admin" && !row.onboarding_completed,
        );

        if (pending) {
          window.location.replace(ENGINEER_ORGANIZATION_SETUP_URL);
          return;
        }
        if (!organization) {
          setError(true);
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
          window.location.replace(ENGINEER_SIGNUP_URL);
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
          <p role="status">Loading your account…</p>
        )}
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
  const [draft, setDraft] = useState(() => loadDraft(account));
  const [saved, setSaved] = useState(true);
  const [ndaOpen, setNdaOpen] = useState(false);
  const headingRef = useRef<HTMLElement>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const patch: UpdateDraft = (values) =>
    setDraft((current) => ({ ...current, ...values }));

  useEffect(() => {
    document.title = draft.submitted
      ? "Your engineer | Gradiated preview"
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
  }, [draft.step, draft.submitted]);

  useEffect(() => {
    if (ndaOpen) dialogRef.current?.showModal();
    else dialogRef.current?.close();
  }, [ndaOpen]);

  return (
    <div className="gr-root gs-root" data-theme="taupe">
      <div className="gs-prototype">
        {demo
          ? "Prototype · demo account · nothing is sent or connected"
          : "Prototype · nothing is sent or connected"}
      </div>
      <div
        className={`gs-auth-shell${draft.submitted ? " gs-auth-shell--project" : ""}`}
      >
        <div className="gs-auth-container">
          <header className="gs-header">
            <Link to="/" aria-label="Gradiated home" className="gs-logo">
              <img
                src="/brand/gradiated-full.svg"
                alt="Gradiated"
                width="1258"
                height="288"
              />
            </Link>
          </header>
          {draft.submitted ? (
            <ProjectPreview
              draft={draft}
              onEdit={() => patch({ submitted: false, step: 2 })}
              onNda={() => setNdaOpen(true)}
            />
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
                        disabled={index > draft.step}
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
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  if (draft.step === 2) {
                    const incomplete = firstIncompleteStep(draft);

                    patch(
                      incomplete === null
                        ? { submitted: true, step: 3 }
                        : { step: incomplete },
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
                  <>
                    <TeamStep draft={draft} patch={patch} />
                    {demo && (
                      <button
                        className="gs-text-button gs-example"
                        type="button"
                        onClick={() =>
                          setDraft(reuseAccount(exampleOnboarding(), account))
                        }
                      >
                        Fill with an example <ArrowRight size={13} />
                      </button>
                    )}
                  </>
                )}
                {draft.step === 1 && (
                  <AccessStep
                    draft={draft}
                    patch={patch}
                    onNda={() => setNdaOpen(true)}
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
                  >
                    {draft.step === 2 ? "Start project" : "Continue"}
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
              </form>
              <div className="gs-account-identity">
                Signed in as {account.email} ·{" "}
                <button
                  type="button"
                  className="gs-text-button"
                  onClick={() =>
                    setDraft(reuseAccount(emptyOnboarding(), account))
                  }
                >
                  Start over
                </button>
              </div>
            </main>
          )}
        </div>
      </div>

      <dialog
        ref={dialogRef}
        className="gs-dialog"
        onCancel={() => setNdaOpen(false)}
        onClick={(event) => {
          if (event.target === event.currentTarget) setNdaOpen(false);
        }}
        aria-labelledby="nda-title"
      >
        <button
          type="button"
          className="gs-dialog-close"
          onClick={() => setNdaOpen(false)}
          aria-label="Close NDA preview"
        >
          <X size={20} />
        </button>
        <span className="gs-label">SIGNATURE PAGE · PREVIEW</span>
        <h2 id="nda-title">Mutual NDA</h2>
        <div className="gs-nda-parties">
          <section>
            <h3>Your company</h3>
            <dl className="gs-summary">
              <div>
                <dt>Company</dt>
                <dd>
                  {counterpartyDetails(draft).company || "Legal company name"}
                </dd>
              </div>
              <div>
                <dt>Name</dt>
                <dd>
                  {counterpartyDetails(draft).name || "Signer’s full name"}
                </dd>
              </div>
              <div>
                <dt>Title</dt>
                <dd>{counterpartyDetails(draft).title || "Signer’s title"}</dd>
              </div>
              <div>
                <dt>Address</dt>
                <dd className="gs-address">
                  {counterpartyDetails(draft).address || "Company address"}
                </dd>
              </div>
              <div>
                <dt>Email</dt>
                <dd>{counterpartyDetails(draft).email || "Signer’s email"}</dd>
              </div>
              <div>
                <dt>Signature</dt>
                <dd>Awaiting signature</dd>
              </div>
              <div>
                <dt>Date</dt>
                <dd>Added at signing</dd>
              </div>
            </dl>
          </section>
          <section>
            <h3>PostHog · pre-filled</h3>
            <dl className="gs-summary">
              <div>
                <dt>Company</dt>
                <dd>{mutualNda.company}</dd>
              </div>
              <div>
                <dt>Name</dt>
                <dd>{mutualNda.signer}</dd>
              </div>
              <div>
                <dt>Title</dt>
                <dd>{mutualNda.title}</dd>
              </div>
              <div>
                <dt>Address</dt>
                <dd className="gs-address">{mutualNda.address}</dd>
              </div>
              <div>
                <dt>Signature</dt>
                <dd>Awaiting signature</dd>
              </div>
              <div>
                <dt>Date</dt>
                <dd>Added at signing</dd>
              </div>
            </dl>
          </section>
        </div>
        <p>
          Signature details only. The live flow sends the full mutual NDA for
          review and e-signing.
        </p>

        <button
          type="button"
          className="gr-button gr-button--main"
          onClick={() => setNdaOpen(false)}
        >
          Done <Check size={14} />
        </button>
      </dialog>
    </div>
  );
};

const ProjectPreview = ({
  draft,
  onEdit,
  onNda,
}: {
  draft: OnboardingDraft;
  onEdit: () => void;
  onNda: () => void;
}) => {
  const [tab, setTab] = useState<"steps" | "engineer" | "access">("steps");
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState<string[]>([]);
  const [sampleAdded, setSampleAdded] = useState(false);
  const [notice, setNotice] = useState("");

  return (
    <main className="gs-project">
      <div className="gs-project-top">
        <span className="gs-label">{draft.company} × GRADIATED</span>
        <button type="button" className="gs-text-button" onClick={onEdit}>
          Edit setup
        </button>
      </div>
      <div className="gs-project-title">
        <h1>Your setup is ready.</h1>
        <p>
          Next: meet your engineer in{" "}
          {draft.channel === "slack" ? "Slack" : "email"}.
        </p>
      </div>
      <nav className="gs-project-tabs" aria-label="Project sections">
        {(
          [
            ["steps", "Next steps"],
            ["engineer", "Your engineer"],
            ["access", "NDA & access"],
          ] as const
        ).map(([id, label]) => (
          <button
            type="button"
            key={id}
            aria-current={tab === id ? "page" : undefined}
            onClick={() => {
              setTab(id);
              setNotice("");
            }}
          >
            {label}
          </button>
        ))}
      </nav>
      {tab === "steps" && (
        <>
          <div className="gs-work-items">
            <div className="is-complete">
              <CheckCircle2 size={19} />
              <div>
                <h3>Setup details ready</h3>
                <p>{draft.context || draft.company + " · " + draft.email}</p>
              </div>
            </div>
            <div>
              <LockKeyhole size={19} />
              <div>
                <h3>Sign the mutual NDA</h3>
                <p>
                  {draft.legalName} and {mutualNda.company} · both signatures
                  pending
                </p>
                <button
                  type="button"
                  className="gs-text-button"
                  onClick={onNda}
                >
                  Review pre-filled NDA <ArrowRight size={13} />
                </button>
              </div>
            </div>
            <div>
              <Code2 size={19} />
              <div>
                <h3>Approve GitHub access</h3>
                <p>{draft.repository} · after the NDA is signed</p>
                <button
                  type="button"
                  className="gs-text-button"
                  onClick={() => setTab("access")}
                >
                  View access request <ArrowRight size={13} />
                </button>
              </div>
            </div>
            <div>
              <MessageSquare size={19} />
              <div>
                <h3>
                  {draft.channel === "slack"
                    ? "Set up the joint Slack channel"
                    : "Email fallback · Slack unavailable"}
                </h3>
                <p>
                  {draft.channel === "slack"
                    ? draft.slack +
                      " · a Slack Connect invitation needs workspace approval."
                    : "We’ll use " +
                      draft.email +
                      ". Slack remains our preferred way to work."}
                </p>
                {draft.channel === "slack" && (
                  <button
                    type="button"
                    className="gs-text-button"
                    onClick={() =>
                      setNotice(
                        "The live flow arranges a Slack Connect invitation for " +
                          draft.slack +
                          ". Nothing is sent in this preview.",
                      )
                    }
                  >
                    Preview Slack Connect invite <ArrowRight size={13} />
                  </button>
                )}
                <button
                  type="button"
                  className="gs-text-button gs-intro-button"
                  onClick={() => setTab("engineer")}
                >
                  Meet your engineer <ArrowRight size={13} />
                </button>
              </div>
            </div>
            <div>
              <CircleDashed size={19} />
              <div>
                <h3>Pick a test case together</h3>
                <p>Then test changes against that baseline.</p>
              </div>
            </div>
          </div>
          <details className="gs-sample">
            <summary>Bring an example</summary>
            <p>One input. What happened. What you expected.</p>
            <button
              type="button"
              className="gs-text-button"
              onClick={() => setSampleAdded(!sampleAdded)}
            >
              {sampleAdded ? <Check size={14} /> : <Plus size={14} />}
              {sampleAdded ? "Remove demo example" : "Add a demo example"}
            </button>
            {sampleAdded && (
              <div className="gs-example-result">
                <span className="gs-label">DEMO EXAMPLE</span>
                <p>
                  <strong>Input</strong> “Change my shipping address.”
                </p>
                <p>
                  <strong>Actual</strong> Generic instructions; no tool call.
                </p>
                <p>
                  <strong>Expected</strong> Look up the order, check its status,
                  then call the update tool.
                </p>
              </div>
            )}
          </details>
        </>
      )}
      {tab === "engineer" && (
        <section className="gs-engineer-view">
          <div className="gs-message">
            <span className="gs-avatar">
              <Code2 size={18} />
            </span>
            <div>
              <span className="gs-label">EXAMPLE INTRODUCTION</span>
              <p>
                Hi {draft.name.split(" ")[0]} — can you share one input, the
                answer you got, and what you expected? I’ll use that as our
                first test.
              </p>
            </div>
          </div>
          {messages.map((body, index) => (
            <div className="gs-message" key={index}>
              <span className="gs-avatar">{draft.name.slice(0, 1)}</span>
              <div>
                <span className="gs-label">YOU · PREVIEW</span>
                <p>{body}</p>
              </div>
            </div>
          ))}
          <form
            className="gs-message-form"
            onSubmit={(event) => {
              event.preventDefault();
              if (!message.trim()) return;
              setMessages((current) => [...current, message.trim()]);
              setMessage("");
              setNotice("Preview only. Nothing sent.");
            }}
          >
            <Field label="Reply">
              <textarea
                required
                rows={3}
                maxLength={2000}
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                placeholder="Here’s one that failed…"
              />
            </Field>
            <button type="submit" className="gr-button gr-button--main">
              Preview reply <ArrowRight size={14} />
            </button>
          </form>
          <p className="gs-note">
            In the live service, you’ll talk in{" "}
            {draft.channel === "slack" ? "Slack" : "email"}.
          </p>
        </section>
      )}
      {tab === "access" && (
        <section className="gs-access-view">
          <dl className="gs-summary">
            <div>
              <dt>NDA</dt>
              <dd>
                {ndaLabel()} · {draft.legalName}
              </dd>
            </div>
            <div>
              <dt>Signer</dt>
              <dd>
                {counterpartyDetails(draft).name} ·{" "}
                {counterpartyDetails(draft).title}
              </dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>Awaiting both signatures</dd>
            </div>
            <div>
              <dt>GitHub</dt>
              <dd>{draft.repository} · access pending</dd>
            </div>
            <div>
              <dt>Channel</dt>
              <dd>
                {draft.channel === "slack"
                  ? draft.slack + " · joint channel pending"
                  : "Email fallback · Slack unavailable"}
              </dd>
            </div>
          </dl>
          <button type="button" className="gs-text-button" onClick={onNda}>
            Review pre-filled NDA <ArrowRight size={13} />
          </button>
          <p>After signing, approve access to the selected repository.</p>
          <button
            type="button"
            className="gs-text-button"
            onClick={() =>
              setNotice(
                "Your engineer will request access to " +
                  draft.repository +
                  " once both parties have signed. Nothing is connected in this preview.",
              )
            }
          >
            Preview GitHub access request <ArrowRight size={14} />
          </button>
          <p className="gs-note">
            Code changes and use of private data in models require separate
            written approval.
          </p>
        </section>
      )}
      <p className="gs-live-notice" role="status">
        {notice}
      </p>
    </main>
  );
};
