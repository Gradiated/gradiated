import NiceModal from "@ebay/nice-modal-react";
import { Link, useMatchRoute, type LinkProps } from "@tanstack/react-router";
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
  WalletCards,
  Settings,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";

import {
  createOrganization,
  createWorkspace,
  type CurrentUser,
  type Workspace,
} from "@/api/queries";
import { CreateNameDialog } from "@/components/create-name-dialog";
import { Logo } from "@/components/logo";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
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
import { useScopeCreation } from "@/hooks/use-product-context";
import type { SignOutResult } from "@/hooks/use-session";
import { useFeatureFlag, type FeatureFlag } from "@/lib/feature-flags";

interface NavGroup {
  label: string;
  flag?: FeatureFlag;
  items: {
    to: NonNullable<LinkProps["to"]>;
    label: string;
    icon: LucideIcon;
  }[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    label: "Research",
    flag: "training",
    items: [{ to: "/tasks", label: "Training", icon: FlaskConical }],
  },
  {
    label: "Inference",
    items: [
      { to: "/models", label: "Models", icon: PackageOpen },
      { to: "/api-keys", label: "API keys", icon: KeyRound },
      { to: "/usage", label: "Usage", icon: ChartNoAxesCombined },
      { to: "/logs", label: "Logs", icon: Logs },
      { to: "/billing", label: "Billing", icon: WalletCards },
    ],
  },
];

export const AppSidebar = ({
  user,
  organizationId,
  workspaces,
  workspaceId,
  onSelectOrganization,
  onSelectWorkspace,
  onSignOut,
}: {
  user: CurrentUser | undefined;
  organizationId: string;
  workspaces: Workspace[];
  workspaceId: string;
  onSelectOrganization: (organizationId: string) => void;
  onSelectWorkspace: (workspaceId: string) => void;
  onSignOut: () => Promise<SignOutResult>;
}) => {
  const { isMobile } = useSidebar();
  const matchRoute = useMatchRoute();
  const [signOutFailed, setSignOutFailed] = useState(false);
  const { organizationCreated, workspaceCreated } = useScopeCreation();
  const selectedWorkspace = workspaces.find(
    (workspace) => workspace.id === workspaceId,
  );

  const addWorkspace = () =>
    void NiceModal.show(CreateNameDialog, {
      title: "Create a workspace",
      label: "Workspace name",
      placeholder: "Production",
      submitLabel: "Create workspace",
      emptyMessage: "Enter a workspace name.",
      submit: async (name) => {
        workspaceCreated(await createWorkspace(organizationId, { name }));
      },
    });

  const signOut = async () => {
    setSignOutFailed((await onSignOut()) === "failed");
  };

  const addOrganization = () =>
    void NiceModal.show(CreateNameDialog, {
      title: "Create an organization",
      label: "Organization name",
      placeholder: "Acme Inc",
      submitLabel: "Create organization",
      emptyMessage: "Enter an organization name.",
      submit: async (name) => {
        organizationCreated(await createOrganization({ name }));
      },
    });

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
                  <span className="flex size-8 shrink-0 items-center justify-center">
                    <Logo className="size-6" aria-hidden="true" />
                  </span>
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
                  <SwitcherItem
                    key={workspace.id}
                    name={workspace.name}
                    selected={workspace.id === workspaceId}
                    onSelect={() => onSelectWorkspace(workspace.id)}
                  />
                ))}
                <DropdownMenuSeparator />
                <AddItem
                  label="Add workspace"
                  disabled={!organizationId}
                  onSelect={addWorkspace}
                />
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        {NAV_GROUPS.map((group) =>
          group.flag ? (
            <FlaggedNavSection
              key={group.label}
              flag={group.flag}
              group={group}
            />
          ) : (
            <NavSection key={group.label} group={group} />
          ),
        )}
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              asChild
              tooltip="Settings"
              isActive={Boolean(matchRoute({ to: "/settings" }))}
            >
              <Link to="/settings">
                <Settings />
                <span>Settings</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
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
                      <SwitcherItem
                        key={organization.id}
                        name={organization.name}
                        selected={organization.id === organizationId}
                        onSelect={() => onSelectOrganization(organization.id)}
                      />
                    ))}
                    <DropdownMenuSeparator />
                    <AddItem
                      label="Add organization"
                      onSelect={addOrganization}
                    />
                  </DropdownMenuSubContent>
                </DropdownMenuSub>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  className={signOutFailed ? "text-destructive" : undefined}
                  onSelect={(event) => {
                    event.preventDefault();
                    void signOut();
                  }}
                >
                  <LogOut />
                  {signOutFailed ? "Sign out failed. Retry" : "Sign out"}
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

const FlaggedNavSection = ({
  flag,
  group,
}: {
  flag: FeatureFlag;
  group: NavGroup;
}) => (useFeatureFlag(flag) === true ? <NavSection group={group} /> : null);

const NavSection = ({ group }: { group: NavGroup }) => {
  const matchRoute = useMatchRoute();

  return (
    <SidebarGroup>
      <SidebarGroupLabel>{group.label}</SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          {group.items.map(({ to, label, icon: Icon }) => (
            <SidebarMenuItem key={label}>
              <SidebarMenuButton
                asChild
                isActive={Boolean(matchRoute({ to, fuzzy: true }))}
                tooltip={label}
              >
                <Link to={to}>
                  <Icon />
                  <span>{label}</span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  );
};

const SwitcherItem = ({
  name,
  selected,
  onSelect,
}: {
  name: string;
  selected: boolean;
  onSelect: () => void;
}) => (
  <DropdownMenuItem className="gap-2 p-2" onSelect={onSelect}>
    <span className="grid size-7 place-items-center rounded-md border bg-background text-xs font-semibold">
      {name.slice(0, 1).toUpperCase()}
    </span>
    <span className="min-w-0 flex-1 truncate">{name}</span>
    {selected ? <Check className="size-4 text-muted-foreground" /> : null}
  </DropdownMenuItem>
);

const AddItem = ({
  label,
  disabled = false,
  onSelect,
}: {
  label: string;
  disabled?: boolean;
  onSelect: () => void;
}) => (
  <DropdownMenuItem
    className="gap-2 p-2"
    disabled={disabled}
    onSelect={onSelect}
  >
    <span className="grid size-7 place-items-center rounded-md border bg-background">
      <Plus className="size-4" />
    </span>
    <span className="font-medium text-muted-foreground">{label}</span>
  </DropdownMenuItem>
);

const initials = (name: string | undefined) => {
  if (!name) return "G";

  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
};
