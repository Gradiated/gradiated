import { test, expect, chromium } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createServer } from "node:https";
import type { AddressInfo } from "node:net";
import type { RequestListener } from "node:http";
import { createAuth } from "../src/auth.js";
import { createHttp } from "../src/http.js";

test("production consent preserves browser origin and reaches Google", async () => {
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
  const auth = createAuth({
    origin,
    clientSecret: "browser-test-only",
    redirectUris: [],
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
        res
          .writeHead(302, { location: "https://accounts.google.com/signin" })
          .end();
      } else if (req.headers.host === "accounts.google.com") {
        res
          .writeHead(200, { "content-type": "text/html" })
          .end("<h1>Google sign-in fixture</h1>");
      } else {
        if (req.url === "/oauth/consent")
          consentOrigins.push(req.headers.origin);
        handler(req, res);
      }
    },
  );
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = (server.address() as AddressInfo).port;
  const browser = await chromium.launch({
    args: [
      `--host-resolver-rules=MAP ops.gradiated.com:443 127.0.0.1:${port}, MAP argocd.gradiated.com:443 127.0.0.1:${port}, MAP accounts.google.com:443 127.0.0.1:${port}`,
    ],
  });
  try {
    const client = await auth.provider.clientsStore.registerClient!({
      redirect_uris: ["http://127.0.0.1:53682/callback"],
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
    await expect(page.getByRole("img", { name: "Gradiated" })).toHaveJSProperty(
      "naturalWidth",
      1258,
    );
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
    await expect(page).toHaveURL("https://accounts.google.com/signin");
    await expect(
      page.getByRole("heading", { name: "Google sign-in fixture" }),
    ).toBeVisible();
    expect(consentOrigins).toEqual([origin]);
    expect(errors).toEqual([]);
  } finally {
    await browser.close();
    server.closeAllConnections();
    await new Promise<void>((resolve) => server.close(() => resolve()));
    http.close();
    metrics.close();
    rmSync(directory, { recursive: true, force: true });
  }
});
