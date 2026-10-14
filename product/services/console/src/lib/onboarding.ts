import type { CurrentUser } from "@/api/queries";

export const organizationToOnboard = (user: CurrentUser | undefined) =>
  user?.organizations.find(
    (organization) =>
      organization.role === "owner" && !organization.onboarding_completed,
  );

export const suggestedOrganizationName = (domain: string | null) => {
  const label = domain?.split(".")[0] ?? "";

  return label.charAt(0).toUpperCase() + label.slice(1);
};
