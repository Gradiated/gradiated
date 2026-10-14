import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Navigate, useNavigate } from "@tanstack/react-router";
import { ArrowRight, LoaderCircle } from "lucide-react";
import { useState, type FormEvent } from "react";

import { updateOrganization, type CurrentUser } from "@/api/queries";
import { Brand } from "@/components/brand";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import { queryKeys } from "@/lib/query-keys";
import { LoadFailed } from "@/pages/console-page";
import { useWorkspaceSelection } from "@/store/workspace-selection";

export const OnboardingPage = () => {
  const { user, signOut } = useSession();
  const me = useCurrentUser();
  const organization = organizationToOnboard(user);

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

  if (!organization) return <Navigate to="/models" />;

  return (
    <main className="flex min-h-svh flex-col items-center justify-center bg-muted p-6 md:p-10">
      <div className="w-full max-w-md">
        <div className="mb-6">
          <Brand />
        </div>
        <Card className="overflow-hidden p-0 shadow-xl shadow-black/5">
          <CardContent className="p-0">
            <OrganizationSetup
              user={user}
              organization={organization}
              onSignOut={() => void signOut()}
            />
          </CardContent>
        </Card>
      </div>
    </main>
  );
};

const OrganizationSetup = ({
  user,
  organization,
  onSignOut,
}: {
  user: CurrentUser;
  organization: CurrentUser["organizations"][number];
  onSignOut: () => void;
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
