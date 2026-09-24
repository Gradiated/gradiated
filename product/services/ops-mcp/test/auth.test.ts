import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createHash } from "node:crypto";
import express from "express";
import { generateKeyPair, SignJWT, type JWTVerifyGetKey } from "jose";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { createAuth, verifyStaff } from "../src/auth.js";

const issuer = "https://argocd.gradiated.com/api/dex";
const origin = "https://ops.gradiated.com";
let key: Awaited<ReturnType<typeof generateKeyPair>>;
let keys: JWTVerifyGetKey;
beforeAll(async () => {
  key = await generateKeyPair("RS256");
  keys = async () => key.publicKey;
});
const jwt = (claims: Record<string, unknown> = {}) =>
  new SignJWT({
    email: "staff@gradiated.com",
    email_verified: true,
    nonce: "nonce",
    ...claims,
  })
    .setProtectedHeader({ alg: "RS256" })
    .setIssuer(issuer)
    .setAudience("production-mcp")
    .setSubject("staff-subject")
    .setIssuedAt()
    .setExpirationTime("5m")
    .sign(key.privateKey);
const directories: string[] = [];
const servers: ReturnType<typeof createServer>[] = [];
afterEach(async () => {
  for (const directory of directories.splice(0))
    rmSync(directory, { recursive: true, force: true });
  for (const server of servers.splice(0)) {
    server.closeAllConnections();
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});
const setup = async (
  email = "staff@gradiated.com",
  options: Partial<Parameters<typeof createAuth>[0]> = {},
) => {
  const redirectUri =
    options.redirectUris?.[0] ?? "http://127.0.0.1:4567/callback";
  let time = Date.now();
  let nonce = "";
  const upstream = vi.fn(
    async () =>
      new Response(JSON.stringify({ id_token: await jwt({ nonce, email }) }), {
        headers: { "content-type": "application/json" },
      }),
  );
  const auth = createAuth({
    origin,
    clientSecret: "test-only-dex-secret",
    redirectUris: [],
    keys,
    fetch: upstream,
    now: () => time,
    ...options,
  });
  const app = express();
  app.use(auth.router);
  const server = createServer(app);
  servers.push(server);
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  const client = (await (
    await fetch(`${base}/register`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        redirect_uris: [redirectUri],
        client_name: "Test <agent>",
        token_endpoint_auth_method: "none",
        grant_types: ["authorization_code"],
        response_types: ["code"],
      }),
    })
  ).json()) as { client_id: string };
  const verifier = "a".repeat(43);
  const challenge = createHash("sha256").update(verifier).digest("base64url");
  const authorize = async (resource = `${origin}/mcp`) => {
    const params = new URLSearchParams({
      client_id: client.client_id,
      redirect_uri: redirectUri,
      response_type: "code",
      state: "client-state",
      code_challenge_method: "S256",
      code_challenge: challenge,
      scope: "production:read",
      resource,
    });
    return fetch(`${base}/authorize?${params}`, { redirect: "manual" });
  };
  const login = async () => {
    const response = await authorize();
    expect(response.status).toBe(200);
    const cookie = response.headers.get("set-cookie")!.split(";")[0]!;
    const html = await response.text();
    expect(html).toContain("Test &lt;agent&gt;");
    const state = /name="state" value="([^"]+)"/.exec(html)![1]!;
    const consent = await fetch(`${base}/oauth/consent`, {
      method: "POST",
      redirect: "manual",
      headers: {
        origin,
        cookie,
        "content-type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams({ state }),
    });
    expect(consent.status).toBe(200);
    const target = /href="([^"]+)"/.exec(await consent.text())![1]!;
    const location = new URL(target.replaceAll("&amp;", "&"));
    expect(location.origin + location.pathname).toBe(`${issuer}/auth`);
    nonce = location.searchParams.get("nonce")!;
    const callback = await fetch(
      `${base}/oauth/callback?${new URLSearchParams({ state, code: "upstream-code" })}`,
      { headers: { cookie }, redirect: "manual" },
    );
    return { callback, cookie, state };
  };
  const exchange = async (code: string, changes: Record<string, string> = {}) =>
    fetch(`${base}/token`, {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "authorization_code",
        client_id: client.client_id,
        code,
        code_verifier: verifier,
        redirect_uri: redirectUri,
        resource: `${origin}/mcp`,
        ...changes,
      }),
    });
  return {
    auth,
    base,
    client,
    authorize,
    login,
    exchange,
    upstream,
    advance: (ms = 3_600_001) => {
      time += ms;
    },
  };
};

describe("staff identity verification", () => {
  it("accepts a verified Gradiated identity signed by the configured issuer", async () => {
    expect(await verifyStaff(await jwt(), "nonce", keys)).toEqual({
      subject: "staff-subject",
      email: "staff@gradiated.com",
    });
  });
  it.each([
    { email: "outsider@example.com" },
    { email: "staff@gradiated.com.evil.test" },
    { email_verified: false },
    { nonce: "wrong" },
    { azp: "another-client" },
  ])("rejects incorrect identity claims: %j", async (claims) => {
    await expect(
      verifyStaff(await jwt(claims), "nonce", keys),
    ).rejects.toThrow();
  });
  it("rejects tokens issued for other services, expired tokens and forged signatures", async () => {
    const other = await generateKeyPair("RS256");
    for (const token of [
      await new SignJWT({ nonce: "nonce" })
        .setProtectedHeader({ alg: "RS256" })
        .setIssuer(issuer)
        .setAudience("nomad-ui")
        .setSubject("s")
        .setIssuedAt()
        .setExpirationTime("1m")
        .sign(key.privateKey),
      await new SignJWT({ nonce: "nonce" })
        .setProtectedHeader({ alg: "RS256" })
        .setIssuer(issuer)
        .setAudience("production-mcp")
        .setSubject("s")
        .setIssuedAt()
        .setExpirationTime(1)
        .sign(key.privateKey),
      await new SignJWT({ nonce: "nonce" })
        .setProtectedHeader({ alg: "RS256" })
        .setIssuer(issuer)
        .setAudience("production-mcp")
        .setSubject("s")
        .setIssuedAt()
        .setExpirationTime("1m")
        .sign(other.privateKey),
    ])
      await expect(verifyStaff(token, "nonce", keys)).rejects.toThrow();
  });
});

describe("MCP OAuth login", () => {
  it("discovers, registers, consents, signs in and issues an expiring resource-specific token", async () => {
    const { auth, base, login, exchange, advance } = await setup();
    const metadata = await (
      await fetch(`${base}/.well-known/oauth-protected-resource/mcp`)
    ).json();
    expect(metadata).toMatchObject({
      resource: `${origin}/mcp`,
      authorization_servers: [`${origin}/`],
    });
    const { callback } = await login();
    expect(callback.status).toBe(302);
    const redirect = new URL(callback.headers.get("location")!);
    expect(redirect.searchParams.get("state")).toBe("client-state");
    expect(redirect.searchParams.get("iss")).toBe(`${origin}/`);
    const code = redirect.searchParams.get("code")!;
    const response = await exchange(code);
    expect(response.status, await response.clone().text()).toBe(200);
    const tokens = (await response.json()) as { access_token: string };
    expect(await auth.authenticate(tokens.access_token)).toEqual({
      subject: "staff-subject",
      email: "staff@gradiated.com",
    });
    expect((await exchange(code)).status).toBe(400);
    advance();
    expect(await auth.authenticate(tokens.access_token)).toBeUndefined();
  });
  it("rejects wrong PKCE, redirect and resource during token exchange", async () => {
    const { login, exchange } = await setup();
    const { callback } = await login();
    const code = new URL(callback.headers.get("location")!).searchParams.get(
      "code",
    )!;
    for (const changes of [
      { code_verifier: "b".repeat(43) },
      { redirect_uri: "http://127.0.0.1:4567/other" },
      { resource: "https://another.test/mcp" },
    ] as Record<string, string>[])
      expect((await exchange(code, changes)).status).toBe(400);
  });
  it("rejects non-staff at the callback without issuing a code", async () => {
    const { login } = await setup("outsider@example.com");
    const { callback } = await login();
    expect(callback.status).toBe(403);
    expect(callback.headers.get("location")).toBeNull();
  });
  it("requires matching browser cookie, explicit consent and state", async () => {
    const { base, upstream } = await setup();
    expect(
      (await fetch(`${base}/oauth/callback?state=wrong&code=test`)).status,
    ).toBe(403);
    expect(
      (
        await fetch(`${base}/oauth/consent`, {
          method: "POST",
          headers: {
            origin,
            "content-type": "application/x-www-form-urlencoded",
          },
          body: "state=wrong",
        })
      ).status,
    ).toBe(400);
    expect(upstream).not.toHaveBeenCalled();
  });
  it("does not exchange an upstream code before explicit browser consent", async () => {
    const { base, authorize, upstream } = await setup();
    const response = await authorize();
    const cookie = response.headers.get("set-cookie")!.split(";")[0]!;
    const state = /name="state" value="([^"]+)"/.exec(
      await response.text(),
    )![1]!;
    const result = await fetch(
      `${base}/oauth/callback?${new URLSearchParams({ state, code: "code" })}`,
      { headers: { cookie }, redirect: "manual" },
    );
    expect(result.status).toBe(403);
    expect(upstream).not.toHaveBeenCalled();
  });
  it("revokes issued access and rejects callback replay", async () => {
    const { base, auth, client, login, exchange } = await setup();
    const { callback, cookie, state } = await login();
    const code = new URL(callback.headers.get("location")!).searchParams.get(
      "code",
    )!;
    const tokens = (await (await exchange(code)).json()) as {
      access_token: string;
    };
    expect(await auth.authenticate(tokens.access_token)).toBeDefined();
    await auth.provider.revokeToken!(
      (await auth.provider.clientsStore.getClient(
        client.client_id,
      )) as NonNullable<
        Awaited<ReturnType<typeof auth.provider.clientsStore.getClient>>
      >,
      { token: tokens.access_token },
    );
    expect(await auth.authenticate(tokens.access_token)).toBeUndefined();
    expect(
      (
        await fetch(
          `${base}/oauth/callback?${new URLSearchParams({ state, code: "code" })}`,
          { headers: { cookie }, redirect: "manual" },
        )
      ).status,
    ).toBe(403);
  });
  it("rejects unapproved external callback URLs", async () => {
    const { base } = await setup();
    const response = await fetch(`${base}/register`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        redirect_uris: ["https://evil.test/callback"],
        token_endpoint_auth_method: "none",
      }),
    });
    expect(response.status).toBe(400);
  });
});

type Tokens = { access_token: string; refresh_token: string };
const connect = async (app: Awaited<ReturnType<typeof setup>>) => {
  const { callback } = await app.login();
  const code = new URL(callback.headers.get("location")!).searchParams.get(
    "code",
  )!;
  const response = await app.exchange(code);
  expect(response.status).toBe(200);
  return (await response.json()) as Tokens;
};
const refresh = (
  app: Awaited<ReturnType<typeof setup>>,
  token: string,
  changes: Record<string, string> = {},
) =>
  fetch(`${app.base}/token`, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "refresh_token",
      client_id: app.client.client_id,
      refresh_token: token,
      resource: `${origin}/mcp`,
      ...changes,
    }),
  });
const sessionFile = () => {
  const directory = mkdtempSync(join(tmpdir(), "ops-mcp-test-"));
  directories.push(directory);
  return join(directory, "sessions.json");
};

describe("renewable sessions", () => {
  it("renews expired access, rotates refresh tokens and revokes the family on replay", async () => {
    const app = await setup();
    const first = await connect(app);
    app.advance();
    expect(await app.auth.authenticate(first.access_token)).toBeUndefined();
    const response = await refresh(app, first.refresh_token);
    expect(response.status).toBe(200);
    const second = (await response.json()) as Tokens;
    expect(second.refresh_token).not.toBe(first.refresh_token);
    expect(await app.auth.authenticate(second.access_token)).toBeDefined();
    expect((await refresh(app, first.refresh_token)).status).toBe(400);
    expect(await app.auth.authenticate(second.access_token)).toBeUndefined();
    expect((await refresh(app, second.refresh_token)).status).toBe(400);
  });

  it("rejects other clients, resources and elevated scopes without consuming the grant", async () => {
    const app = await setup();
    const tokens = await connect(app);
    const other = await app.auth.provider.clientsStore.registerClient!({
      redirect_uris: ["http://127.0.0.1:4568/callback"],
      client_name: "Other",
    });
    for (const changes of [
      { resource: "https://evil.test/mcp" },
      { scope: "production:write" },
      { client_id: other.client_id },
    ] as Record<string, string>[]) {
      expect((await refresh(app, tokens.refresh_token, changes)).status).toBe(
        400,
      );
    }
    expect((await refresh(app, tokens.refresh_token)).status).toBe(200);
  });

  it("bounds the lifetime even when the client keeps renewing", async () => {
    const app = await setup();
    const first = await connect(app);
    app.advance(29 * 24 * 3_600_000);
    const second = (await (
      await refresh(app, first.refresh_token)
    ).json()) as Tokens;
    app.advance(24 * 3_600_000 + 1);
    expect((await refresh(app, second.refresh_token)).status).toBe(400);
  });

  it("persists rotation and revocation across restarts without storing bearer secrets", async () => {
    const path = sessionFile();
    const app = await setup(undefined, { sessionFile: path });
    const first = await connect(app);
    const restart = () =>
      createAuth({
        origin,
        clientSecret: "test-only-dex-secret",
        redirectUris: [],
        sessionFile: path,
      });
    let restarted = restart();
    const client = (await restarted.provider.clientsStore.getClient(
      app.client.client_id,
    ))!;
    expect(client).toBeDefined();
    expect(await restarted.authenticate(first.access_token)).toBeDefined();
    const second = await restarted.provider.exchangeRefreshToken(
      client,
      first.refresh_token,
      undefined,
      new URL(`${origin}/mcp`),
    );
    const disk = readFileSync(path, "utf8");
    for (const token of [
      first.access_token,
      first.refresh_token,
      second.access_token,
      second.refresh_token!,
    ])
      expect(disk).not.toContain(token);
    restarted = restart();
    expect(await restarted.authenticate(second.access_token)).toBeDefined();
    await restarted.provider.revokeToken!(client, {
      token: second.refresh_token!,
    });
    restarted = restart();
    expect(await restarted.authenticate(second.access_token)).toBeUndefined();
    await expect(
      restarted.provider.exchangeRefreshToken(client, second.refresh_token!),
    ).rejects.toThrow();
  });

  it("revokes existing sessions when an identity is denied or the signing secret rotates", async () => {
    const path = sessionFile();
    const app = await setup(undefined, { sessionFile: path });
    const tokens = await connect(app);
    const rotated = createAuth({
      origin,
      clientSecret: "rotated-test-only",
      redirectUris: [],
      sessionFile: path,
    });
    expect(await rotated.authenticate(tokens.access_token)).toBeUndefined();
    expect(
      await rotated.provider.clientsStore.getClient(app.client.client_id),
    ).toBeUndefined();
    const denied = createAuth({
      origin,
      clientSecret: "test-only-dex-secret",
      redirectUris: [],
      sessionFile: path,
      deniedEmails: ["STAFF@gradiated.com"],
    });
    expect(await denied.authenticate(tokens.access_token)).toBeUndefined();
    const client = (await denied.provider.clientsStore.getClient(
      app.client.client_id,
    ))!;
    await expect(
      denied.provider.exchangeRefreshToken(client, tokens.refresh_token),
    ).rejects.toThrow();
  });
});

describe("public client registration", () => {
  it("advertises issuer identification and includes it in authorization errors", async () => {
    const app = await setup();
    const metadata = await (
      await fetch(`${app.base}/.well-known/oauth-authorization-server`)
    ).json();
    expect(metadata).toMatchObject({
      issuer: `${origin}/`,
      authorization_response_iss_parameter_supported: true,
      token_endpoint_auth_methods_supported: ["none"],
    });
    const response = await app.authorize("https://evil.test/mcp");
    expect(response.status).toBe(302);
    const target = new URL(response.headers.get("location")!);
    expect(target.searchParams.get("iss")).toBe(metadata.issuer);
    expect(target.searchParams.get("error")).toBe("invalid_request");
  });
  it("cannot exhaust registrations and rejects tampered client metadata", async () => {
    const app = await setup();
    for (let i = 0; i < 1100; i++) {
      const client = await app.auth.provider.clientsStore.registerClient!({
        redirect_uris: ["http://localhost:8787/callback"],
        client_name: `Agent ${i}`,
      });
      expect(
        await app.auth.provider.clientsStore.getClient(client.client_id),
      ).toBeDefined();
    }
    expect(
      await app.auth.provider.clientsStore.getClient(app.client.client_id),
    ).toBeDefined();
    expect(
      await app.auth.provider.clientsStore.getClient(
        `e30.${app.client.client_id.split(".")[1]}`,
      ),
    ).toBeUndefined();
    expect(
      await app.auth.provider.clientsStore.getClient("a".repeat(5000)),
    ).toBeUndefined();
  });

  it.each([
    "https://claude.ai/api/mcp/auth_callback",
    "https://www.cursor.com/agents/mcp/oauth/callback",
    "https://chatgpt.com/connector_platform_oauth_redirect",
  ])("allows the exact configured hosted callback %s", async (redirect) => {
    const app = await setup(undefined, { redirectUris: [redirect] });
    const client = await app.auth.provider.clientsStore.registerClient!({
      redirect_uris: [redirect],
    });
    expect(client.redirect_uris).toEqual([redirect]);
    const tokens = await connect(app);
    expect(await app.auth.authenticate(tokens.access_token)).toBeDefined();
    expect((await refresh(app, tokens.refresh_token)).status).toBe(200);
    await expect(
      app.auth.provider.clientsStore.registerClient!({
        redirect_uris: [`${redirect}/evil`],
      }),
    ).rejects.toThrow();
    const restricted = createAuth({
      origin,
      clientSecret: "test-only-dex-secret",
      redirectUris: [],
    });
    expect(
      await restricted.provider.clientsStore.getClient(client.client_id),
    ).toBeUndefined();
  });
});
