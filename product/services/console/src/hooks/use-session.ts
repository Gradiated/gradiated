import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "@tanstack/react-router";
import { useEffect } from "react";

import { getCurrentUser } from "@/api/queries";
import { authClient } from "@/auth";
import { analytics } from "@/lib/analytics";
import { identifyUser } from "@/lib/feature-flags";
import { queryKeys } from "@/lib/query-keys";
import type { LoginSearch } from "@/lib/login-search";
import { announceSessionChange } from "@/lib/session-sync";
import { endSession } from "@/lib/session";
import {
  clearEngineerPreview,
  engineerPreviewLoginPath,
  getEngineerPreviewUser,
  isEngineerPreview,
} from "@/lib/engineer-preview";

export type SignOutResult = "signed-out" | "failed";

export const useCurrentUser = () =>
  useQuery({
    queryKey: isEngineerPreview()
      ? [...queryKeys.me, "engineer-preview"]
      : queryKeys.me,
    queryFn: isEngineerPreview()
      ? () => Promise.resolve(getEngineerPreviewUser())
      : getCurrentUser,
  });

export const useSession = () => {
  const queryClient = useQueryClient();
  const router = useRouter();
  const me = useCurrentUser();

  useEffect(() => {
    if (me.data && !isEngineerPreview()) identifyUser(me.data);
  }, [me.data]);

  const signOut = async (search?: LoginSearch): Promise<SignOutResult> => {
    if (isEngineerPreview()) {
      clearEngineerPreview();
      window.location.assign(engineerPreviewLoginPath);
      return "signed-out";
    }

    if (me.data) analytics.track("sign_out_clicked", { user_id: me.data.id });

    const failureStatus = await authClient.signOut().then(
      ({ error }) => error?.status,
      (error: unknown) => (error instanceof Error ? error.name : typeof error),
    );

    if (failureStatus !== undefined) {
      console.error("sign_out_failed", failureStatus);
      return "failed";
    }

    announceSessionChange();
    await endSession(queryClient, router, search);

    return "signed-out";
  };

  return { user: me.data, signOut };
};
