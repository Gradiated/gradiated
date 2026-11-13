import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { bundles } from "./release.mjs";
import { bundlesToVerify } from "./verify-inputs.mjs";

const every = Object.keys(bundles);

test("base and shared packaging changes verify every bundle", () => {
  for (const path of [
    "product/inference/images/gpu-base/Dockerfile",
    "product/inference/.dockerignore",
    "product/inference/bundles/package.sh",
    "product/inference/bundles/build.hcl",
    ".github/workflows/model-deployment.yml",
  ])
    assert.deepEqual(bundlesToVerify([path]), every, path);
});
test("a bundle's own inputs verify only that bundle", () => {
  assert.deepEqual(
    bundlesToVerify(["product/inference/runtimes/kev/adapter.py"]),
    ["decider-27b", "kev-9b"],
  );
  assert.deepEqual(bundlesToVerify(["product/inference/lora/manager.py"]), [
    "glm-5-3-flash-sglang",
    "deepseek-v4-1-flash-sglang",
  ]);
});
test("Decider runtime changes verify its isolated bundle", () => {
  assert.deepEqual(bundlesToVerify(["product/inference/runtimes/decider/service.py"]), ["decider-27b"]);
});

test("docs, tests, GLM and release tooling verify nothing", () => {
  assert.deepEqual(
    bundlesToVerify([
      "product/inference/images/gpu-base/README.md",
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

test("a pinned autotrain package change verifies the training bundle", () => {
  assert.deepEqual(bundlesToVerify(["product/packages/autotrain"]), [
    "training",
  ]);
});

test("GPU launcher changes verify only the host bundle", () => {
  assert.deepEqual(
    bundlesToVerify(["product/inference/gpu/supervise.py"]).sort(),
    ["host"],
  );
});

test("host agent and staging changes verify only the host bundle", () => {
  for (const path of [
    "product/inference/gpu/host-agent.py",
    "product/inference/runtime-launcher/supervise.cpp",
    "product/inference/gpu/download-runtime.py",
  ])
    assert.deepEqual(bundlesToVerify([path]), ["host"]);
});

test("SGLang GLM bundle and helper changes verify only that runtime", () => {
  for (const input of [
    "product/inference/bundles/glm-5-3-flash-sglang/entrypoint",
    "product/inference/runtimes/glm-sglang/config.py",
  ]) {
    assert.deepEqual(bundlesToVerify([input]), ["glm-5-3-flash-sglang"]);
  }
});

test("shared SGLang build and service changes verify GLM and DeepSeek", () => {
  for (const input of [
    "product/inference/runtimes/glm-sglang/service.py",
    "product/inference/bundles/glm-5-3-flash-sglang/patches.json",
    "product/inference/lora/loader.py",
  ]) {
    assert.deepEqual(bundlesToVerify([input]).sort(), [
      "deepseek-v4-1-flash-sglang",
      "glm-5-3-flash-sglang",
    ]);
  }
  assert.deepEqual(
    bundlesToVerify(["product/inference/runtimes/deepseek-sglang/config.py"]),
    ["deepseek-v4-1-flash-sglang"],
  );
});

test("shared warmup changes verify GLM and Kimi runtimes", () => {
  assert.deepEqual(
    bundlesToVerify(["product/inference/runtimes/glm/warmup-supervisor.py"]),
    ["glm-5-3-flash-sglang", "kimi-k31-pro", "deepseek-v4-1-flash-sglang"],
  );
});

test("Kimi changes verify its isolated runtime and shared SMG fixes verify both users", () => {
  assert.deepEqual(
    bundlesToVerify(["product/inference/runtimes/kimi-k31/config.py"]),
    ["kimi-k31-pro"],
  );
  assert.deepEqual(
    bundlesToVerify([
      "product/inference/bundles/glm-5-3-flash-sglang/smg-patches.json",
    ]),
    ["glm-5-3-flash-sglang", "kimi-k31-pro", "deepseek-v4-1-flash-sglang"],
  );
});


test("shared energy attribution changes verify all SGLang bundles", () => {
  assert.deepEqual(
    bundlesToVerify(["product/inference/runtimes/energy/middleware.py"]),
    ["glm-5-3-flash-sglang", "kimi-k31-pro", "deepseek-v4-1-flash-sglang"],
  );
});
