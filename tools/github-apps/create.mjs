// Creates the GitHub Apps in apps.mjs through GitHub's manifest flow and stores
// each private key directly in its consumer's secret store. Keys never reach
// stdout, files in the repository, or command-line arguments.
//
// Usage: mise run github-apps:create -- [app-key ...]
import { spawnSync } from "node:child_process";
import { createSign, randomBytes } from "node:crypto";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import os from "node:os";
import path from "node:path";
import { apps, argoRepositoryCredential, manifest, owner } from "./apps.mjs";

const api = "https://api.github.com";
const env = { ...process.env, AWS_PROFILE: process.env.AWS_PROFILE ?? "gradiated-admin" };

function run(command, args, input) {
  const result = spawnSync(command, args, { env, input, encoding: "utf8", stdio: ["pipe", "pipe", "pipe"] });
  if (result.status !== 0) {
    throw new Error(`${command} ${args.slice(0, 3).join(" ")} failed: ${result.stderr.trim()}`);
  }
  return result.stdout;
}

function escapeHtml(value) {
  return value.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

async function github(method, url, token, body) {
  const response = await fetch(`${api}${url}`, {
    method,
    headers: {
      accept: "application/vnd.github+json",
      "x-github-api-version": "2022-11-28",
      ...(token ? { authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) throw new Error(`${method} ${url}: ${response.status} ${await response.text()}`);
  return response.json();
}

function appJwt(clientId, pem) {
  const encode = (value) => Buffer.from(JSON.stringify(value)).toString("base64url");
  const now = Math.floor(Date.now() / 1000);
  const unsigned = `${encode({ alg: "RS256", typ: "JWT" })}.${encode({ iat: now - 60, exp: now + 540, iss: clientId })}`;
  const signature = createSign("RSA-SHA256").update(unsigned).sign(pem, "base64url");
  return `${unsigned}.${signature}`;
}

async function createApp(app) {
  const state = randomBytes(16).toString("hex");
  return new Promise((resolve, reject) => {
    const server = createServer(async (request, response) => {
      const url = new URL(request.url, "http://127.0.0.1");
      if (url.pathname === "/") {
        const target = `https://github.com/organizations/${owner}/settings/apps/new?state=${state}`;
        const body = escapeHtml(JSON.stringify(manifest(app, `http://127.0.0.1:${server.address().port}/callback`)));
        response.writeHead(200, { "content-type": "text/html" });
        response.end(`<form id="f" method="post" action="${target}"><input type="hidden" name="manifest" value="${body}"></form><script>f.submit()</script>`);
        return;
      }
      if (url.pathname !== "/callback") {
        response.writeHead(404).end();
        return;
      }
      try {
        if (url.searchParams.get("state") !== state) throw new Error("State mismatch in GitHub callback");
        const created = await github("POST", `/app-manifests/${url.searchParams.get("code")}/conversions`);
        response.writeHead(200, { "content-type": "text/plain" }).end(`${app.name} created. Return to the terminal.`);
        resolve({ id: created.id, slug: created.slug, clientId: created.client_id, pem: created.pem });
      } catch (error) {
        response.writeHead(500, { "content-type": "text/plain" }).end("App creation failed. See the terminal.");
        reject(error);
      } finally {
        server.close();
      }
    });
    server.listen(0, "127.0.0.1", () => {
      const local = `http://127.0.0.1:${server.address().port}/`;
      console.log(`\n${app.name}: confirm "Create GitHub App" in the browser (${local})`);
      spawnSync("open", [local]);
    });
  });
}

async function waitForInstallation(app, created) {
  const expected = [...app.repositories].sort();
  console.log(`${app.name}: install on ${owner} with "Only select repositories": ${expected.join(", ")}`);
  spawnSync("open", [`https://github.com/apps/${created.slug}/installations/new`]);
  const deadline = Date.now() + 15 * 60_000;
  while (Date.now() < deadline) {
    const jwt = appJwt(created.clientId, created.pem);
    const installation = (await github("GET", "/app/installations", jwt)).find((item) => item.account.login === owner);
    if (installation) {
      const { token } = await github("POST", `/app/installations/${installation.id}/access_tokens`, jwt);
      const repositories = (await github("GET", "/installation/repositories?per_page=100", token)).repositories
        .map((repository) => repository.name)
        .sort();
      if (installation.repository_selection === "selected" && repositories.join() === expected.join()) {
        return installation.id;
      }
      console.log(`${app.name}: installation covers [${repositories.join(", ")}]; narrow it to [${expected.join(", ")}] in its settings.`);
    }
    await new Promise((done) => setTimeout(done, 5_000));
  }
  throw new Error(`${app.name}: no correctly scoped installation within 15 minutes`);
}

function storeGithub(app, created) {
  const target = app.store.github;
  const repository = `${owner}/${target.repository}`;
  const scope = target.environment ? ["--env", target.environment] : [];
  run("gh", ["secret", "set", target.secret, "--repo", repository, ...scope], created.pem);
  run("gh", ["variable", "set", target.variable, "--repo", repository, "--body", created.clientId]);
  console.log(`${app.name}: stored ${target.secret}${target.environment ? ` (${target.environment})` : ""} and ${target.variable}`);
}

function storeAws(app, created, installationId) {
  const directory = mkdtempSync(path.join(os.tmpdir(), "github-app-"));
  const file = path.join(directory, "secret.json");
  try {
    writeFileSync(file, JSON.stringify(argoRepositoryCredential(app, { ...created, installationId })), { mode: 0o600 });
    run("aws", ["secretsmanager", "put-secret-value", "--secret-id", app.store.aws.secretId, "--secret-string", `file://${file}`]);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
  console.log(`${app.name}: stored Argo CD repository credential in ${app.store.aws.secretId}`);
}

const selected = process.argv.slice(2);
const unknown = selected.filter((key) => !apps.some((app) => app.key === key));
if (unknown.length) {
  console.error(`Unknown app: ${unknown.join(", ")}. Choose from: ${apps.map((app) => app.key).join(", ")}`);
  process.exit(1);
}

for (const app of apps.filter((candidate) => !selected.length || selected.includes(candidate.key))) {
  // Check the destination first so a newly generated key is never stranded.
  if (app.store.aws) run("aws", ["secretsmanager", "describe-secret", "--secret-id", app.store.aws.secretId]);
  else run("gh", ["secret", "list", "--repo", `${owner}/${app.store.github.repository}`]);

  const created = await createApp(app);
  console.log(`${app.name}: created app ${created.id} (${created.slug})`);
  if (app.store.github) storeGithub(app, created);
  const installationId = await waitForInstallation(app, created);
  if (app.store.aws) storeAws(app, created, installationId);
  console.log(`${app.name}: installation ${installationId} verified`);
}
