import { invitationPath, type LoginSearch } from "./login-search";

export const parseOnboardingSearch = (
  search: Record<string, unknown>,
): { next?: "engineer" } =>
  search.next === "engineer" ? { next: "engineer" } : {};

export const engineerOnboardingUrl = (
  organizationId?: string,
  websiteUrl = import.meta.env.VITE_WEBSITE_URL ??
    (import.meta.env.DEV ? "http://localhost:5173" : "https://gradiated.com"),
) => {
  const url = new URL("/get-started/", websiteUrl);

  if (organizationId) url.searchParams.set("organization", organizationId);

  return url.toString();
};

export const signInCallbacks = (search: LoginSearch, consoleOrigin: string) => {
  const invitation = search.invitation
    ? invitationPath(search.invitation)
    : undefined;
  const engineer = !invitation && search.next === "engineer";
  const callbackUrl = (path: string) => new URL(path, consoleOrigin).toString();

  return {
    callbackURL: invitation
      ? callbackUrl(invitation)
      : engineer
        ? engineerOnboardingUrl()
        : callbackUrl("/api-keys"),
    newUserCallbackURL: callbackUrl(
      invitation ?? (engineer ? "/onboarding?next=engineer" : "/onboarding"),
    ),
    errorCallbackURL: callbackUrl(engineer ? "/login?next=engineer" : "/login"),
  };
};
