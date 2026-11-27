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

const oauthLoginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/oauth/login",
  component: lazyRouteComponent(
    () => import("@/pages/oauth-page"),
    "OAuthLoginPage",
  ),
});

const oauthConsentRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/oauth/consent",
  component: lazyRouteComponent(
    () => import("@/pages/oauth-page"),
    "OAuthConsentPage",
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
    ...(typeof search.task === "string" && search.task
      ? { task: search.task }
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

const reportSearch = (search: Record<string, unknown>) => ({
  ...(typeof search.eval === "string" && search.eval
    ? { eval: search.eval }
    : {}),
  ...(typeof search.case === "string" && search.case
    ? { case: search.case }
    : {}),
});

const versionRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tasks/$taskId/versions/$versionId",
  validateSearch: reportSearch,
  component: lazyRouteComponent(
    () => import("@/pages/version-page"),
    "VersionPage",
  ),
});

const sharedReportRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/share/$versionId/$signature",
  validateSearch: reportSearch,
  component: lazyRouteComponent(
    () => import("@/pages/shared-report-page"),
    "SharedReportPage",
  ),
});

const trainingIndexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/training",
  beforeLoad: () => {
    throw redirect({ to: "/training/runs" });
  },
});

const trainingRunsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/training/runs",
  component: lazyRouteComponent(
    () => import("@/pages/training/runs-page"),
    "RunsPage",
  ),
});

const trainingNewRunRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/training/runs/new",
  validateSearch: (search: Record<string, unknown>) => ({
    ...(typeof search.dataset === "string" && search.dataset
      ? { dataset: search.dataset }
      : {}),
  }),
  component: lazyRouteComponent(
    () => import("@/pages/training/new-run-page"),
    "NewRunPage",
  ),
});

const trainingRunRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/training/runs/$runId",
  component: lazyRouteComponent(
    () => import("@/pages/training/run-page"),
    "RunPage",
  ),
});

const trainingDatasetsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/training/datasets",
  component: lazyRouteComponent(
    () => import("@/pages/training/datasets-page"),
    "DatasetsPage",
  ),
});

const DATASET_TABS = ["records", "versions", "sources", "imports"] as const;

const trainingDatasetRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/training/datasets/$datasetName",
  validateSearch: (search: Record<string, unknown>) => {
    const tab = DATASET_TABS.find((value) => value === search.tab);
    const version = Number(search.version);

    return {
      ...(tab ? { tab } : {}),
      ...(Number.isInteger(version) && version > 0 ? { version } : {}),
    };
  },
  component: lazyRouteComponent(
    () => import("@/pages/training/dataset-page"),
    "DatasetPage",
  ),
});

const trainingEvalsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/training/evals",
  component: lazyRouteComponent(
    () => import("@/pages/training/evals-page"),
    "EvalsPage",
  ),
});

const trainingEvalRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/training/evals/$evalId",
  component: lazyRouteComponent(
    () => import("@/pages/training/eval-page"),
    "EvalPage",
  ),
});

const trainingUsageRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/training/usage",
  component: lazyRouteComponent(
    () => import("@/pages/training/training-usage-page"),
    "TrainingUsagePage",
  ),
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
  oauthLoginRoute,
  oauthConsentRoute,
  onboardingRoute,
  githubReturnRoute,
  onboardingJourneyRoute,
  apiKeysRoute,
  modelsRoute,
  playgroundRoute,
  tasksRoute,
  taskRoute,
  versionRoute,
  sharedReportRoute,
  trainingIndexRoute,
  trainingRunsRoute,
  trainingNewRunRoute,
  trainingRunRoute,
  trainingDatasetsRoute,
  trainingDatasetRoute,
  trainingEvalsRoute,
  trainingEvalRoute,
  trainingUsageRoute,
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
