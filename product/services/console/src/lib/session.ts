import type { QueryClient } from "@tanstack/react-query";
import type { RegisteredRouter } from "@tanstack/react-router";

import type { LoginSearch } from "@/lib/login-search";

import { resetUser } from "@/lib/feature-flags";
import { usePlaygroundStore } from "@/store/playground";
import { useWorkspaceSelection } from "@/store/workspace-selection";

export const endSession = async (
  queryClient: QueryClient,
  router: RegisteredRouter,
  search: LoginSearch = {},
) => {
  await router.navigate({ to: "/login", search });

  queryClient.clear();
  useWorkspaceSelection.getState().reset();
  usePlaygroundStore.getState().reset();
  resetUser();
};
