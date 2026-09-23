import { Navigate } from "@tanstack/react-router";
import type { ReactNode } from "react";

import { useFeatureFlag } from "@/lib/feature-flags";

export const TrainingGate = ({ children }: { children: ReactNode }) => {
  const flag = useFeatureFlag("training");

  if (flag === "loading") return null;
  if (!flag) return <Navigate to="/models" replace />;

  return <>{children}</>;
};
