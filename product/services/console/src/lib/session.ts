import type { QueryClient } from "@tanstack/react-query";
import type { RegisteredRouter } from "@tanstack/react-router";

import { resetUser } from "@/lib/feature-flags";
import { useWorkspaceSelection } from "@/store/workspace-selection";

export const endSession = async (
  queryClient: QueryClient,
  router: RegisteredRouter,
) => {
  await router.navigate({ to: "/login" });

  queryClient.clear();
  useWorkspaceSelection.getState().reset();
  resetUser();
};
