import { Toaster } from "@/components/ui/sonner";
import NiceModal from "@ebay/nice-modal-react";
import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
  type QueryKey,
} from "@tanstack/react-query";
import {
  Outlet,
  RouterProvider,
  createRootRoute,
  createRoute,
  createRouter,
  lazyRouteComponent,
  redirect,
} from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { httpStatus, isClientError } from "@/lib/errors";
import { endSession } from "@/lib/session";
import { ApiKeysPage } from "@/pages/api-keys-page";
import { BillingPage } from "@/pages/billing-page";
import { LoginPage } from "@/pages/login-page";
import { ModelsPage } from "@/pages/models-page";

import "./styles.css";

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

const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

const MAX_QUERY_RETRIES = 3;

const endSessionWhenUnauthorized = (error: Error) => {
  if (httpStatus(error) === 401) void endSession(queryClient, router);
};

const queryFailed = (error: Error, { queryKey }: { queryKey: QueryKey }) => {
  const status = httpStatus(error);

  if (status === 401) {
    void endSession(queryClient, router);
    return;
  }

  console.error("query_failed", String(queryKey[0]), status ?? error.name);
};

const queryClient: QueryClient = new QueryClient({
  queryCache: new QueryCache({ onError: queryFailed }),
  mutationCache: new MutationCache({ onError: endSessionWhenUnauthorized }),
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      refetchOnWindowFocus: false,
      retry: (failureCount, error) =>
        failureCount < MAX_QUERY_RETRIES && !isClientError(error),
    },
  },
});

const rootElement = document.getElementById("root");
if (!rootElement) throw new Error("The console needs a #root element.");

createRoot(rootElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <NiceModal.Provider>
        <RouterProvider router={router} />
        <Toaster />
      </NiceModal.Provider>
    </QueryClientProvider>
  </StrictMode>,
);
