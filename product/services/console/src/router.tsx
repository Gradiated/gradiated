import {
  Outlet,
  createRootRoute,
  createRoute,
  createRouter,
  lazyRouteComponent,
  redirect,
  type RouterHistory,
} from "@tanstack/react-router";

import { ApiKeysPage } from "@/pages/api-keys-page";
import { BillingPage } from "@/pages/billing-page";
import { parseLoginSearch } from "@/lib/login-search";
import { LoginPage } from "@/pages/login-page";
import { ModelsPage } from "@/pages/models-page";
import { OnboardingPage } from "@/pages/onboarding-page";

const rootRoute = createRootRoute({ component: Outlet });

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  beforeLoad: () => {
    throw redirect({ to: "/api-keys" });
  },
});

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  validateSearch: parseLoginSearch,
  component: LoginPage,
});

const invitationAcceptRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/invitations/accept",
  validateSearch: (search: Record<string, unknown>) => ({
    ...(typeof search.token === "string" ? { token: search.token } : {}),
  }),
  component: lazyRouteComponent(
    () => import("@/pages/invitation-accept-page"),
    "InvitationAcceptPage",
  ),
});

const onboardingRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/onboarding",
  component: OnboardingPage,
});

const apiKeysRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/api-keys",
  component: ApiKeysPage,
});

const modelsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/models",
  validateSearch: (search: Record<string, unknown>) => ({
    ...(search.welcome === true || search.welcome === "true"
      ? { welcome: true }
      : {}),
  }),
  component: ModelsPage,
});

const tasksRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tasks",
  component: lazyRouteComponent(
    () => import("@/pages/tasks-page"),
    "TasksPage",
  ),
});

const taskRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tasks/$taskId",
  validateSearch: (search: Record<string, unknown>) => ({
    ...(typeof search.traceId === "string" && search.traceId
      ? { traceId: search.traceId }
      : {}),
  }),
  component: lazyRouteComponent(() => import("@/pages/task-page"), "TaskPage"),
});

const billingRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/billing",
  component: BillingPage,
});

const usageRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/usage",
  component: lazyRouteComponent(
    () => import("@/pages/usage-page"),
    "UsagePage",
  ),
});

const logsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/logs",
  validateSearch: (search: Record<string, unknown>) => ({
    ...(typeof search.apiKeyId === "string"
      ? { apiKeyId: search.apiKeyId }
      : {}),
  }),
  component: lazyRouteComponent(() => import("@/pages/logs-page"), "LogsPage"),
});

const settingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings",
  component: lazyRouteComponent(
    () => import("@/pages/settings/settings-layout"),
    "SettingsLayout",
  ),
});

const settingsIndexRoute = createRoute({
  getParentRoute: () => settingsRoute,
  path: "/",
  beforeLoad: () => {
    throw redirect({ to: "/settings/workspace" });
  },
});

const workspaceSettingsRoute = createRoute({
  getParentRoute: () => settingsRoute,
  path: "workspace",
  component: lazyRouteComponent(
    () => import("@/pages/settings/workspace-settings-page"),
    "WorkspaceSettingsPage",
  ),
});

const organizationSettingsRoute = createRoute({
  getParentRoute: () => settingsRoute,
  path: "organization",
  component: lazyRouteComponent(
    () => import("@/pages/settings/organization-settings-page"),
    "OrganizationSettingsPage",
  ),
});

const membersSettingsRoute = createRoute({
  getParentRoute: () => settingsRoute,
  path: "members",
  component: lazyRouteComponent(
    () => import("@/pages/settings/members-settings-page"),
    "MembersSettingsPage",
  ),
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  loginRoute,
  invitationAcceptRoute,
  onboardingRoute,
  apiKeysRoute,
  modelsRoute,
  tasksRoute,
  taskRoute,
  billingRoute,
  usageRoute,
  logsRoute,
  settingsRoute.addChildren([
    settingsIndexRoute,
    workspaceSettingsRoute,
    organizationSettingsRoute,
    membersSettingsRoute,
  ]),
]);

export const createConsoleRouter = (history?: RouterHistory) =>
  createRouter({ routeTree, ...(history ? { history } : {}) });

export const router = createConsoleRouter();

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
