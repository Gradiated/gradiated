import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useRouter } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { ApiError } from "@/api/client";
import {
  getEngineerOnboarding,
  submitEngineerOnboarding,
  type EngineerOnboarding,
  type GithubInstallation,
} from "@/api/engineer-onboarding";
import type { CurrentUser } from "@/api/queries";
import { AuthCard } from "@/components/auth-card";
import { Brand } from "@/components/brand";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { FieldError } from "@/components/ui/field";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  engineerOnboardingKey,
  changesNda,
  chooseAccount,
  counterpartyDetails,
  draftStorageKey,
  emptyDraft,
  engineerSubmission,
  ndaPending as isNdaPending,
  restoreDraft,
  sectionId,
  startBlockers,
  submitProblem,
  type OnboardingAccount,
  type OnboardingDraft,
  type OnboardingSection,
} from "@/lib/engineer-onboarding";
import { POST_TRAINING_JOURNEY } from "@/lib/login-search";
import { cn } from "@/lib/utils";
import { GithubAppInstallation } from "@/pages/engineer-onboarding/github-installation";
import { NdaSigning } from "@/pages/engineer-onboarding/nda-signing";
import {
  ContextSection,
  NdaSection,
  PageHeader,
  ProjectPanel,
  ProjectStarted,
  Section,
  type UpdateDraft,
} from "@/pages/engineer-onboarding/onboarding-steps";
import { SlackInvitation } from "@/pages/engineer-onboarding/slack-invitation";
import { useWorkspaceSelection } from "@/store/workspace-selection";

const errorMessage = (error: unknown, fallback: string) =>
  error instanceof Error ? error.message : fallback;

export const PostTrainingOnboarding = ({
  user,
  organization,
  from,
}: {
  user: CurrentUser;
  organization: string | undefined;
  from?: string | undefined;
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

  if (choice.kind === "not_admin")
    return (
      <AuthCard>
        <div className="flex flex-col gap-2 p-6 md:p-9">
          <h1 className="text-2xl font-bold tracking-tight">
            Ask an admin to start your project
          </h1>
          <p className="text-sm leading-6 text-muted-foreground">
            Only an admin of {choice.organization} can set up a post-training
            project. Ask one to sign in and start it, or to make you an admin.
          </p>
          <OnboardingHelp step="Organization admin" />
          {from ? <BackToConsole from={from} className="mt-2" /> : null}
        </div>
      </AuthCard>
    );

  return (
    <PostTrainingWorkflow
      key={choice.account.userId + ":" + choice.account.organizationId}
      account={choice.account}
      from={from}
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
        <div className="flex flex-col gap-2">
          <h1 className="text-2xl font-bold tracking-tight">
            Choose your organization
          </h1>
          <p className="text-sm leading-6 text-muted-foreground">
            Which team is this project for?
          </p>
        </div>
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

const BackToConsole = ({
  from,
  className,
}: {
  from: string;
  className?: string;
}) => {
  const router = useRouter();

  return (
    <Button
      variant="ghost"
      size="sm"
      className={cn("self-start", className)}
      onClick={() => router.history.push(from)}
    >
      <ArrowLeft />
      Back to console
    </Button>
  );
};

const PageShell = ({
  from,
  children,
}: {
  from?: string | undefined;
  children: ReactNode;
}) => (
  <main className="min-h-svh bg-background">
    <div className="mx-auto flex max-w-6xl flex-col gap-10 px-4 pt-8 pb-24 md:px-6 md:pt-10">
      <div className="self-start">
        <Brand />
      </div>
      {/* Sits just above the page's h1, its arrow in line with the text. */}
      {from ? <BackToConsole from={from} className="-mb-6 -ml-3" /> : null}
      {children}
    </div>
  </main>
);

const PostTrainingWorkflow = ({
  account,
  from,
}: {
  account: OnboardingAccount;
  from?: string | undefined;
}) => {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const router = useRouter();
  const selectOrganization = useWorkspaceSelection(
    (state) => state.selectOrganization,
  );
  const queryKey = engineerOnboardingKey(account.organizationId);
  const onboarding = useQuery({
    queryKey,
    queryFn: () => getEngineerOnboarding(account.organizationId),
  });
  const server = onboarding.data;
  const [draft, setDraft] = useState(() => loadDraft(account));
  const [saved, setSaved] = useState(true);
  const [installation, setInstallation] = useState<GithubInstallation | null>(
    null,
  );
  const [githubAccounts, setGithubAccounts] = useState(0);
  const [signingOpen, setSigningOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [problem, setProblem] = useState<{
    message: string;
    section?: OnboardingSection;
  } | null>(null);
  const installationRef = useRef(installation);
  installationRef.current = installation;

  useEffect(() => {
    try {
      localStorage.setItem(draftStorageKey(account), JSON.stringify(draft));
      setSaved(true);
    } catch {
      setSaved(false);
    }
  }, [draft, account]);

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

  if (server.submitted_at)
    return (
      <PageShell>
        <ProjectStarted
          onConsole={() => {
            selectOrganization(account.organizationId);
            if (from) router.history.push(from);
            else void navigate({ to: "/playground" });
          }}
          onReset={
            import.meta.env.DEV
              ? () =>
                  void fetch(
                    `/api/v1/organizations/${account.organizationId}/engineer-onboarding/submission`,
                    { method: "DELETE" },
                  ).then(() => onboarding.refetch())
              : undefined
          }
          account={account}
          server={server}
        />
      </PageShell>
    );

  const ndaPending = isNdaPending(server, draft);
  const blockers = startBlockers(server, draft, installation, githubAccounts);

  const goTo = (section: OnboardingSection) => {
    const element = document.getElementById(sectionId(section));
    element?.scrollIntoView({ behavior: "smooth", block: "start" });
    element?.focus({ preventScroll: true });
  };

  const finish = async (current: OnboardingEngineerState) => {
    setSubmitting(true);
    setProblem(null);
    try {
      const result = await submitEngineerOnboarding(
        account.organizationId,
        engineerSubmission(current.server, current.draft, current.installation),
      );
      queryClient.setQueryData<EngineerOnboarding>(queryKey, result);
    } catch (error) {
      const known = submitProblem(
        error instanceof ApiError ? error.code : undefined,
      );
      setProblem({
        message:
          known?.message ??
          errorMessage(error, "Could not start your project. Please retry."),
        ...(known ? { section: known.section } : {}),
      });
    } finally {
      setSubmitting(false);
    }
  };

  const start = () => {
    if (submitting || !installation || blockers.length) return;

    if (ndaPending) {
      setProblem(null);
      setSigningOpen(true);
      return;
    }

    void finish({ server, draft, installation });
  };

  const ndaCompleted = async (documentId: string) => {
    const signedDraft = { ...draft, ndaDocumentId: documentId };
    setDraft(signedDraft);
    setSigningOpen(false);
    try {
      const { data } = await refresh();
      const current = installationRef.current;
      if (data && current)
        await finish({
          server: data,
          draft: signedDraft,
          installation: current,
        });
    } catch (error) {
      setProblem({
        message: errorMessage(
          error,
          "Could not confirm your NDA. Please retry.",
        ),
        section: "nda",
      });
    }
  };

  return (
    <PageShell from={from}>
      <PageHeader title="Let’s start your project.">
        Connect your code, tell us where to reach you, and a post-training
        researcher picks it up within a working day.
      </PageHeader>
      <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="flex min-w-0 flex-col gap-4">
          <Section
            section="code"
            title="Repository access"
            invalid={problem?.section === "code"}
          >
            <GithubAppInstallation
              organizationId={account.organizationId}
              selectedId={installation?.id ?? null}
              onChange={(next, accounts) => {
                setInstallation(next);
                setGithubAccounts(accounts);
                if (problem?.section === "code") setProblem(null);
              }}
            />
          </Section>
          <Section
            section="contact"
            title="Where we’ll talk"
            invalid={problem?.section === "contact"}
          >
            <SlackInvitation
              account={account}
              server={server}
              draft={draft}
              patch={patch}
              onInvited={refresh}
            />
          </Section>
          <NdaSection
            account={account}
            server={server}
            draft={draft}
            patch={patch}
          />
          <ContextSection server={server} draft={draft} patch={patch} />
          <div className="flex flex-wrap items-center justify-between gap-2 px-1 text-sm text-muted-foreground">
            <p>
              Signed in as {account.email}
              {saved ? null : " · Progress won’t be saved on this device"}
            </p>
            <OnboardingHelp step="Project setup" />
          </div>
        </div>
        <ProjectPanel
          account={account}
          server={server}
          draft={draft}
          blockers={blockers}
          ndaPending={ndaPending}
          submitting={submitting}
          error={problem}
          onStart={start}
          onGoTo={goTo}
        />
      </div>
      <Dialog open={signingOpen} onOpenChange={setSigningOpen}>
        <DialogContent className="max-h-[92svh] max-w-5xl overflow-y-auto">
          <DialogTitle className="sr-only">
            Review and sign your NDA
          </DialogTitle>
          <DialogDescription className="sr-only">
            Mutual NDA between {draft.legalName || account.company} and PostHog
            Inc.
          </DialogDescription>
          <NdaSigning
            organizationId={account.organizationId}
            details={counterpartyDetails(draft, account)}
            initialDocumentId={draft.ndaDocumentId}
            onDocument={(id) => patch({ ndaDocumentId: id })}
            onComplete={(id) => void ndaCompleted(id)}
            onBack={() => setSigningOpen(false)}
          />
        </DialogContent>
      </Dialog>
    </PageShell>
  );
};

interface OnboardingEngineerState {
  server: EngineerOnboarding;
  draft: OnboardingDraft;
  installation: GithubInstallation;
}
