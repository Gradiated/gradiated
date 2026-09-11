import NiceModal from "@ebay/nice-modal-react";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  Building2,
  ChartNoAxesCombined,
  Check,
  ChevronsUpDown,
  FlaskConical,
  KeyRound,
  LogOut,
  Logs,
  PackageOpen,
  Plus,
  Settings2,
  WalletCards,
} from "lucide-react";

import type { CurrentUser, Workspace } from "@/api/queries";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { CreateOrganizationDialog } from "@/components/create-organization-dialog";
import { CreateWorkspaceDialog } from "@/components/create-workspace-dialog";
import { useFeatureFlag } from "@/lib/feature-flags";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar";

type Organization = CurrentUser["organizations"][number];

export const AppSidebar = ({
  user,
  organizationId,
  workspaces,
  workspaceId,
  onSelectOrganization,
  onSelectWorkspace,
  onSignOut,
  activePage,
}: {
  user: CurrentUser | undefined;
  organizationId: string;
  workspaces: Workspace[];
  workspaceId: string;
  onSelectOrganization: (organizationId: string) => void;
  onSelectWorkspace: (workspaceId: string) => void;
  onSignOut: () => void;
  activePage: "api-keys" | "billing" | "logs" | "models" | "tasks" | "usage";
}) => {
  const { isMobile } = useSidebar();
  const trainingConsole = useFeatureFlag("training");
  const queryClient = useQueryClient();
  const selectedOrganization =
    user?.organizations.find(
      (organization) => organization.id === organizationId,
    ) ?? user?.organizations[0];
  const selectedWorkspace =
    workspaces.find((workspace) => workspace.id === workspaceId) ??
    workspaces[0];

  const organizationCreated = (
    createdOrganizationId: string,
    defaultWorkspaceId: string,
  ) => {
    onSelectOrganization(createdOrganizationId);
    onSelectWorkspace(defaultWorkspaceId);
    void queryClient.invalidateQueries({ queryKey: ["me"] });
    void queryClient.invalidateQueries({
      queryKey: ["workspaces", createdOrganizationId],
    });
  };

  const workspaceCreated = (workspace: Workspace) => {
    queryClient.setQueryData<{ data: Workspace[]; next_cursor: string | null }>(
      ["workspaces", workspace.organization_id],
      (current) => ({
        data: [
          ...(current?.data.filter((item) => item.id !== workspace.id) ?? []),
          workspace,
        ],
        next_cursor: current?.next_cursor ?? null,
      }),
    );
    onSelectWorkspace(workspace.id);
  };

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <SidebarMenuButton
                  size="lg"
                  className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
                  aria-label="Workspace menu"
                >
                  <img
                    className="aspect-square size-8"
                    src="/brand/gradiated-mark-dark.svg"
                    alt=""
                    width="32"
                    height="32"
                  />
                  <span className="min-w-0 flex-1 truncate text-left text-sm font-medium">
                    {selectedWorkspace?.name ?? "Select workspace"}
                  </span>
                  <ChevronsUpDown className="ml-auto size-4" />
                </SidebarMenuButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                className="min-w-56 rounded-lg"
                align="start"
                side={isMobile ? "bottom" : "right"}
                sideOffset={4}
              >
                <DropdownMenuLabel className="text-xs text-muted-foreground">
                  Workspaces
                </DropdownMenuLabel>
                {workspaces.map((workspace) => (
                  <WorkspaceItem
                    key={workspace.id}
                    workspace={workspace}
                    selected={workspace.id === selectedWorkspace?.id}
                    onSelect={() => onSelectWorkspace(workspace.id)}
                  />
                ))}
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  className="gap-2 p-2"
                  onSelect={() => {
                    void NiceModal.show(CreateWorkspaceDialog, {
                      organizationId,
                      onCreated: workspaceCreated,
                    });
                  }}
                >
                  <span className="grid size-7 place-items-center rounded-md border bg-background">
                    <Plus className="size-4" />
                  </span>
                  <span className="font-medium text-muted-foreground">
                    Add workspace
                  </span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        {trainingConsole === true ? (
          <SidebarGroup>
            <SidebarGroupLabel>Research</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                <SidebarMenuItem>
                  <SidebarMenuButton
                    asChild
                    isActive={activePage === "tasks"}
                    tooltip="Training"
                  >
                    <Link to="/tasks">
                      <FlaskConical />
                      <span>Training</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ) : null}
        <SidebarGroup>
          <SidebarGroupLabel>Inference</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton
                  asChild
                  isActive={activePage === "models"}
                  tooltip="Models"
                >
                  <Link to="/models">
                    <PackageOpen />
                    <span>Models</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  asChild
                  isActive={activePage === "api-keys"}
                  tooltip="API keys"
                >
                  <Link to="/api-keys">
                    <KeyRound />
                    <span>API keys</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  asChild
                  isActive={activePage === "usage"}
                  tooltip="Usage"
                >
                  <Link to="/usage">
                    <ChartNoAxesCombined />
                    <span>Usage</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  asChild
                  isActive={activePage === "logs"}
                  tooltip="Logs"
                >
                  <Link to="/logs">
                    <Logs />
                    <span>Logs</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  asChild
                  isActive={activePage === "billing"}
                  tooltip="Billing"
                >
                  <Link to="/billing">
                    <WalletCards />
                    <span>Billing</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <SidebarMenuButton
                  size="lg"
                  className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
                  aria-label="Account menu"
                >
                  <Avatar className="size-8 rounded-lg">
                    <AvatarFallback className="rounded-lg bg-muted text-xs">
                      {initials(user?.name)}
                    </AvatarFallback>
                  </Avatar>
                  <span className="grid min-w-0 flex-1 text-left text-sm leading-tight">
                    <span className="truncate font-medium">{user?.name}</span>
                    <span className="truncate text-xs text-muted-foreground">
                      {user?.email}
                    </span>
                  </span>
                  <ChevronsUpDown className="ml-auto size-4" />
                </SidebarMenuButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                className="min-w-56 rounded-lg"
                side={isMobile ? "bottom" : "right"}
                align="end"
                sideOffset={4}
              >
                <DropdownMenuLabel className="font-normal">
                  <div className="grid gap-1">
                    <span className="font-medium">{user?.name}</span>
                    <span className="text-xs text-muted-foreground">
                      {user?.email}
                    </span>
                  </div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuSub>
                  <DropdownMenuSubTrigger>
                    <Building2 />
                    Change organization
                  </DropdownMenuSubTrigger>
                  <DropdownMenuSubContent className="min-w-56 rounded-lg">
                    <DropdownMenuLabel className="text-xs text-muted-foreground">
                      Organizations
                    </DropdownMenuLabel>
                    {user?.organizations.map((organization) => (
                      <OrganizationItem
                        key={organization.id}
                        organization={organization}
                        selected={organization.id === selectedOrganization?.id}
                        onSelect={() => onSelectOrganization(organization.id)}
                      />
                    ))}
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      className="gap-2 p-2"
                      onSelect={() => {
                        void NiceModal.show(CreateOrganizationDialog, {
                          onCreated: organizationCreated,
                        });
                      }}
                    >
                      <span className="grid size-7 place-items-center rounded-md border bg-background">
                        <Plus className="size-4" />
                      </span>
                      <span className="font-medium text-muted-foreground">
                        Add organization
                      </span>
                    </DropdownMenuItem>
                  </DropdownMenuSubContent>
                </DropdownMenuSub>
                <DropdownMenuItem disabled>
                  <Settings2 />
                  Account settings
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onSelect={onSignOut}>
                  <LogOut />
                  Sign out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
};

const WorkspaceItem = ({
  workspace,
  selected,
  onSelect,
}: {
  workspace: Workspace;
  selected: boolean;
  onSelect: () => void;
}) => {
  return (
    <DropdownMenuItem className="gap-2 p-2" onSelect={onSelect}>
      <span className="grid size-7 place-items-center rounded-md border bg-background text-xs font-semibold">
        {workspace.name.slice(0, 1).toUpperCase()}
      </span>
      <span className="min-w-0 flex-1 truncate">{workspace.name}</span>
      {selected ? <Check className="size-4 text-muted-foreground" /> : null}
    </DropdownMenuItem>
  );
};

const OrganizationItem = ({
  organization,
  selected,
  onSelect,
}: {
  organization: Organization;
  selected: boolean;
  onSelect: () => void;
}) => {
  return (
    <DropdownMenuItem className="gap-2 p-2" onSelect={onSelect}>
      <span className="grid size-7 place-items-center rounded-md border bg-background text-xs font-semibold">
        {organization.name.slice(0, 1).toUpperCase()}
      </span>
      <span className="min-w-0 flex-1 truncate">{organization.name}</span>
      {selected ? <Check className="size-4 text-muted-foreground" /> : null}
    </DropdownMenuItem>
  );
};

const initials = (name: string | undefined) => {
  if (!name) return "G";
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
};
