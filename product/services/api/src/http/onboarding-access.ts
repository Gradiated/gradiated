import type { OrganizationService } from "@gradiated/control";

import type { NdaDocument, PandaDocNda } from "../legal/pandadoc.js";
import { ApiProblem, problems, requireUser } from "./problems.js";

export type OnboardingOrganizations = Pick<
  OrganizationService,
  "listForUser" | "getOnboarding" | "recordOnboardingNda" | "submitOnboarding"
>;

export type OnboardingOwner = Parameters<PandaDocNda["read"]>[0];

export const requireOnboardingAdmin = async (
  context: Parameters<typeof requireUser>[0],
  organizations: Pick<OrganizationService, "listForUser">,
  organizationId: string,
) => {
  const user = await requireUser(context);
  if (user.impersonatedBy)
    throw new ApiProblem(
      problems.forbidden(
        "Leave impersonation before continuing engineer onboarding.",
      ),
    );

  const memberships = await organizations.listForUser(user.id);
  const organization = memberships.find(
    (membership) =>
      membership.id === organizationId &&
      membership.status === "active" &&
      membership.role === "admin",
  );
  if (!user.emailVerified || !organization)
    throw new ApiProblem(
      problems.forbidden(
        "A verified organization admin must complete engineer onboarding.",
      ),
    );

  return {
    organization,
    owner: { userId: user.id, email: user.email, organizationId },
  };
};

export const recordCompletedNda = async (
  organizations: Pick<OrganizationService, "recordOnboardingNda">,
  nda: Pick<PandaDocNda, "templateVersion">,
  owner: OnboardingOwner,
  document: NdaDocument,
) => {
  if (document.status !== "completed") return undefined;

  const onboarding = await organizations.recordOnboardingNda(
    owner.userId,
    owner.organizationId,
    {
      document_id: document.id,
      template_version: nda.templateVersion,
      signed_at: document.completed_at ?? new Date().toISOString(),
    },
  );

  return onboarding.nda;
};

export const requireRecordedNda = async (
  organizations: Pick<
    OrganizationService,
    "getOnboarding" | "recordOnboardingNda"
  >,
  nda: Pick<PandaDocNda, "read" | "templateVersion">,
  owner: OnboardingOwner,
  nextStep: string,
  documentId?: string,
) => {
  const { nda: recorded } = await organizations.getOnboarding(
    owner.userId,
    owner.organizationId,
  );
  if (recorded?.template_version === nda.templateVersion) return recorded;

  const confirmed = documentId
    ? await recordCompletedNda(
        organizations,
        nda,
        owner,
        await nda.read(owner, documentId),
      )
    : undefined;
  if (confirmed?.template_version === nda.templateVersion) return confirmed;

  throw new ApiProblem(
    problems.onboardingConflict(
      "nda_required",
      `Complete your mutual NDA before ${nextStep}.`,
    ),
  );
};
