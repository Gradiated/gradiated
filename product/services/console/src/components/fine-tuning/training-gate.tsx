import { Navigate } from "@tanstack/react-router";
import type { ReactNode } from "react";

import { useSession } from "@/hooks/use-session";
import { ConsolePage } from "@/pages/console-page";
import { Skeleton } from "@/components/ui/skeleton";
import { useFeatureFlag } from "@/lib/feature-flags";

export const TrainingGate = ({
  children,
  loadingContent,
}: {
  children: ReactNode;
  loadingContent?: ReactNode;
}) => {
  useSession();
  const flag = useFeatureFlag("training");

  if (flag === "loading")
    return (
      loadingContent ?? (
        <ConsolePage page="tasks" title="Tasks">
          <div role="status" aria-label="Loading tasks" className="space-y-4">
            <Skeleton className="h-10 w-64" />
            <Skeleton className="h-64 w-full" />
          </div>
        </ConsolePage>
      )
    );
  if (!flag) return <Navigate to="/models" replace />;

  return <>{children}</>;
};
