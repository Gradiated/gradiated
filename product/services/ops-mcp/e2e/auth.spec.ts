import { test, expect, chromium } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createServer } from "node:https";
import type { AddressInfo } from "node:net";
import {
  createServer as createHttpServer,
  type RequestListener,
} from "node:http";
import { generateKeyPair, SignJWT } from "jose";
import { createAuth } from "../src/auth.js";
import { createHttp } from "../src/http.js";

for (const signedIn of [false, true]) {
  test(`production login completes with Google signed in: ${signedIn}`, async () => {
    const directory = mkdtempSync(join(tmpdir(), "mcp-browser-"));
    const origin = "https://ops.gradiated.com";
    execFileSync(
      "openssl",
      [
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-days",
        "1",
        "-subj",
        "/CN=localhost",
        "-keyout",
        join(directory, "key.pem"),
        "-out",
        join(directory, "cert.pem"),
      ],
      { stdio: "ignore" },
    );
    let returnedCode = "";
    let returnedState = "";
    const callbackServer = createHttpServer((req, res) => {
      const url = new URL(req.url!, "http://localhost");
      returnedCode = url.searchParams.get("code") ?? "";
      returnedState = url.searchParams.get("state") ?? "";
      res
        .writeHead(200, { "content-type": "text/html" })
        .end("<h1>Connected</h1>");
    });
    await new Promise<void>((resolve) =>
      callbackServer.listen(0, "127.0.0.1", resolve),
    );
    const callback = `http://127.0.0.1:${(callbackServer.address() as AddressInfo).port}/callback`;
    const key = await generateKeyPair("RS256");
    let upstreamNonce = "";
    let upstreamState = "";
    const auth = createAuth({
      origin,
      clientSecret: "browser-test-only",
      redirectUris: [],
      keys: async () => key.publicKey,
      fetch: async () =>
        new Response(
          JSON.stringify({
            id_token: await new SignJWT({
              email: "staff@gradiated.com",
              email_verified: true,
              nonce: upstreamNonce,
            })
              .setProtectedHeader({ alg: "RS256" })
              .setIssuer("https://argocd.gradiated.com/api/dex")
              .setAudience("production-mcp")
              .setSubject("test-staff")
              .setIssuedAt()
              .setExpirationTime("5m")
              .sign(key.privateKey),
          }),
        ),
    });
    const { server: http, metrics } = createHttp({
      host: "ops.gradiated.com",
      authRouter: auth.router,
      authenticate: auth.authenticate,
      backend: async () => ({}),
      audit: () => {},
    });
    const handler = http.listeners("request")[0] as RequestListener;
    const consentOrigins: (string | undefined)[] = [];
    const server = createServer(
      {
        key: readFileSync(join(directory, "key.pem")),
        cert: readFileSync(join(directory, "cert.pem")),
      },
      (req, res) => {
        if (req.headers.host === "argocd.gradiated.com") {
          const url = new URL(req.url!, "https://argocd.gradiated.com");
          upstreamNonce = url.searchParams.get("nonce")!;
          upstreamState = url.searchParams.get("state")!;
          res
            .writeHead(302, { location: "https://accounts.google.com/signin" })
            .end();
        } else if (req.headers.host === "accounts.google.com") {
          const target = `${origin}/oauth/callback?${new URLSearchParams({ state: upstreamState, code: "fixture-code" })}`;
          if (signedIn) res.writeHead(302, { location: target }).end();
          else
            res
              .writeHead(200, { "content-type": "text/html" })
              .end(
                `<h1>Google sign-in fixture</h1><a href="${target}">Sign in</a>`,
              );
        } else {
          if (req.url === "/oauth/consent")
            consentOrigins.push(req.headers.origin);
          handler(req, res);
        }
      },
    );
    await new Promise<void>((resolve) =>
      server.listen(0, "127.0.0.1", resolve),
    );
    const port = (server.address() as AddressInfo).port;
    const browser = await chromium.launch({
      args: [
        `--host-resolver-rules=MAP ops.gradiated.com:443 127.0.0.1:${port}, MAP argocd.gradiated.com:443 127.0.0.1:${port}, MAP accounts.google.com:443 127.0.0.1:${port}`,
      ],
    });
    try {
      const client = await auth.provider.clientsStore.registerClient!({
        redirect_uris: [callback],
        client_name: "Test <agent>",
        token_endpoint_auth_method: "none",
      });
      const params = new URLSearchParams({
        client_id: client.client_id,
        redirect_uri: client.redirect_uris[0]!,
        response_type: "code",
        state: "browser-test",
        code_challenge_method: "S256",
        code_challenge: "a".repeat(43),
        scope: "production:read",
        resource: `${origin}/mcp`,
      });
      const page = await browser.newPage({ ignoreHTTPSErrors: true });
      const errors: string[] = [];
      page.on("console", (message) => {
        if (message.type() === "error") errors.push(message.text());
      });
      await page.goto(`${origin}/authorize?${params}`);
      await expect(
        page.getByRole("heading", { name: "Production access" }),
      ).toBeVisible();
      await expect(page.getByText("Test <agent>")).toBeVisible();
      await expect(
        page.getByRole("img", { name: "Gradiated" }),
      ).toHaveJSProperty("naturalWidth", 1258);
      for (const width of [390, 1280]) {
        await page.setViewportSize({ width, height: 800 });
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= window.innerWidth,
          ),
        ).toBe(true);
      }
      await page.screenshot({ path: test.info().outputPath("consent.png") });
      await page.getByRole("button", { name: "Continue with Google" }).click();
      if (!signedIn) {
        await expect(page).toHaveURL("https://accounts.google.com/signin");
        await page.getByRole("link", { name: "Sign in" }).click();
      }
      await expect(
        page.getByRole("heading", { name: "Connected" }),
      ).toBeVisible();
      expect(new URL(page.url()).origin).toBe(new URL(callback).origin);
      expect(returnedCode).not.toBe("");
      expect(returnedState).toBe("browser-test");
      expect(
        await auth.provider.challengeForAuthorizationCode(client, returnedCode),
      ).toBe("a".repeat(43));
      expect(consentOrigins).toEqual([origin]);
      expect(errors).toEqual([]);
    } finally {
      await browser.close();
      server.closeAllConnections();
      await new Promise<void>((resolve) => server.close(() => resolve()));
      callbackServer.closeAllConnections();
      await new Promise<void>((resolve) =>
        callbackServer.close(() => resolve()),
      );
      http.close();
      metrics.close();
      rmSync(directory, { recursive: true, force: true });
    }
  });
}
