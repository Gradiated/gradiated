import { oauthProvider } from "@better-auth/oauth-provider";
import type { BetterAuthPlugin } from "better-auth";
import { createAuthMiddleware } from "better-auth/api";
import {
  OAUTH_ACCESS_TOKEN_PREFIX,
  OAUTH_WORKSPACE_SCOPE,
} from "@gradiated/control";

export interface OAuthConfiguration {
  consoleUrl: string;
  mcpResource: string;
}

const SCOPES = [OAUTH_WORKSPACE_SCOPE, "offline_access"];

// No consent has this reference, so a session without a chosen workspace always reaches the consent page.
const NO_WORKSPACE = "none";

// MCP clients register themselves and sign the user in through the console. The
// workspace chosen on the consent page becomes the consent's reference ID, which
// the access token carries; the API confines the token to that workspace.
export const mcpOAuthProvider = ({
  consoleUrl,
  mcpResource,
}: OAuthConfiguration): BetterAuthPlugin =>
  // The plugin's endpoint metadata types do not satisfy exactOptionalPropertyTypes.
  oauthProvider({
    loginPage: new URL("/oauth/login", consoleUrl).href,
    consentPage: new URL("/oauth/consent", consoleUrl).href,
    postLogin: {
      page: new URL("/oauth/consent", consoleUrl).href,
      shouldRedirect: () => false,
      consentReferenceId: ({ session }) => {
        const workspaceId = Reflect.get(session ?? {}, "oauthWorkspaceId");

        return typeof workspaceId === "string" ? workspaceId : NO_WORKSPACE;
      },
    },
    scopes: SCOPES,
    grantTypes: ["authorization_code", "refresh_token"],
    disableJwtPlugin: true,
    prefix: { opaqueAccessToken: OAUTH_ACCESS_TOKEN_PREFIX },
    accessTokenExpiresIn: 60 * 60,
    refreshTokenExpiresIn: 30 * 24 * 60 * 60,
    allowDynamicClientRegistration: true,
    allowUnauthenticatedClientRegistration: true,
    clientRegistrationRequirePKCE: true,
    clientRegistrationDefaultScopes: SCOPES,
    clientRegistrationAllowedScopes: SCOPES,
    resources: [
      { identifier: mcpResource, name: "Gradiated MCP", allowedScopes: SCOPES },
    ],
    clientRegistrationDefaultResources: [mcpResource],
    clientRegistrationAllowedResources: [mcpResource],
  }) as unknown as BetterAuthPlugin;

const isLoopback = (uri: unknown) => {
  if (typeof uri !== "string" || !URL.canParse(uri)) return false;

  const { protocol, hostname } = new URL(uri);

  return (
    protocol === "http:" &&
    ["localhost", "127.0.0.1", "[::1]"].includes(hostname)
  );
};

// Desktop MCP clients register loopback redirect URIs without an application
// type, which the provider would otherwise treat as a web client and reject.
export const nativeLoopbackRegistration: BetterAuthPlugin = {
  id: "native-loopback-registration",
  hooks: {
    before: [
      {
        matcher: (context) => context.path === "/oauth2/register",
        handler: createAuthMiddleware(async (context) => {
          const body: unknown = context.body;
          if (typeof body !== "object" || body === null) return;

          const uris: unknown = Reflect.get(body, "redirect_uris");
          if (
            Reflect.has(body, "application_type") ||
            !Array.isArray(uris) ||
            !uris.length ||
            !uris.every(isLoopback)
          )
            return;

          return { context: { body: { ...body, application_type: "native" } } };
        }),
      },
    ],
  },
};

export interface OAuthServerApi {
  api: { getOAuthServerConfig: (...args: never[]) => unknown };
}
