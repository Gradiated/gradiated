import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "@tanstack/react-router";
import { useEffect } from "react";

import { getCurrentUser } from "@/api/queries";
import { authClient } from "@/auth";
import { identifyUser } from "@/lib/feature-flags";
import { queryKeys } from "@/lib/query-keys";
import { endSession } from "@/lib/session";

export type SignOutResult = "signed-out" | "failed";

export const useCurrentUser = () =>
  useQuery({ queryKey: queryKeys.me, queryFn: getCurrentUser });

export const useSession = () => {
  const queryClient = useQueryClient();
  const router = useRouter();
  const me = useCurrentUser();

  useEffect(() => {
    if (me.data) identifyUser(me.data);
  }, [me.data]);

  const signOut = async (): Promise<SignOutResult> => {
    const failureStatus = await authClient.signOut().then(
      ({ error }) => error?.status,
      (error: unknown) => (error instanceof Error ? error.name : typeof error),
    );

    if (failureStatus !== undefined) {
      console.error("sign_out_failed", failureStatus);
      return "failed";
    }

    await endSession(queryClient, router);

    return "signed-out";
  };

  return { user: me.data, signOut };
};
