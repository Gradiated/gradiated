import { GradError } from "@gradiated/grad";

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

// A 401 from grad means the training token was refused or could not be
// minted; it says nothing about the console session, so it never signs out.
export const signsOutOnUnauthorized = (error: unknown) =>
  !(error instanceof GradError);
