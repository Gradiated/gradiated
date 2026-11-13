import { useMutation, useQueries, useQuery } from "@tanstack/react-query";
import { Navigate, useRouter } from "@tanstack/react-router";
import { Check, LoaderCircle } from "lucide-react";
import { useEffect, useState } from "react";

import {
  getCurrentUser,
  listWorkspaces,
  selectOAuthWorkspace,
} from "@/api/queries";
import { authClient } from "@/auth";
import { AuthCard } from "@/components/auth-card";
import { OptionSelect, type Option } from "@/components/option-select";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/errors";
import {
  authorizeUrl,
  OAUTH_SCOPE_DESCRIPTIONS,
  organizationLabel,
} from "@/lib/oauth";
import { queryKeys } from "@/lib/query-keys";
import { useWorkspaceSelection } from "@/store/workspace-selection";

const Loading = () => (
  <AuthCard>
    <div className="grid place-items-center p-10">
      <LoaderCircle
        aria-label="Loading"
        className="size-5 animate-spin text-muted-foreground"
      />
    </div>
  </AuthCard>
);

// The signed authorization query exactly as it arrived; the router's parsed search would re-encode it.
const useOAuthQuery = () => useRouter().history.location;

const SignIn = () => {
  const { pathname, search } = useOAuthQuery();

  return <Navigate to="/login" search={{ next: `${pathname}${search}` }} />;
};

// The API sends a signed-out user here; after sign-in the authorization starts again.
export const OAuthLoginPage = () => {
  const session = authClient.useSession();
  const { search } = useOAuthQuery();

  useEffect(() => {
    if (session.data)
      window.location.replace(
        authorizeUrl(search, import.meta.env.VITE_API_URL ?? location.origin),
      );
  }, [session.data, search]);

  if (session.isPending || session.data) return <Loading />;

  return <SignIn />;
};

interface OAuthClient {
  client_name?: string;
  client_uri?: string;
}

interface OAuthRedirect {
  url?: string;
  redirect_uri?: string;
}

const respond = async (query: string, accept: boolean) => {
  const { data, error } = await authClient.$fetch<OAuthRedirect>(
    "/oauth2/consent",
    {
      method: "POST",
      body: { accept, oauth_query: query.slice(1) },
    },
  );
  const target = data?.url ?? data?.redirect_uri;
  if (error || !target)
    throw new Error(error?.message ?? "The authorization could not finish.");

  window.location.assign(target);
};

export const OAuthConsentPage = () => {
  const session = authClient.useSession();
  const query = useOAuthQuery().search;
  const search = new URLSearchParams(query);
  const clientId = search.get("client_id") ?? "";
  const scopes = (search.get("scope") ?? "").split(" ").filter(Boolean);
  const signedIn = Boolean(session.data);

  const client = useQuery({
    queryKey: ["oauth-client", clientId],
    queryFn: async () => {
      const { data } = await authClient.$fetch<OAuthClient>(
        "/oauth2/public-client",
        { query: { client_id: clientId } },
      );

      return data ?? {};
    },
    enabled: signedIn && clientId !== "",
    retry: false,
  });
  const me = useQuery({
    queryKey: queryKeys.me,
    queryFn: getCurrentUser,
    enabled: signedIn,
  });
  const organizations = me.data?.organizations ?? [];
  const workspaceLists = useQueries({
    queries: organizations.map((organization) => ({
      queryKey: queryKeys.workspaces(organization.id),
      queryFn: () => listWorkspaces(organization.id),
    })),
  });
  const options: Option<string>[] = organizations.flatMap(
    (organization, index) =>
      (workspaceLists[index]?.data?.data ?? []).map((workspace) => ({
        value: workspace.id,
        label: workspace.name,
        group: organizationLabel(organization, organizations),
        groupKey: organization.id,
        disabled: organization.status !== "active",
      })),
  );

  const remembered = useWorkspaceSelection((state) => state.workspaceId);
  const [chosen, setChosen] = useState<string>();
  const workspaceId =
    chosen ??
    options.find((option) => option.value === remembered && !option.disabled)
      ?.value ??
    options.find((option) => !option.disabled)?.value;

  const allow = useMutation({
    mutationFn: async (selected: string) => {
      await selectOAuthWorkspace(selected);
      await respond(query, true);
    },
  });
  const deny = useMutation({ mutationFn: () => respond(query, false) });

  if (session.isPending) return <Loading />;
  if (!session.data) return <SignIn />;
  if (me.isPending || workspaceLists.some((list) => list.isPending))
    return <Loading />;

  const name = client.data?.client_name ?? "An application";
  const failure = allow.error ?? deny.error ?? me.error;
  const pending = allow.isPending || deny.isPending;

  return (
    <AuthCard>
      <div className="space-y-6 p-6 md:p-8">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold">Connect {name} to Gradiated</h1>
          <p className="text-sm text-muted-foreground">
            Signed in as {session.data.user.email}.
          </p>
        </div>

        <div className="space-y-2">
          <p className="text-sm font-medium">Workspace</p>
          {workspaceId ? (
            <OptionSelect
              label="Workspace"
              value={workspaceId}
              options={options}
              onValueChange={setChosen}
              disabled={pending}
              className="w-full"
            />
          ) : (
            <p className="text-sm text-muted-foreground">
              You have no workspace this application can use.
            </p>
          )}
          <p className="text-xs text-muted-foreground">
            {name} can act only in this workspace.
          </p>
        </div>

        <ul className="space-y-2 text-sm">
          {scopes.map((scope) => (
            <li key={scope} className="flex gap-2">
              <Check className="mt-0.5 size-4 shrink-0" />
              {OAUTH_SCOPE_DESCRIPTIONS[scope] ?? scope}
            </li>
          ))}
        </ul>

        {failure ? (
          <p role="alert" className="text-sm text-destructive">
            {errorMessage(failure, "The authorization could not finish.")}
          </p>
        ) : null}

        <div className="flex justify-end gap-2">
          <Button
            variant="outline"
            disabled={pending}
            onClick={() => deny.mutate()}
          >
            Deny
          </Button>
          <Button
            disabled={pending || !workspaceId}
            onClick={() => workspaceId && allow.mutate(workspaceId)}
          >
            {allow.isPending ? <LoaderCircle className="animate-spin" /> : null}
            Allow
          </Button>
        </div>
      </div>
    </AuthCard>
  );
};
