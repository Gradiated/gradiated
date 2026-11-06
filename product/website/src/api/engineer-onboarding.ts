import type { components } from "./schema";
import { api, requireData } from "./client";

export type EngineerOnboarding = components["schemas"]["EngineerOnboarding"];
export type EngineerOnboardingSubmission =
  components["schemas"]["EngineerOnboardingSubmission"];

export const getEngineerOnboarding = (
  organizationId: string,
): Promise<EngineerOnboarding> =>
  requireData(
    api.GET("/api/v1/organizations/{organization_id}/engineer-onboarding", {
      params: { path: { organization_id: organizationId } },
    }),
  );

export const submitEngineerOnboarding = (
  organizationId: string,
  submission: EngineerOnboardingSubmission,
): Promise<EngineerOnboarding> =>
  requireData(
    api.POST(
      "/api/v1/organizations/{organization_id}/engineer-onboarding/submission",
      {
        params: { path: { organization_id: organizationId } },
        body: submission,
      },
    ),
  );
