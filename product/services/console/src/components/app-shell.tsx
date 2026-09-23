import type { ReactNode } from "react";

import type { CurrentUser, Workspace } from "@/api/queries";
import { AppSidebar } from "@/components/app-sidebar";
import { Button } from "@/components/ui/button";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
} from "@/components/ui/breadcrumb";
import { Separator } from "@/components/ui/separator";
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { useWorkspaceList } from "@/hooks/use-product-context";
import { useCurrentUser, type SignOutResult } from "@/hooks/use-session";
import { httpStatus } from "@/lib/errors";

export const AppShell = ({
  user,
  organizationId,
  workspaces,
  workspaceId,
  onSelectOrganization,
  onSelectWorkspace,
  onSignOut,
  pageTitle,
  children,
}: {
  user: CurrentUser | undefined;
  organizationId: string;
  workspaces: Workspace[];
  workspaceId: string;
  onSelectOrganization: (organizationId: string) => void;
  onSelectWorkspace: (workspaceId: string) => void;
  onSignOut: () => Promise<SignOutResult>;
  activePage: "api-keys" | "billing" | "logs" | "models" | "tasks" | "usage";
  pageTitle: string;
  children: ReactNode;
}) => {
  const me = useCurrentUser();
  const workspaceList = useWorkspaceList(organizationId);
  const failed = [me, workspaceList].find(
    (query) => query.isError && httpStatus(query.error) !== 401,
  );

  if (failed) {
    return (
      <main className="grid min-h-svh place-items-center p-6">
        <div className="flex items-center gap-3 text-sm text-muted-foreground">
          Could not load your account.
          <Button
            variant="outline"
            size="sm"
            onClick={() => void failed.refetch()}
          >
            Retry
          </Button>
        </div>
      </main>
    );
  }

  return (
    <SidebarProvider>
      <AppSidebar
        user={user}
        organizationId={organizationId}
        workspaces={workspaces}
        workspaceId={workspaceId}
        onSelectOrganization={onSelectOrganization}
        onSelectWorkspace={onSelectWorkspace}
        onSignOut={onSignOut}
      />
      <SidebarInset>
        <header className="flex h-16 shrink-0 items-center gap-2 border-b bg-background transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-12">
          <div className="flex items-center gap-2 px-4">
            <SidebarTrigger className="-ml-1" />
            <Separator orientation="vertical" className="mr-2 h-4" />
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbPage>{pageTitle}</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </div>
        </header>
        {children}
      </SidebarInset>
    </SidebarProvider>
  );
};
