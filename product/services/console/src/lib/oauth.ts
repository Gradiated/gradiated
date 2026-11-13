// Parameters the API adds when it signs an authorization request for the console.
const SIGNING_PARAMETERS = ["sig", "exp", "ba_iat", "ba_param", "ba_pl"];

// After sign-in, the original authorization request runs again with the new session.
export const authorizeUrl = (search: string, apiOrigin: string): string => {
  const query = new URLSearchParams(search);
  for (const name of SIGNING_PARAMETERS) query.delete(name);

  // The user has just signed in, so a client's request to sign in again is satisfied.
  const prompt = query
    .get("prompt")
    ?.split(" ")
    .filter((value) => value && value !== "login");
  if (prompt?.length) query.set("prompt", prompt.join(" "));
  else query.delete("prompt");

  return new URL(`/api/auth/oauth2/authorize?${query}`, apiOrigin).href;
};

export const isOAuthPath = (path: string): boolean =>
  /^\/oauth\/(login|consent)(\?|$)/.test(path);

export const OAUTH_SCOPE_DESCRIPTIONS: Record<string, string> = {
  mcp: "Read and manage the workspace's models, usage, generations, tasks and training runs, as you.",
  offline_access: "Stay connected after this browser session ends.",
};

// Organization names are not unique, so a shared name is told apart by its slug.
export const organizationLabel = (
  organization: { name: string; slug: string },
  organizations: readonly { name: string }[],
): string =>
  organizations.filter(({ name }) => name === organization.name).length > 1
    ? `${organization.name} (${organization.slug})`
    : organization.name;
