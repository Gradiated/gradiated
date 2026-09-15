import test from "node:test";
import assert from "node:assert/strict";
import { needsRuntimeVerification as required } from "./verify-inputs.mjs";

test("runtime and base changes require full verification", () => {
  for (const path of [
    "product/inference/images/nomad-base/start-client.sh",
    "product/inference/runtime-launcher/supervise.cpp",
    "product/inference/bundles/deepseek-v4-1-flash/package.sh",
    "product/inference/bundles/build.hcl",
    "product/inference/images/deepseek-v4-1-flash/start.sh",
    "product/inference/.dockerignore",
    ".github/workflows/model-deployment.yml",
  ])
    assert.equal(required([path]), true, path);
});
test("docs, tests, GLM and release tooling do not rebuild DeepSeek", () => {
  assert.equal(
    required([
      "product/inference/images/nomad-base/README.md",
      "product/inference/runtime-launcher/tests/launcher.sh",
      "product/inference/images/glm-5-3-flash/start.sh",
      "tools/models/release.mjs",
      "infra/bootstrap/github-oidc/main.tf",
    ]),
    false,
  );
});
test("a runtime change still requires verification alongside unrelated changes", () => {
  assert.equal(
    required([
      "tools/models/release.test.mjs",
      "product/inference/images/nomad-base/Dockerfile",
    ]),
    true,
  );
});
