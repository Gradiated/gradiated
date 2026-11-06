import { submitEngineerOnboarding } from "./api/engineer-onboarding";
import type { EngineerOnboarding } from "./api/engineer-onboarding";
import { getGithubInstallations } from "./api/github";
import { engineerSubmission } from "./onboarding";
import type {
  OnboardingAccount,
  OnboardingDraft,
  VerifiedInstallation,
} from "./onboarding";

export const submitOnboarding = ({
  account,
  server,
  draft,
  installation,
}: {
  account: OnboardingAccount;
  server: EngineerOnboarding;
  draft: OnboardingDraft;
  installation: VerifiedInstallation;
}): Promise<EngineerOnboarding> =>
  submitEngineerOnboarding(
    account.organizationId,
    engineerSubmission(server, draft, installation),
  );

export const githubInstallationActive = async (
  organizationId: string,
  installationId: number,
  ndaDocumentId?: string,
) => {
  const result = await getGithubInstallations(organizationId, {
    ndaDocumentId,
    installationId,
  });

  return result.installations.some(
    (installation) => installation.id === installationId,
  );
};
