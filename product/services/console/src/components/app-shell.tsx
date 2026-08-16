import type { ReactNode } from "react";

import type { CurrentUser, Workspace } from "@/api/queries";
import { AppSidebar } from "@/components/app-sidebar";
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

export const AppShell = ({
  user,
  organizationId,
  workspaces,
  workspaceId,
  onSelectOrganization,
  onSelectWorkspace,
  onSignOut,
  activePage,
  pageTitle,
  children,
}: {
  user: CurrentUser | undefined;
  organizationId: string;
  workspaces: Workspace[];
  workspaceId: string;
  onSelectOrganization: (organizationId: string) => void;
  onSelectWorkspace: (workspaceId: string) => void;
  onSignOut: () => void;
  activePage: "api-keys" | "billing" | "models";
  pageTitle: string;
  children: ReactNode;
}) => {
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
        activePage={activePage}
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
