import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, ArrowRight, Check } from "lucide-react";
import { getEngineerOnboarding } from "../../api/engineer-onboarding";
import type { EngineerOnboarding } from "../../api/engineer-onboarding";
import {
  accountStorageKey,
  changesNda,
  confirmationMessage,
  counterpartyDetails,
  emptyOnboarding,
  ndaReference,
  restoreOnboardingDraft,
  resumeStep,
  resumeView,
  stepLocked,
  submitAction,
  submitProblem,
} from "../../onboarding";
import type {
  OnboardingAccount,
  OnboardingDraft,
  OnboardingView,
  VerifiedInstallation,
} from "../../onboarding";
import {
  githubInstallationActive,
  submitOnboarding,
} from "../../onboarding-submit";
import { NdaSigning } from "../NdaSigning";
import { OnboardingHelp, StepTitle } from "./OnboardingParts";
import { AccessStep, ReviewStep, TeamStep } from "./OnboardingSteps";
import type { UpdateDraft } from "./OnboardingSteps";

const steps = ["Mutual NDA", "Slack & GitHub", "Get to work"];

const githubRequiredMessage =
  "Install the Gradiated GitHub app and select at least one repository before continuing. If installation needs approval, ask your GitHub organization owner to approve it.";

const loadDraft = (account: OnboardingAccount): OnboardingDraft => {
  try {
    return restoreOnboardingDraft(
      JSON.parse(localStorage.getItem(accountStorageKey(account)) ?? "{}"),
    );
  } catch {
    return emptyOnboarding();
  }
};

const errorMessage = (error: unknown, fallback: string) =>
  error instanceof Error ? error.message : fallback;

const errorCode = (error: unknown) =>
  error instanceof Error && "code" in error ? String(error.code) : undefined;

export const GetStartedWorkflow = ({
  account,
}: {
  account: OnboardingAccount;
}) => {
  const [draft, setDraft] = useState(() => loadDraft(account));
  const [saved, setSaved] = useState(true);
  const [server, setServer] = useState<EngineerOnboarding | null>(null);
  const [loadError, setLoadError] = useState("");
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [view, setView] = useState<OnboardingView>("introduction");
  const [step, setStep] = useState(0);
  const [installation, setInstallation] = useState<VerifiedInstallation | null>(
    null,
  );
  const [signingOpen, setSigningOpen] = useState(false);
  const [checkingGithub, setCheckingGithub] = useState(false);
  const [githubError, setGithubError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const headingRef = useRef<HTMLElement>(null);

  useEffect(() => {
    let active = true;
    setLoadError("");

    void getEngineerOnboarding(account.organizationId)
      .then((current) => {
        if (!active) return;

        setServer(current);
        setView(resumeView(current));
        setStep(resumeStep(current));
      })
      .catch((error) => {
        if (active)
          setLoadError(
            errorMessage(error, "Could not load your setup. Please retry."),
          );
      });

    return () => {
      active = false;
    };
  }, [account.organizationId, loadAttempt]);

  useEffect(() => {
    document.title =
      view === "complete"
        ? "Setup complete | Gradiated"
        : "Get a forward deployed engineer | Gradiated";
    try {
      localStorage.setItem(accountStorageKey(account), JSON.stringify(draft));
      setSaved(true);
    } catch {
      setSaved(false);
    }
  }, [draft, account, view]);

  useEffect(() => {
    headingRef.current?.focus({ preventScroll: true });
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [step, view, signingOpen, server === null, loadError]);

  const patch: UpdateDraft = (values) =>
    setDraft((current) => ({
      ...current,
      ...values,
      ...(changesNda(current, values) ? { ndaDocumentId: null } : {}),
    }));

  const refresh = async () => {
    setServer(await getEngineerOnboarding(account.organizationId));
  };

  if (!server)
    return (
      <Shell>
        <main className="gs-main" ref={headingRef} tabIndex={-1}>
          {loadError ? (
            <>
              <p role="alert">{loadError}</p>
              <button
                type="button"
                className="gr-button gs-primary"
                onClick={() => setLoadAttempt((attempt) => attempt + 1)}
              >
                Try again
              </button>
            </>
          ) : (
            <p role="status">Restoring your setup…</p>
          )}
        </main>
        <OnboardingHelp step="Project setup" />
      </Shell>
    );

  const ndaSigned = server.nda !== null;

  const recheckGithub = async (current: VerifiedInstallation) => {
    setCheckingGithub(true);
    setGithubError("");
    try {
      if (
        await githubInstallationActive(
          account.organizationId,
          current.id,
          ndaReference(server, draft),
        )
      )
        return true;

      setInstallation(null);
      setGithubError(
        "GitHub access changed. Return to the installation step and check again.",
      );
      return false;
    } catch (error) {
      setGithubError(errorMessage(error, "Could not verify GitHub."));
      return false;
    } finally {
      setCheckingGithub(false);
    }
  };

  const finish = async (current: VerifiedInstallation) => {
    setSubmitting(true);
    setSubmitError("");
    try {
      const result = await submitOnboarding({
        account,
        server,
        draft,
        installation: current,
      });
      setServer(result);
      if (result.submitted_at) setView("complete");
    } catch (error) {
      const problem = submitProblem(errorCode(error));
      if (problem) setStep(problem.step);

      setSubmitError(
        problem?.message ??
          errorMessage(error, "Could not start your project. Please retry."),
      );
    } finally {
      setSubmitting(false);
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (checkingGithub || submitting) return;

    const action = submitAction(step, { ndaSigned, installation });
    if (action === "sign") {
      setSigningOpen(true);
      return;
    }

    if (action === "github_required") {
      setGithubError(githubRequiredMessage);
      return;
    }

    if (step === 0) {
      setStep(1);
      return;
    }

    if (!installation || !(await recheckGithub(installation))) return;

    if (action === "finish") await finish(installation);
    else setStep(step + 1);
  };

  const githubChecked = (verified: VerifiedInstallation | null) => {
    setInstallation(verified);
    if (verified) setGithubError("");
  };

  const ndaCompleted = async (documentId: string) => {
    patch({ ndaDocumentId: documentId });
    setSigningOpen(false);
    try {
      await refresh();
      setStep(1);
    } catch (error) {
      setSubmitError(
        errorMessage(error, "Could not confirm your NDA. Please retry."),
      );
    }
  };

  const confirmation = confirmationMessage(server, account.email);

  return (
    <Shell wide={signingOpen}>
      {view === "introduction" ? (
        <main className="gs-main" ref={headingRef} tabIndex={-1}>
          <StepTitle title="Let’s get you set up with a forward deployed engineer.">
            Self-serve. No sales call.
          </StepTitle>
          <p className="gs-introduction">
            A real human from our team will join you in Slack and work with your
            codebase to get more out of your models.
          </p>
          <div className="gs-actions">
            <button
              type="button"
              className="gr-button gr-button--main gs-primary"
              onClick={() => {
                setStep(0);
                setView("steps");
              }}
            >
              Get started <ArrowRight size={15} />
            </button>
          </div>
        </main>
      ) : view === "complete" ? (
        <main
          className="gs-main gs-confirmation"
          ref={headingRef}
          tabIndex={-1}
          aria-label="Setup complete"
        >
          <p>{confirmation.plan}</p>
          <p>{confirmation.followUp}</p>
        </main>
      ) : (
        <main className="gs-main" ref={headingRef} tabIndex={-1}>
          <nav className="gs-progress" aria-label="Setup steps">
            <ol>
              {steps.map((label, index) => (
                <li
                  key={label}
                  className={
                    index === step
                      ? "is-current"
                      : index < step
                        ? "is-done"
                        : ""
                  }
                >
                  <button
                    type="button"
                    disabled={
                      signingOpen ||
                      stepLocked(index, step, {
                        nda: ndaSigned,
                        github: installation !== null,
                      })
                    }
                    onClick={() => setStep(index)}
                    aria-current={index === step ? "step" : undefined}
                  >
                    <span>
                      {index < step ? <Check size={12} /> : index + 1}
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
              details={counterpartyDetails(draft, account)}
              initialDocumentId={draft.ndaDocumentId}
              onDocument={(id) => patch({ ndaDocumentId: id })}
              onComplete={(id) => void ndaCompleted(id)}
              onBack={() => setSigningOpen(false)}
            />
          ) : (
            <form onSubmit={(event) => void submit(event)}>
              {step === 0 &&
                (server.nda ? (
                  <StepTitle title="Your mutual NDA is signed.">
                    Signed {new Date(server.nda.signed_at).toLocaleDateString()}
                    .
                  </StepTitle>
                ) : (
                  <AccessStep account={account} draft={draft} patch={patch} />
                ))}
              {step === 1 && (
                <TeamStep
                  account={account}
                  server={server}
                  draft={draft}
                  patch={patch}
                  installation={installation}
                  onRefresh={refresh}
                  onGithubVerified={githubChecked}
                />
              )}
              {step === 2 && (
                <ReviewStep
                  account={account}
                  server={server}
                  draft={draft}
                  installation={installation}
                  patch={patch}
                  onEdit={() => setStep(0)}
                />
              )}
              <div className="gs-actions">
                <button
                  type="submit"
                  className="gr-button gr-button--main gs-primary"
                  disabled={checkingGithub || submitting}
                  aria-describedby={githubError ? "gs-github-error" : undefined}
                >
                  {submitting
                    ? "Starting project…"
                    : checkingGithub
                      ? "Checking GitHub…"
                      : step === 0 && !ndaSigned
                        ? "Review & sign NDA"
                        : step === 2
                          ? "Start project"
                          : "Continue"}
                  <ArrowRight size={15} />
                </button>
                {step > 0 && (
                  <button
                    type="button"
                    className="gs-back"
                    onClick={() => setStep(step - 1)}
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
              {submitError && (
                <p role="alert" className="gs-note">
                  {submitError}
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
                setSigningOpen(false);
                setDraft(emptyOnboarding());
              }}
            >
              Clear form
            </button>
          </div>
        </main>
      )}
      {view !== "complete" && (
        <OnboardingHelp
          step={
            view === "introduction"
              ? "Get an engineer"
              : (steps[step] ?? "Project setup")
          }
        />
      )}
    </Shell>
  );
};

const Shell = ({
  wide = false,
  children,
}: {
  wide?: boolean;
  children: ReactNode;
}) => (
  <div className="gr-root gs-root" data-theme="taupe">
    <div className="gs-auth-shell">
      <div
        className={`gs-auth-container${wide ? " gs-auth-container--signing" : ""}`}
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
        {children}
      </div>
    </div>
  </div>
);
