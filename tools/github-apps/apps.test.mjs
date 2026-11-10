import assert from "node:assert/strict";
import test from "node:test";
import { apps, argoRepositoryCredential, manifest } from "./apps.mjs";

test("apps have unique keys, names and storage targets", () => {
  for (const field of ["key", "name"]) {
    assert.equal(new Set(apps.map((app) => app[field])).size, apps.length);
  }
  const secrets = apps.flatMap((app) => [app.store.github?.secret, app.store.aws?.secretId]).filter(Boolean);
  assert.equal(new Set(secrets).size, apps.length);
});

test("only the release app writes to the production repository through a protected environment", () => {
  for (const app of apps) {
    assert.ok(app.repositories.length > 0);
    const expected = app.key === "docs" ? ["contents", "pull_requests"] : ["contents"];
    assert.deepEqual(Object.keys(app.permissions), expected);
  }
  assert.equal(apps.find((app) => app.key === "release").store.github.environment, "production");
  assert.equal(apps.find((app) => app.key === "autotrain-reader").permissions.contents, "read");
  assert.equal(apps.find((app) => app.key === "argocd").permissions.contents, "read");
});

test("manifests are private, webhook-free and least privilege", () => {
  for (const app of apps) {
    const body = manifest(app, "http://127.0.0.1:1/callback");
    assert.equal(body.public, false);
    assert.equal(body.hook_attributes.active, false);
    assert.deepEqual(body.default_events, []);
    assert.deepEqual(body.default_permissions, { metadata: "read", ...app.permissions });
  }
});

test("Argo CD credential uses HTTPS and string identifiers", () => {
  const app = apps.find((candidate) => candidate.key === "argocd");
  assert.deepEqual(argoRepositoryCredential(app, { id: 12, installationId: 34, pem: "key" }), {
    type: "git",
    url: "https://github.com/Gradiated/gradiated.git",
    githubAppID: "12",
    githubAppInstallationID: "34",
    githubAppPrivateKey: "key",
  });
});
