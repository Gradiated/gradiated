import { Navigate } from "@tanstack/react-router";
import type { ReactNode } from "react";

import { useTrainingAvailable } from "@/lib/grad/config";

// Off (or still loading flags): nothing renders, so no token is minted and
// nothing calls grad. Off sends direct URLs home.
export const TrainingGate = ({ children }: { children: ReactNode }) => {
  const available = useTrainingAvailable();

  if (available === "loading") return null;
  if (!available) return <Navigate to="/" replace />;

  return children;
};
