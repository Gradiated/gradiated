import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { ArrowLeft, ArrowRight, Check, LoaderCircle } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { ApiError } from "@/api/client";
import {
  getEngineerOnboarding,
  getGithubInstallations,
  submitEngineerOnboarding,
  type EngineerOnboarding,
} from "@/api/engineer-onboarding";
import type { CurrentUser } from "@/api/queries";
import { AuthCard } from "@/components/auth-card";
import { Button } from "@/components/ui/button";
import { FieldError } from "@/components/ui/field";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  changesNda,
  chooseAccount,
  confirmationMessage,
  counterpartyDetails,
  draftStorageKey,
  emptyDraft,
  engineerSubmission,
  ndaReference,
  restoreDraft,
  resumeStep,
  resumeView,
  stepLocked,
  submitAction,
  submitProblem,
  type OnboardingAccount,
  type OnboardingDraft,
  type OnboardingView,
  type VerifiedInstallation,
} from "@/lib/engineer-onboarding";
import { POST_TRAINING_JOURNEY } from "@/lib/login-search";
import { cn } from "@/lib/utils";
import { NdaSigning } from "@/pages/engineer-onboarding/nda-signing";
import {
  NdaStep,
  ReviewStep,
  StepTitle,
  TeamStep,
  type UpdateDraft,
} from "@/pages/engineer-onboarding/onboarding-steps";

const steps = ["Mutual NDA", "Slack & GitHub", "Get to work"];

const githubRequiredMessage =
  "Install the Gradiated GitHub app and select at least one repository before continuing. If installation needs approval, ask your GitHub organization owner to approve it.";

const errorMessage = (error: unknown, fallback: string) =>
  error instanceof Error ? error.message : fallback;

const engineerOnboardingKey = (organizationId: string) => [
  "engineer-onboarding",
  organizationId,
];

export const PostTrainingOnboarding = ({
  user,
  organization,
}: {
  user: CurrentUser;
  organization: string | undefined;
}) => {
  const choice = chooseAccount(user, organization);

  if (choice.kind === "pick")
    return <OrganizationPicker organizations={choice.organizations} />;

  if (choice.kind === "missing")
    return (
      <AuthCard>
        <div className="flex flex-col gap-2 p-6 md:p-9">
          <h1 className="text-2xl font-bold tracking-tight">
            We couldn’t find that organization
          </h1>
          <p className="text-sm leading-6 text-muted-foreground">
            Ask an admin of your organization to invite you, then try again.
          </p>
          <OnboardingHelp step="Choose an organization" />
        </div>
      </AuthCard>
    );

  return (
    <PostTrainingWorkflow
      key={choice.account.userId + ":" + choice.account.organizationId}
      account={choice.account}
    />
  );
};

const OnboardingHelp = ({ step }: { step: string }) => (
  <p className="text-sm text-muted-foreground">
    Stuck?{" "}
    <a
      className="text-foreground underline underline-offset-4"
      href={`mailto:help@gradiated.com?subject=${encodeURIComponent(`Help with Gradiated setup: ${step}`)}`}
    >
      Email us
    </a>
  </p>
);

const OrganizationPicker = ({
  organizations,
}: {
  organizations: CurrentUser["organizations"];
}) => {
  const navigate = useNavigate();

  return (
    <AuthCard>
      <div className="flex flex-col gap-6 p-6 md:p-9">
        <StepTitle title="Choose your organization">
          Which team is this engineer for?
        </StepTitle>
        <Select
          onValueChange={(organization) =>
            void navigate({
              to: "/onboarding",
              search: { journey: POST_TRAINING_JOURNEY, organization },
            })
          }
        >
          <SelectTrigger aria-label="Organization" className="w-full">
            <SelectValue placeholder="Choose an organization" />
          </SelectTrigger>
          <SelectContent>
            {organizations.map((row) => (
              <SelectItem key={row.id} value={row.id}>
                {row.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <OnboardingHelp step="Choose an organization" />
      </div>
    </AuthCard>
  );
};

const loadDraft = (account: OnboardingAccount): OnboardingDraft => {
  try {
    return restoreDraft(
      JSON.parse(localStorage.getItem(draftStorageKey(account)) ?? "{}"),
    );
  } catch {
    return emptyDraft();
  }
};

const githubInstallationActive = async (
  organizationId: string,
  installationId: number,
  ndaDocumentId?: string,
) => {
  const result = await getGithubInstallations(organizationId, {
    ndaDocumentId,
    installationId,
  });

  return result.installations.some(
    (installation) => installation.id === installationId,
  );
};

const PostTrainingWorkflow = ({ account }: { account: OnboardingAccount }) => {
  const queryClient = useQueryClient();
  const queryKey = engineerOnboardingKey(account.organizationId);
  const onboarding = useQuery({
    queryKey,
    queryFn: () => getEngineerOnboarding(account.organizationId),
  });
  const server = onboarding.data;
  const [draft, setDraft] = useState(() => loadDraft(account));
  const [saved, setSaved] = useState(true);
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
  const resumed = useRef(false);

  useEffect(() => {
    if (!server || resumed.current) return;

    resumed.current = true;
    setView(resumeView(server));
    setStep(resumeStep(server));
  }, [server]);

  useEffect(() => {
    try {
      localStorage.setItem(draftStorageKey(account), JSON.stringify(draft));
      setSaved(true);
    } catch {
      setSaved(false);
    }
  }, [draft, account]);

  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [step, view, signingOpen]);

  const patch: UpdateDraft = (values) =>
    setDraft((current) => ({
      ...current,
      ...values,
      ...(changesNda(current, values) ? { ndaDocumentId: null } : {}),
    }));

  const refresh = () => onboarding.refetch({ throwOnError: true });

  if (!server)
    return (
      <AuthCard>
        <div className="flex flex-col items-start gap-4 p-6 md:p-9">
          {onboarding.isError ? (
            <>
              <FieldError>
                {errorMessage(
                  onboarding.error,
                  "Could not load your setup. Please retry.",
                )}
              </FieldError>
              <Button
                type="button"
                disabled={onboarding.isFetching}
                onClick={() => void onboarding.refetch()}
              >
                Try again
              </Button>
            </>
          ) : (
            <p role="status" className="text-sm text-muted-foreground">
              Restoring your setup…
            </p>
          )}
        </div>
      </AuthCard>
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
      const result = await submitEngineerOnboarding(
        account.organizationId,
        engineerSubmission(server, draft, current),
      );
      queryClient.setQueryData<EngineerOnboarding>(queryKey, result);
      if (result.submitted_at) setView("complete");
    } catch (error) {
      const problem = submitProblem(
        error instanceof ApiError ? error.code : undefined,
      );
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

  if (view === "complete") {
    const confirmation = confirmationMessage(server, account.email);

    return (
      <AuthCard className="max-w-xl">
        <section
          aria-label="Setup complete"
          className="flex flex-col gap-4 p-6 text-sm leading-6 md:p-9"
        >
          <h1 className="text-2xl font-bold tracking-tight">You’re all set</h1>
          <p>{confirmation.plan}</p>
          <p className="text-muted-foreground">{confirmation.followUp}</p>
        </section>
      </AuthCard>
    );
  }

  if (view === "introduction")
    return (
      <AuthCard className="max-w-xl">
        <div className="flex flex-col gap-6 p-6 md:p-9">
          <StepTitle title="Let’s get you set up with a forward deployed engineer">
            Self-serve. No sales call.
          </StepTitle>
          <p className="text-sm leading-6">
            A real human from our team will join you in Slack and work with your
            codebase to get more out of your models.
          </p>
          <Button
            type="button"
            className="self-start"
            onClick={() => {
              setStep(0);
              setView("steps");
            }}
          >
            Get started <ArrowRight />
          </Button>
          <OnboardingHelp step="Get an engineer" />
        </div>
      </AuthCard>
    );

  return (
    <AuthCard className={signingOpen ? "max-w-5xl" : "max-w-2xl"}>
      <div className="flex flex-col gap-7 p-6 md:p-9">
        <nav aria-label="Setup steps">
          <ol className="flex flex-wrap gap-2">
            {steps.map((label, index) => (
              <li key={label}>
                <button
                  type="button"
                  className={cn(
                    "flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium disabled:opacity-50",
                    index === step && "border-primary bg-primary/5",
                  )}
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
                  <span className="grid size-4 place-items-center">
                    {index < step ? <Check className="size-3" /> : index + 1}
                  </span>
                  {label}
                </button>
              </li>
            ))}
          </ol>
        </nav>
        {saved ? null : (
          <p role="status" className="text-sm text-muted-foreground">
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
          <form
            className="flex flex-col gap-7"
            onSubmit={(event) => void submit(event)}
          >
            {step === 0 ? (
              server.nda ? (
                <StepTitle title="Your mutual NDA is signed">
                  Signed {new Date(server.nda.signed_at).toLocaleDateString()}.
                </StepTitle>
              ) : (
                <NdaStep account={account} draft={draft} patch={patch} />
              )
            ) : null}
            {step === 1 ? (
              <TeamStep
                account={account}
                server={server}
                draft={draft}
                patch={patch}
                installation={installation}
                onRefresh={refresh}
                onGithubVerified={githubChecked}
              />
            ) : null}
            {step === 2 ? (
              <ReviewStep
                account={account}
                server={server}
                draft={draft}
                installation={installation}
                patch={patch}
                onEdit={() => setStep(0)}
              />
            ) : null}
            {githubError ? <FieldError>{githubError}</FieldError> : null}
            {submitError ? <FieldError>{submitError}</FieldError> : null}
            <div className="flex flex-row-reverse items-center justify-between gap-3">
              <Button type="submit" disabled={checkingGithub || submitting}>
                {submitting ? <LoaderCircle className="animate-spin" /> : null}
                {submitting
                  ? "Starting project…"
                  : checkingGithub
                    ? "Checking GitHub…"
                    : step === 0 && !ndaSigned
                      ? "Review & sign NDA"
                      : step === 2
                        ? "Start project"
                        : "Continue"}
                {submitting ? null : <ArrowRight />}
              </Button>
              {step > 0 ? (
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setStep(step - 1)}
                >
                  <ArrowLeft /> Back
                </Button>
              ) : null}
            </div>
          </form>
        )}
        <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-muted-foreground">
          <p>
            Signed in as {account.email} ·{" "}
            <button
              type="button"
              className="text-foreground underline underline-offset-4"
              onClick={() => {
                setSigningOpen(false);
                setDraft(emptyDraft());
              }}
            >
              Clear form
            </button>
          </p>
          <OnboardingHelp step={steps[step] ?? "Project setup"} />
        </div>
      </div>
    </AuthCard>
  );
};
