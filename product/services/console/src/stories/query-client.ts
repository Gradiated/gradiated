import { MutationCache, QueryClient } from "@tanstack/react-query";

import { toastMutationError } from "@/lib/mutation-errors";

// Stories share the app's mutation error toasts and skip retries.
export const createStoryQueryClient = () =>
  new QueryClient({
    mutationCache: new MutationCache({ onError: toastMutationError }),
    defaultOptions: { queries: { retry: false } },
  });
