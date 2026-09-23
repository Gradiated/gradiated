import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
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
const servers: ReturnType<typeof createServer>[] = [];
afterEach(async () => {
  for (const server of servers.splice(0)) {
    server.closeAllConnections();
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});
const setup = async (email = "staff@gradiated.com") => {
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
        redirect_uris: ["http://127.0.0.1:4567/callback"],
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
      redirect_uri: "http://127.0.0.1:4567/callback",
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
    expect(consent.status).toBe(302);
    const location = new URL(consent.headers.get("location")!);
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
        redirect_uri: "http://127.0.0.1:4567/callback",
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
    advance: () => {
      time += 3_600_001;
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
