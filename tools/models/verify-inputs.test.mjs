import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { bundles } from "./release.mjs";
import { bundlesToVerify } from "./verify-inputs.mjs";

const every = Object.keys(bundles);

test("base and shared packaging changes verify every bundle", () => {
  for (const path of [
    "product/inference/images/nomad-base/start-client.sh",
    "product/inference/runtime-launcher/supervise.cpp",
    "product/inference/bundles/package.sh",
    "product/inference/bundles/build.hcl",
    ".github/workflows/model-deployment.yml",
  ])
    assert.deepEqual(bundlesToVerify([path]), every, path);
});
test("a bundle's own inputs verify only that bundle", () => {
  assert.deepEqual(
    bundlesToVerify(["product/inference/bundles/deepseek-v4-1-flash/vllm"]),
    ["deepseek-v4-1-flash"],
  );
  assert.deepEqual(
    bundlesToVerify(["product/inference/images/deepseek-v4-1-flash/start.sh"]),
    ["deepseek-v4-1-flash"],
  );
  assert.deepEqual(
    bundlesToVerify(["product/inference/runtimes/kev/adapter.py"]),
    ["kev-9b"],
  );
});
test("docs, tests, GLM and release tooling verify nothing", () => {
  assert.deepEqual(
    bundlesToVerify([
      "product/inference/images/nomad-base/README.md",
      "product/inference/runtime-launcher/tests/launcher.sh",
      "product/inference/images/glm-5-3-flash/start.sh",
      "product/inference/runtimes/kev/test_http.py",
      "product/inference/bundles/kev-9b-extra/Dockerfile",
      "tools/models/release.mjs",
      "infra/bootstrap/github-oidc/main.tf",
    ]),
    [],
  );
});
test("every bundle has a verification target", () => {
  const build = readFileSync("product/inference/bundles/build.hcl", "utf8");
  for (const bundle of every)
    assert.match(build, new RegExp(`target "verify-${bundle}"`), bundle);
});
