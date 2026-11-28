import { useFeatureFlag, type FeatureFlagState } from "@/lib/feature-flags";

export const TRAINING_FLAG = "grad-training";

// Unset until grad's public routes exist (api.gradiated.com's ALB routes).
// Without it the training pages stay off even when the flag is on.
export const GRAD_API_URL = import.meta.env.VITE_GRAD_API_URL || undefined;

export const trainingAvailability = (
  flag: FeatureFlagState,
  apiUrl: string | undefined,
): FeatureFlagState => (apiUrl ? flag : false);

// Training pages render, mint tokens and call grad only when this is true.
export const useTrainingAvailable = () =>
  trainingAvailability(useFeatureFlag(TRAINING_FLAG), GRAD_API_URL);

// Every grad query and mutation key starts with this. A 401 from grad means
// the training token was refused or could not be minted; it says nothing
// about the console session, so it never signs the member out. (Keys, not
// the SDK's error class, keep the SDK out of the console's main chunk.)
export const GRAD_KEY = ["grad"] as const;

export const gradKeys = {
  all: (workspaceId: string) => [...GRAD_KEY, workspaceId] as const,
  runs: (workspaceId: string) => ["grad", workspaceId, "runs"] as const,
  run: (workspaceId: string, id: string) =>
    ["grad", workspaceId, "run", id] as const,
  runEvents: (workspaceId: string, id: string) =>
    ["grad", workspaceId, "run-events", id] as const,
  checkpoints: (workspaceId: string, runId: string) =>
    ["grad", workspaceId, "checkpoints", runId] as const,
  datasets: (workspaceId: string) => ["grad", workspaceId, "datasets"] as const,
  imports: (workspaceId: string) => ["grad", workspaceId, "imports"] as const,
  sources: (workspaceId: string) => ["grad", workspaceId, "sources"] as const,
  evals: (workspaceId: string) => ["grad", workspaceId, "evals"] as const,
};

export const isGradKey = (key: readonly unknown[] | undefined) =>
  key?.[0] === GRAD_KEY[0];
