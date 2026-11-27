import { SessionSync } from "@/components/session-sync";
import { Toaster } from "@/components/ui/sonner";
import NiceModal from "@ebay/nice-modal-react";
import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
  type QueryKey,
} from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { needsStaffSessionRecovery } from "@/api/client";
import { getCurrentUser } from "@/api/queries";
import { httpStatus, isClientError } from "@/lib/errors";
import { signsOutOnUnauthorized } from "@/lib/grad/config";
import { loginSearchFor } from "@/lib/engineer-onboarding";
import { toastMutationError } from "@/lib/mutation-errors";
import { endSession } from "@/lib/session";
import { router } from "@/router";

import "./styles.css";

const MAX_QUERY_RETRIES = 3;

const signIn = () =>
  endSession(queryClient, router, loginSearchFor(router.state.location));

const handleUnauthorized = (error: Error) => {
  if (!signsOutOnUnauthorized(error)) return;
  if (needsStaffSessionRecovery(error)) {
    void getCurrentUser().catch((failure: unknown) => {
      if (httpStatus(failure) === 401) void signIn();
    });
  } else if (httpStatus(error) === 401) void signIn();
};

const queryFailed = (error: Error, { queryKey }: { queryKey: QueryKey }) => {
  const status = httpStatus(error);

  if (status === 401 && signsOutOnUnauthorized(error)) {
    handleUnauthorized(error);
    return;
  }

  console.error("query_failed", String(queryKey[0]), status ?? error.name);
};

const queryClient: QueryClient = new QueryClient({
  queryCache: new QueryCache({ onError: queryFailed }),
  mutationCache: new MutationCache({
    onError: (error, variables, context, mutation) => {
      handleUnauthorized(error);
      toastMutationError(error, variables, context, mutation);
    },
  }),
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
      <SessionSync />
      <NiceModal.Provider>
        <RouterProvider router={router} />
        <Toaster />
      </NiceModal.Provider>
    </QueryClientProvider>
  </StrictMode>,
);
