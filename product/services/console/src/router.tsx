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
import { LoginPage } from "@/pages/login-page";
import { ModelsPage } from "@/pages/models-page";

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
  component: LoginPage,
});

const apiKeysRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/api-keys",
  component: ApiKeysPage,
});

const modelsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/models",
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

const routeTree = rootRoute.addChildren([
  indexRoute,
  loginRoute,
  apiKeysRoute,
  modelsRoute,
  tasksRoute,
  taskRoute,
  billingRoute,
  usageRoute,
  logsRoute,
]);

export const createConsoleRouter = (history?: RouterHistory) =>
  createRouter({ routeTree, ...(history ? { history } : {}) });

export const router = createConsoleRouter();

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
