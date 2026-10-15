import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { ReactElement, ReactNode } from "react";

import {
  createApiKey,
  getCurrentUser,
  listApiKeys,
  listWorkspaces,
  type ApiKey,
  type CurrentUser,
  type Workspace,
} from "../../api/queries";

type SessionStatus = "loading" | "guest" | "ready" | "error";

type DocsSessionValue = {
  apiKey: string | null;
  apiKeys: ApiKey[];
  canManageKeys: boolean;
  clearApiKey: () => void;
  createDocsKey: () => Promise<string | null>;
  error: string | null;
  organization: CurrentUser["organizations"][number] | null;
  refresh: () => Promise<void>;
  selectOrganization: (organizationId: string) => Promise<void>;
  selectWorkspace: (workspaceId: string) => void;
  setApiKey: (value: string) => void;
  status: SessionStatus;
  user: CurrentUser | null;
  workspace: Workspace | null;
  workspaces: Workspace[];
};

const DocsSessionContext = createContext<DocsSessionValue | null>(null);

const errorStatus = (error: unknown): number | undefined =>
  error instanceof Error && "status" in error
    ? Number((error as Error & { status?: number }).status)
    : undefined;

export const DocsSessionProvider = ({
  children,
}: {
  children: ReactNode;
}): ReactElement => {
  const [status, setStatus] = useState<SessionStatus>("loading");
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [organization, setOrganization] = useState<
    CurrentUser["organizations"][number] | null
  >(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [apiKey, setApiKeyState] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadOrganization = useCallback(
    async (
      nextOrganization: CurrentUser["organizations"][number],
    ): Promise<void> => {
      setOrganization(nextOrganization);
      setApiKeyState(null);
      setApiKeys([]);
      const workspaceList = await listWorkspaces(nextOrganization.id);
      const activeWorkspaces = workspaceList.data.filter(
        (item) => item.archived_at === null,
      );
      const nextWorkspace =
        activeWorkspaces.find(
          (item) => item.id === nextOrganization.default_workspace_id,
        ) ??
        activeWorkspaces.find((item) => item.is_default) ??
        activeWorkspaces[0] ??
        null;
      setWorkspaces(activeWorkspaces);
      setWorkspace(nextWorkspace);
      if (!nextWorkspace) return;

      if (nextOrganization.role === "admin") {
        const keyList = await listApiKeys(
          nextOrganization.id,
          nextWorkspace.id,
        );
        setApiKeys(keyList.data);
      }
    },
    [],
  );

  const refresh = useCallback(async (): Promise<void> => {
    setStatus("loading");
    setError(null);
    try {
      const nextUser = await getCurrentUser();
      setUser(nextUser);
      const nextOrganization =
        nextUser.organizations.find((item) => item.status === "active") ??
        nextUser.organizations[0] ??
        null;
      if (nextOrganization) await loadOrganization(nextOrganization);
      setStatus("ready");
    } catch (nextError) {
      setUser(null);
      setOrganization(null);
      setWorkspaces([]);
      setWorkspace(null);
      setApiKeys([]);
      setApiKeyState(null);
      if (errorStatus(nextError) === 401) {
        setStatus("guest");
        return;
      }
      setError(
        errorStatus(nextError) === undefined
          ? "We could not connect to your Gradiated account."
          : nextError instanceof Error
            ? nextError.message
            : "We could not load your Gradiated account.",
      );
      setStatus("error");
    }
  }, [loadOrganization]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const selectOrganization = useCallback(
    async (organizationId: string): Promise<void> => {
      const nextOrganization = user?.organizations.find(
        (item) => item.id === organizationId,
      );
      if (!nextOrganization) return;
      setError(null);
      try {
        await loadOrganization(nextOrganization);
      } catch (nextError) {
        setError(
          nextError instanceof Error
            ? nextError.message
            : "Could not load this organization. Try again.",
        );
      }
    },
    [loadOrganization, user],
  );

  const selectWorkspace = useCallback(
    (workspaceId: string): void => {
      const nextWorkspace = workspaces.find((item) => item.id === workspaceId);
      if (!nextWorkspace || !organization) return;
      setWorkspace(nextWorkspace);
      setApiKeyState(null);
      setApiKeys([]);
      if (organization.role !== "admin") {
        return;
      }
      void listApiKeys(organization.id, nextWorkspace.id)
        .then((result) => setApiKeys(result.data))
        .catch((nextError: unknown) =>
          setError(
            nextError instanceof Error
              ? nextError.message
              : "Could not load API keys. Try again.",
          ),
        );
    },
    [organization, workspaces],
  );

  const createDocsKey = useCallback(async (): Promise<string | null> => {
    if (!organization || !workspace) return null;
    setError(null);
    try {
      const created = await createApiKey(organization.id, workspace.id);
      setApiKeys((current) => [created.api_key, ...current]);
      setApiKeyState(created.secret);
      return created.secret;
    } catch (nextError) {
      setError(
        nextError instanceof Error
          ? nextError.message
          : "The API key could not be created.",
      );
      return null;
    }
  }, [organization, workspace]);

  const value = useMemo<DocsSessionValue>(
    () => ({
      apiKey,
      apiKeys,
      canManageKeys: organization?.role === "admin",
      clearApiKey: () => setApiKeyState(null),
      createDocsKey,
      error,
      organization,
      refresh,
      selectOrganization,
      selectWorkspace,
      setApiKey: (value) => setApiKeyState(value.trim() || null),
      status,
      user,
      workspace,
      workspaces,
    }),
    [
      apiKey,
      apiKeys,
      createDocsKey,
      error,
      organization,
      refresh,
      selectOrganization,
      selectWorkspace,
      status,
      user,
      workspace,
      workspaces,
    ],
  );

  return (
    <DocsSessionContext.Provider value={value}>
      {children}
    </DocsSessionContext.Provider>
  );
};

export const useDocsSession = (): DocsSessionValue => {
  const value = useContext(DocsSessionContext);
  if (!value) throw new Error("DocsSessionProvider is missing.");
  return value;
};
