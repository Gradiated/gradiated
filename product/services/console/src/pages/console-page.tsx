import { RefreshCw } from "lucide-react";
import { useEffect, type ComponentProps, type ReactNode } from "react";
import { analytics, setAnalyticsScope } from "@/lib/analytics";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { useProductContext } from "@/hooks/use-product-context";
import { cn } from "@/lib/utils";

const WIDTH_CLASS = {
  default: "max-w-5xl",
  wide: "max-w-7xl",
} as const;

export const ConsolePage = ({
  page,
  title,
  description,
  actions,
  back,
  width = "default",
  children,
}: {
  page: ComponentProps<typeof AppShell>["activePage"];
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  back?: ReactNode;
  width?: keyof typeof WIDTH_CLASS;
  children: ReactNode;
}) => {
  const context = useProductContext();
  const { user, organizationId, workspaceId, workspaces } = context;
  const isDefault =
    workspaces.find((workspace) => workspace.id === workspaceId)?.is_default ??
    false;

  useEffect(() => {
    if (!user || !organizationId || !workspaceId) return;

    setAnalyticsScope(user.id, organizationId, workspaceId, isDefault);
  }, [user?.id, organizationId, workspaceId, isDefault]);

  return (
    <AppShell
      user={context.user}
      organizationId={context.organizationId}
      workspaces={context.workspaces}
      workspaceId={context.workspaceId}
      onSelectOrganization={(id) => {
        analytics.track("organization_selected", { organization_id: id });
        context.selectOrganization(id);
      }}
      onSelectWorkspace={(id) => {
        analytics.track("workspace_selected", {
          organization_id: context.organizationId,
          workspace_id: id,
        });
        context.selectWorkspace(id);
      }}
      onSignOut={context.signOut}
      activePage={page}
      pageTitle={title}
    >
      <main className="min-w-0 flex-1 px-5 py-8 lg:px-10 lg:py-10">
        <div className={cn("mx-auto w-full", WIDTH_CLASS[width])}>
          {back}
          <div className="mb-7 flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
            <div className="min-w-0">
              <h1 className="text-3xl font-semibold tracking-[-0.035em] break-words">
                {title}
              </h1>
              {description ? (
                <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
                  {description}
                </p>
              ) : null}
            </div>
            {actions ? (
              <div className="flex shrink-0 items-center gap-2">{actions}</div>
            ) : null}
          </div>
          {children}
        </div>
      </main>
    </AppShell>
  );
};

export const LoadFailed = ({
  subject,
  retrying,
  onRetry,
  className,
}: {
  subject: string;
  retrying: boolean;
  onRetry: () => void;
  className?: string;
}) => (
  <div
    role="alert"
    className={cn(
      "grid min-h-48 place-items-center px-6 text-center",
      className,
    )}
  >
    <div>
      <p className="text-sm font-medium">Could not load {subject}.</p>
      <Button
        variant="outline"
        size="sm"
        className="mt-3 text-foreground"
        disabled={retrying}
        onClick={onRetry}
      >
        <RefreshCw className={retrying ? "animate-spin" : ""} />
        Retry
      </Button>
    </div>
  </div>
);
