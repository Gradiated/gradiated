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
import { parseOnboardingSearch } from "@/lib/engineer-onboarding";
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
  validateSearch: parseOnboardingSearch,
  component: OnboardingPage,
});

const githubReturnRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/onboarding/github-connected",
  validateSearch: (search: Record<string, unknown>) => ({
    ...(typeof search.error === "string" ? { error: search.error } : {}),
  }),
  component: lazyRouteComponent(
    () => import("@/pages/engineer-onboarding/github-return"),
    "GithubReturnPage",
  ),
});

const onboardingJourneyRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/onboarding/$journey",
  beforeLoad: ({ params }) => {
    throw redirect({
      to: "/onboarding",
      search: parseOnboardingSearch({ journey: params.journey }),
    });
  },
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

const playgroundRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/playground",
  validateSearch: (search: Record<string, unknown>) => ({
    ...(typeof search.model === "string" && search.model
      ? { model: search.model }
      : {}),
  }),
  component: lazyRouteComponent(
    () => import("@/pages/playground-page"),
    "PlaygroundPage",
  ),
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

const workspacePrivacySettingsRoute = createRoute({
  getParentRoute: () => settingsRoute,
  path: "workspace/privacy",
  component: lazyRouteComponent(
    () => import("@/pages/settings/workspace-privacy-settings-page"),
    "WorkspacePrivacySettingsPage",
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

const adminRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/admin",
  component: lazyRouteComponent(
    () => import("@/pages/admin-page"),
    "AdminPage",
  ),
});

const adminOrganizationRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/admin/organizations/$organizationId",
  component: lazyRouteComponent(
    () => import("@/pages/admin-organization-page"),
    "AdminOrganizationPage",
  ),
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  adminRoute,
  adminOrganizationRoute,
  loginRoute,
  invitationAcceptRoute,
  onboardingRoute,
  githubReturnRoute,
  onboardingJourneyRoute,
  apiKeysRoute,
  modelsRoute,
  playgroundRoute,
  tasksRoute,
  taskRoute,
  billingRoute,
  usageRoute,
  logsRoute,
  settingsRoute.addChildren([
    settingsIndexRoute,
    workspaceSettingsRoute,
    workspacePrivacySettingsRoute,
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
