import {
  createHash,
  createHmac,
  randomBytes,
  timingSafeEqual,
} from "node:crypto";
import express, { type Response } from "express";
import { createRemoteJWKSet, jwtVerify, type JWTVerifyGetKey } from "jose";
import {
  mcpAuthRouter,
  createOAuthMetadata,
} from "@modelcontextprotocol/sdk/server/auth/router.js";
import type {
  OAuthServerProvider,
  AuthorizationParams,
} from "@modelcontextprotocol/sdk/server/auth/provider.js";
import type { OAuthClientInformationFull } from "@modelcontextprotocol/sdk/shared/auth.js";
import {
  InvalidGrantError,
  InvalidRequestError,
  InvalidTokenError,
} from "@modelcontextprotocol/sdk/server/auth/errors.js";
import { z } from "zod";
import { fileURLToPath } from "node:url";
import { createSessions, type Session } from "./sessions.js";
import { authPage, consentPage, escaped, pagePolicy } from "./auth-page.js";

const ISSUER = "https://argocd.gradiated.com/api/dex";
const CLIENT = "production-mcp";
const COOKIE = "__Host-mcp-login";
const random = () => randomBytes(32).toString("base64url");
const hash = (value: string) =>
  createHash("sha256").update(value).digest("base64url");
const equal = (a: string, b: string) =>
  timingSafeEqual(Buffer.from(hash(a)), Buffer.from(hash(b)));
export type Identity = { subject: string; email: string };

export const verifyStaff = async (
  token: string,
  nonce: string,
  keys: JWTVerifyGetKey,
): Promise<Identity> => {
  const { payload } = await jwtVerify(token, keys, {
    issuer: ISSUER,
    audience: CLIENT,
    algorithms: ["RS256"],
    requiredClaims: ["exp", "iat", "sub", "nonce"],
  });
  if (
    payload.nonce !== nonce ||
    payload.email_verified !== true ||
    typeof payload.email !== "string" ||
    !/^[^@\s]+@gradiated\.com$/i.test(payload.email) ||
    (payload.azp !== undefined && payload.azp !== CLIENT)
  ) {
    throw new InvalidGrantError("Gradiated staff login required");
  }

  return { subject: payload.sub!, email: payload.email.toLowerCase() };
};

type Pending = {
  client: string;
  params: AuthorizationParams;
  nonce: string;
  verifier: string;
  cookie: string;
  expires: number;
  consented: boolean;
};
type Code = {
  client: string;
  params: AuthorizationParams;
  identity: Identity;
  expires: number;
};
const cookieOptions = {
  secure: true,
  httpOnly: true,
  sameSite: "lax" as const,
  path: "/",
  maxAge: 300_000,
};

export const createAuth = (options: {
  origin: string;
  clientSecret: string;
  redirectUris: string[];
  fetch?: typeof fetch;
  keys?: JWTVerifyGetKey;
  now?: () => number;
  sessionFile?: string;
  deniedEmails?: string[];
  audit?: (event: Record<string, unknown>) => void;
}): {
  router: express.Router;
  provider: OAuthServerProvider;
  authenticate: (token: string) => Promise<Identity | undefined>;
} => {
  if (
    options.redirectUris.some((uri) => {
      const url = new URL(uri);
      return (
        url.protocol !== "https:" ||
        !!url.username ||
        !!url.password ||
        !!url.hash
      );
    })
  )
    throw new Error("Configured remote OAuth callbacks must use HTTPS");
  const origin = new URL(options.origin).origin;
  const resource = `${origin}/mcp`;
  const issuer = new URL(origin).href;
  const callback = `${origin}/oauth/callback`;
  const now = options.now ?? Date.now;
  const fetcher = options.fetch ?? fetch;
  const keys =
    options.keys ??
    createRemoteJWKSet(new URL(`${ISSUER}/keys`), { timeoutDuration: 5000 });
  const signClient = (data: string) =>
    createHmac("sha256", options.clientSecret)
      .update(`ops-mcp-client-v1:${data}`)
      .digest("base64url");
  const sessions = createSessions(
    signClient("session-key"),
    options.sessionFile,
  );
  const denied = new Set(
    options.deniedEmails?.map((email) => email.toLowerCase()),
  );
  const allowedIdentity = (identity: Identity) => !denied.has(identity.email);
  const clientMetadata = z.object({
    redirect_uris: z.array(z.string().url().max(512)).min(1).max(5),
    client_name: z.string().max(128).optional(),
  });
  const pending = new Map<string, Pending>();
  const codes = new Map<string, Code>();
  const prune = () => {
    for (const map of [pending, codes]) {
      for (const [key, value] of map)
        if (value.expires <= now()) map.delete(key);
    }
  };
  const allowedRedirect = (uri: string) => {
    const url = new URL(uri);
    if (url.username || url.password || url.hash) return false;
    return (
      (url.protocol === "http:" &&
        ["127.0.0.1", "localhost", "[::1]"].includes(url.hostname)) ||
      options.redirectUris.includes(uri)
    );
  };
  const getFlow = (state: unknown, cookie: string | undefined) => {
    prune();
    if (typeof state !== "string")
      throw new InvalidRequestError("Invalid login");
    const flow = pending.get(state);
    const supplied = cookie
      ?.split(";")
      .map((value) => value.trim())
      .find((value) => value.startsWith(`${COOKIE}=`))
      ?.slice(COOKIE.length + 1);
    if (!flow || !supplied || !equal(flow.cookie, supplied))
      throw new InvalidRequestError("Invalid login");
    return flow;
  };
  // The client ID carries signed public metadata, not a credential. Registration
  // allocates no server-side state, so anonymous callers cannot fill a client table.
  const getClient = (id: string): OAuthClientInformationFull | undefined => {
    if (id.length > 4096) return undefined;
    const parts = id.split(".");
    if (parts.length !== 2 || !equal(signClient(parts[0]!), parts[1]!))
      return undefined;
    try {
      const metadata = clientMetadata.parse(
        JSON.parse(Buffer.from(parts[0]!, "base64url").toString()),
      );
      if (!metadata.redirect_uris.every(allowedRedirect)) return undefined;
      return {
        ...metadata,
        client_id: id,
        token_endpoint_auth_method: "none",
        grant_types: ["authorization_code", "refresh_token"],
        response_types: ["code"],
      };
    } catch {
      return undefined;
    }
  };
  const issue = (
    id: string,
    grant: Omit<Session, "accessHash" | "accessExpires" | "refreshHash">,
  ) => {
    const token = `${id}.${random()}`;
    const refresh = `${id}.${random()}`;
    const accessExpires = Math.min(now() + 3_600_000, grant.expires);
    sessions.put(id, {
      ...grant,
      accessHash: hash(token),
      accessExpires,
      refreshHash: hash(refresh),
    });
    return {
      access_token: token,
      refresh_token: refresh,
      token_type: "Bearer",
      expires_in: Math.floor((accessExpires - now()) / 1000),
      scope: "production:read",
    };
  };
  const tokenSession = (token: string) => {
    if (token.length > 256) return undefined;
    const id = token.split(".")[0]!;
    const session = sessions.get(id);
    if (!session) return undefined;
    if (
      session.expires <= now() ||
      !allowedIdentity(session.identity) ||
      !getClient(session.client)
    ) {
      sessions.remove(id);
      return undefined;
    }
    return { id, session };
  };
  const audit = (event: string, session: Pick<Session, "identity">) =>
    options.audit?.({
      service: "ops-mcp",
      event,
      principal: session.identity.subject,
      email: session.identity.email,
    });
  const provider: OAuthServerProvider = {
    clientsStore: {
      getClient,
      registerClient: async (input) => {
        if (
          JSON.stringify(input).length > 4096 ||
          (input.token_endpoint_auth_method &&
            input.token_endpoint_auth_method !== "none")
        )
          throw new InvalidRequestError("Unsupported client registration");
        const parsed = clientMetadata.safeParse(input);
        if (
          !parsed.success ||
          !parsed.data.redirect_uris.every(allowedRedirect)
        )
          throw new InvalidRequestError("Unsupported client registration");
        const data = Buffer.from(JSON.stringify(parsed.data)).toString(
          "base64url",
        );
        const client = getClient(`${data}.${signClient(data)}`);
        if (!client)
          throw new InvalidRequestError("Unsupported client registration");
        return client;
      },
    },
    authorize: async (client, params, res: Response) => {
      prune();
      if (
        (params.resource?.href ?? resource) !== resource ||
        !params.codeChallenge ||
        params.scopes?.some((scope) => scope !== "production:read") ||
        pending.size >= 100
      )
        throw new InvalidRequestError("Invalid authorization request");
      const state = random();
      const flow: Pending = {
        client: client.client_id,
        params: { ...params, resource: new URL(resource) },
        cookie: random(),
        nonce: random(),
        verifier: random(),
        expires: now() + 300_000,
        consented: false,
      };
      pending.set(state, flow);
      res.cookie(COOKIE, flow.cookie, cookieOptions);
      res.setHeader("Content-Security-Policy", pagePolicy);
      res.setHeader("Cache-Control", "no-store");
      // Preserve Origin on the same-origin consent POST without leaking the
      // authorization URL to the external identity provider.
      res.setHeader("Referrer-Policy", "same-origin");
      res
        .type("html")
        .send(
          consentPage(
            client.client_name ?? "your agent",
            client.client_id,
            params.redirectUri,
            state,
          ),
        );
    },
    challengeForAuthorizationCode: async (client, code) => {
      prune();
      const grant = codes.get(hash(code));
      if (!grant || grant.client !== client.client_id)
        throw new InvalidGrantError("Invalid code");
      return grant.params.codeChallenge;
    },
    // The SDK validates S256 PKCE via challengeForAuthorizationCode before exchange.
    exchangeAuthorizationCode: async (
      client,
      code,
      _verifier,
      redirectUri,
      requestedResource,
    ) => {
      prune();
      const grant = codes.get(hash(code));
      if (
        !grant ||
        grant.client !== client.client_id ||
        redirectUri !== grant.params.redirectUri ||
        (requestedResource?.href ?? resource) !== resource
      )
        throw new InvalidGrantError("Invalid code");
      codes.delete(hash(code));
      if (!allowedIdentity(grant.identity))
        throw new InvalidGrantError("Access revoked");
      sessions.prune(now());
      const tokens = issue(random(), {
        client: client.client_id,
        identity: grant.identity,
        expires: now() + 30 * 24 * 3_600_000,
        usedRefreshHashes: [],
      });
      audit("oauth_session_created", grant);
      return tokens;
    },
    exchangeRefreshToken: async (client, token, scopes, requestedResource) => {
      if (
        (requestedResource && requestedResource.href !== resource) ||
        scopes?.some((scope) => scope !== "production:read")
      )
        throw new InvalidGrantError("Invalid refresh resource or scope");
      const found = tokenSession(token);
      if (!found || found.session.client !== client.client_id)
        throw new InvalidGrantError("Invalid refresh token");
      const { id, session } = found;
      const digest = hash(token);
      if (session.usedRefreshHashes.includes(digest)) {
        sessions.remove(id);
        audit("oauth_refresh_replay", session);
        throw new InvalidGrantError("Refresh token replay; sign in again");
      }
      if (!equal(digest, session.refreshHash))
        throw new InvalidGrantError("Invalid refresh token");
      if (session.usedRefreshHashes.length >= 1024) {
        sessions.remove(id);
        throw new InvalidGrantError("Sign in again to renew production access");
      }
      const tokens = issue(id, {
        ...session,
        usedRefreshHashes: [...session.usedRefreshHashes, digest],
      });
      audit("oauth_session_refreshed", session);
      return tokens;
    },
    verifyAccessToken: async (token) => {
      const found = tokenSession(token);
      if (
        !found ||
        found.session.accessExpires <= now() ||
        !equal(hash(token), found.session.accessHash)
      )
        throw new InvalidTokenError("Sign in with Gradiated Google login");
      const grant = found.session;
      return {
        token,
        clientId: grant.client,
        scopes: ["production:read"],
        expiresAt: Math.floor(grant.accessExpires / 1000),
        resource: new URL(resource),
        extra: grant.identity,
      };
    },
    revokeToken: async (client, request) => {
      const found = tokenSession(request.token);
      if (!found || found.session.client !== client.client_id) return;
      const digest = hash(request.token);
      if (
        equal(digest, found.session.accessHash) ||
        equal(digest, found.session.refreshHash) ||
        found.session.usedRefreshHashes.includes(digest)
      ) {
        sessions.remove(found.id);
        audit("oauth_session_revoked", found.session);
      }
    },
  };
  const router = express.Router();
  router.use((_req, res, next) => {
    res.setHeader("Cache-Control", "no-store");
    res.setHeader("Referrer-Policy", "no-referrer");
    next();
  });
  router.get("/brand/gradiated.svg", (_req, res) => {
    res.sendFile("gradiated-full.svg", {
      root: fileURLToPath(
        new URL("../../console/public/brand/", import.meta.url),
      ),
    });
  });
  // Apply small body limits before the SDK's parsers on public OAuth endpoints.
  router.use("/register", express.json({ limit: "4kb" }));
  router.use(
    ["/token", "/revoke", "/authorize"],
    express.urlencoded({ extended: false, limit: "8kb" }),
  );
  const oauthOptions = {
    provider,
    issuerUrl: new URL(origin),
    resourceServerUrl: new URL(resource),
    scopesSupported: ["production:read"],
    resourceName: "Gradiated production",
  };
  router.get("/.well-known/oauth-authorization-server", (_req, res) => {
    res.json({
      ...createOAuthMetadata(oauthOptions),
      authorization_response_iss_parameter_supported: true,
      token_endpoint_auth_methods_supported: ["none"],
      revocation_endpoint_auth_methods_supported: ["none"],
    });
  });
  // SDK-validated error redirects must carry the same RFC 9207 issuer as success.
  router.use("/authorize", (_req, res, next) => {
    const location = res.location.bind(res);
    res.location = (url: string) => {
      const target = new URL(url);
      target.searchParams.set("iss", issuer);
      return location(target.href);
    };
    next();
  });
  router.use(mcpAuthRouter(oauthOptions));
  router.post(
    "/oauth/consent",
    express.urlencoded({ extended: false, limit: "4kb" }),
    (req, res) => {
      try {
        if (req.headers.origin !== origin)
          throw new InvalidRequestError("Invalid origin");
        const flow = getFlow(req.body.state, req.headers.cookie);
        if (flow.consented)
          throw new InvalidRequestError("Login already started");
        flow.consented = true;
        const url = new URL(`${ISSUER}/auth`);
        url.search = new URLSearchParams({
          client_id: CLIENT,
          redirect_uri: callback,
          response_type: "code",
          scope: "openid email profile",
          state: req.body.state,
          nonce: flow.nonce,
          code_challenge: hash(flow.verifier),
          code_challenge_method: "S256",
        }).toString();
        // Finish the form navigation before starting OAuth. An existing Google
        // session can redirect all the way to the client's loopback callback,
        // which must not inherit the consent form's same-origin restriction.
        res
          .set("Content-Security-Policy", pagePolicy)
          .type("html")
          .send(
            authPage(
              "Connecting to Google",
              `<p class="intro">Taking you to Gradiated Google sign-in.</p><p class="intro"><a href="${escaped(url.href)}">Continue to Google</a></p>`,
              url.href,
            ),
          );
      } catch {
        res
          .status(400)
          .set("Content-Security-Policy", pagePolicy)
          .type("html")
          .send(
            authPage(
              "Start a new login",
              '<p class="intro">This sign-in link expired or is invalid. Start login again from your MCP client.</p>',
            ),
          );
      }
    },
  );
  router.get("/oauth/callback", async (req, res) => {
    try {
      const flow = getFlow(req.query.state, req.headers.cookie);
      pending.delete(String(req.query.state));
      if (
        !flow.consented ||
        typeof req.query.code !== "string" ||
        req.query.code.length > 4096
      )
        throw new InvalidGrantError("Invalid callback");
      const response = await fetcher(`${ISSUER}/token`, {
        method: "POST",
        redirect: "error",
        signal: AbortSignal.timeout(10_000),
        headers: {
          "content-type": "application/x-www-form-urlencoded",
          authorization: `Basic ${Buffer.from(`${CLIENT}:${options.clientSecret}`).toString("base64")}`,
        },
        body: new URLSearchParams({
          grant_type: "authorization_code",
          code: req.query.code,
          redirect_uri: callback,
          code_verifier: flow.verifier,
        }),
      });
      if (!response.ok) throw new InvalidGrantError("Login failed");
      const tokens = z
        .object({ id_token: z.string().max(16_384) })
        .parse(await response.json());
      const identity = await verifyStaff(tokens.id_token, flow.nonce, keys);
      if (!allowedIdentity(identity))
        throw new InvalidGrantError("Access revoked");
      prune();
      if (codes.size >= 100)
        throw new InvalidGrantError("Login capacity reached");
      const code = random();
      codes.set(hash(code), {
        client: flow.client,
        params: flow.params,
        identity,
        expires: now() + 60_000,
      });
      res.clearCookie(COOKIE, cookieOptions);
      const target = new URL(flow.params.redirectUri);
      target.searchParams.set("code", code);
      target.searchParams.set("iss", issuer);
      if (flow.params.state)
        target.searchParams.set("state", flow.params.state);
      res.redirect(target.href);
    } catch {
      res
        .status(403)
        .set("Content-Security-Policy", pagePolicy)
        .type("html")
        .send(
          authPage(
            "Sign-in unsuccessful",
            '<p class="intro">Sign in again from your MCP client using your gradiated.com Google account. Your sign-in link may have expired.</p>',
          ),
        );
    }
  });

  return {
    router,
    provider,
    authenticate: async (token: string): Promise<Identity | undefined> => {
      try {
        const info = await provider.verifyAccessToken(token);
        return info.extra as Identity;
      } catch {
        return undefined;
      }
    },
  };
};
