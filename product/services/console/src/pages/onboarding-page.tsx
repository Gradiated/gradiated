import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Navigate, useNavigate, useSearch } from "@tanstack/react-router";
import { ArrowRight, LoaderCircle } from "lucide-react";
import { useState, type FormEvent } from "react";

import { updateOrganization, type CurrentUser } from "@/api/queries";
import { ImpersonationBanner } from "@/components/impersonation-banner";
import { AuthCard } from "@/components/auth-card";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { useCurrentUser, useSession } from "@/hooks/use-session";
import { httpStatus } from "@/lib/errors";
import {
  organizationToOnboard,
  suggestedOrganizationName,
} from "@/lib/onboarding";
import { POST_TRAINING_JOURNEY } from "@/lib/login-search";
import { queryKeys } from "@/lib/query-keys";
import { LoadFailed } from "@/pages/console-page";
import { PostTrainingOnboarding } from "@/pages/engineer-onboarding/post-training-onboarding";
import { useWorkspaceSelection } from "@/store/workspace-selection";

export const OnboardingPage = () => {
  const { journey, organization: requestedOrganization } = useSearch({
    from: "/onboarding",
  });
  const postTraining = journey === POST_TRAINING_JOURNEY;
  const { user, signOut } = useSession();
  const me = useCurrentUser();
  const [onboarded, setOnboarded] = useState<string>();
  const organization = organizationToOnboard(user, requestedOrganization);

  if (me.isError && httpStatus(me.error) !== 401)
    return (
      <main className="grid min-h-svh place-items-center bg-muted">
        <LoadFailed
          subject="your account"
          retrying={me.isFetching}
          onRetry={() => void me.refetch()}
        />
      </main>
    );

  if (!user)
    return (
      <main className="grid min-h-svh place-items-center bg-muted">
        <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
      </main>
    );

  if (!organization && !postTraining) return <Navigate to="/models" />;

  return (
    <>
      <ImpersonationBanner user={user} />
      {organization ? (
        <AuthCard>
          <OrganizationSetup
            user={user}
            organization={organization}
            onOnboarded={postTraining ? setOnboarded : undefined}
            onSignOut={() => void signOut()}
          />
        </AuthCard>
      ) : (
        <PostTrainingOnboarding
          user={user}
          organization={requestedOrganization ?? onboarded}
        />
      )}
    </>
  );
};

const OrganizationSetup = ({
  user,
  organization,
  onSignOut,
  onOnboarded,
}: {
  user: CurrentUser;
  organization: CurrentUser["organizations"][number];
  onSignOut: () => void;
  onOnboarded: ((organizationId: string) => void) | undefined;
}) => {
  const domain = user.company_email_domain;
  const [name, setName] = useState(suggestedOrganizationName(domain));
  const [autoJoin, setAutoJoin] = useState(true);
  const client = useQueryClient();
  const navigate = useNavigate();
  const selectOrganization = useWorkspaceSelection((s) => s.selectOrganization);
  const selectWorkspace = useWorkspaceSelection((s) => s.selectWorkspace);

  const save = useMutation({
    mutationFn: () =>
      updateOrganization(organization.id, {
        name: name.trim(),
        ...(domain ? { auto_join_domain: autoJoin ? domain : null } : {}),
        onboarding_completed: true,
      }),
    onSuccess: async (updated) => {
      onOnboarded?.(updated.id);
      client.setQueryData<CurrentUser>(
        queryKeys.me,
        (current) =>
          current && {
            ...current,
            organizations: current.organizations.map((row) =>
              row.id === updated.id ? updated : row,
            ),
          },
      );
      selectOrganization(updated.id);
      selectWorkspace(updated.default_workspace_id);
      if (onOnboarded) return;

      await navigate({ to: "/models", search: { welcome: true } });
    },
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (name.trim() && !save.isPending) save.mutate();
  };

  return (
    <form className="p-6 md:p-9" onSubmit={submit}>
      <FieldGroup>
        <div className="flex flex-col gap-2">
          <h1 className="text-2xl font-bold tracking-tight">
            Set up your organization
          </h1>
          <p className="text-sm leading-6 text-muted-foreground">
            Your organization holds your team&apos;s workspaces, API keys and
            billing. You can change this later in Settings.
          </p>
        </div>
        <Field>
          <FieldLabel htmlFor="organization-name">Organization name</FieldLabel>
          <Input
            id="organization-name"
            name="scopeLabel"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Acme Inc"
            maxLength={200}
            required
            autoFocus
            autoComplete="off"
            data-1p-ignore="true"
            disabled={save.isPending}
          />
          {domain ? null : (
            <FieldDescription>
              Your company or project name. Just you? Use your own name.
            </FieldDescription>
          )}
        </Field>
        {domain ? (
          <Field
            orientation="horizontal"
            className="rounded-lg border bg-muted/30 p-4"
          >
            <Checkbox
              id="auto-join"
              checked={autoJoin}
              onCheckedChange={(checked) => setAutoJoin(checked === true)}
              disabled={save.isPending}
            />
            <FieldContent>
              <FieldLabel htmlFor="auto-join">
                Let anyone with an @{domain} email join
              </FieldLabel>
              <FieldDescription>
                Teammates who sign in with a verified{" "}
                <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">
                  @{domain}
                </code>{" "}
                address are added to {name.trim() || "your organization"} as
                members automatically.
              </FieldDescription>
            </FieldContent>
          </Field>
        ) : null}
        {save.error ? <FieldError>{save.error.message}</FieldError> : null}
        <Field>
          <Button
            type="submit"
            className="w-full"
            disabled={!name.trim() || save.isPending}
          >
            {save.isPending ? (
              <LoaderCircle className="size-4 animate-spin" />
            ) : null}
            Continue
            {save.isPending ? null : <ArrowRight className="size-4" />}
          </Button>
          <p className="text-center text-sm text-muted-foreground">
            Signed in as {user.email} ·{" "}
            <button
              type="button"
              className="text-foreground underline underline-offset-4"
              onClick={onSignOut}
            >
              Not you?
            </button>
          </p>
        </Field>
      </FieldGroup>
    </form>
  );
};
